"""Phase 0 Maya probe: checks the H-MY-* hypotheses on a real Maya.

Run in Maya 2023+ (Script Editor, Python), ideally in a scene that has a
Scene Time Warp created from the Maya UI:

    import sys
    sys.path.insert(0, r"<repo>/maya_plugin/scripts")
    import syncbridge_maya.probe as probe
    probe.run(r"<repo>/probe_results/maya_probe.json")

The probe does not modify the scene's Scene Time Warp. It creates temporary
animCurveTT nodes for the write tests and deletes them afterwards.
Paste the printed summary (or the JSON) into docs/PHASE0_RESEARCH.md.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import traceback

from maya import cmds, mel

from syncbridge.core import maya_codec, testcurves
from syncbridge.core.validation import compare_samples
from . import anim_curve, scene_timewarp

TIME_NODE = scene_timewarp.TIME_NODE


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # the probe must report, not stop
        return {"error": "%s: %s" % (type(exc).__name__, exc), "traceback": traceback.format_exc()}


def probe_environment() -> dict:
    info = {
        "maya_version": cmds.about(version=True),
        "maya_api": cmds.about(apiVersion=True),
        "python": sys.version,
        "os": platform.platform(),
        "time_unit": cmds.currentUnit(q=True, time=True),
    }
    try:
        import PySide2  # noqa: F401
        info["pyside2"] = PySide2.__version__
    except ImportError as exc:
        info["pyside2"] = "not importable: %s" % exc
    return info


def probe_time_node() -> dict:
    """H-MY-1/2: what does time1 look like and what is connected to it?"""
    attrs = cmds.listAttr(TIME_NODE) or []
    warp_attrs = {}
    for a in attrs:
        if "warp" in a.lower():
            warp_attrs[a] = {
                "type": _safe(cmds.getAttr, "%s.%s" % (TIME_NODE, a), type=True),
                "value": _safe(cmds.getAttr, "%s.%s" % (TIME_NODE, a)),
            }
    conns = cmds.listConnections(TIME_NODE, plugs=True, connections=True) or []
    return {
        "all_attributes": attrs,
        "warp_attributes": warp_attrs,
        "connections": [[a, b, _safe(cmds.nodeType, b.split(".")[0])]
                        for a, b in zip(conns[0::2], conns[1::2])],
        "animCurveTT_nodes": [
            {"node": n, "outputs": _pairs(cmds.listConnections(n, plugs=True, connections=True,
                                                              source=False, destination=True))}
            for n in (cmds.ls(type="animCurveTT") or [])],
    }


def probe_commands() -> dict:
    """Which commands / runtime commands / MEL procs mention time warp?"""
    found = {"commands": _safe(cmds.help, "*arp*", list=True)}
    rtc = []
    for flag in ("userCommandArray", "defaultCommandArray", "commandArray"):
        names = _safe(cmds.runTimeCommand, q=True, **{flag: True})
        if isinstance(names, list):
            rtc.extend(names)
    rtc = sorted({n for n in rtc if "warp" in n.lower()})
    found["runtime_commands"] = {n: _safe(cmds.runTimeCommand, n, q=True, command=True) for n in rtc}
    for name in rtc[:20]:
        found.setdefault("whatIs", {})[name] = _safe(mel.eval, 'whatIs "%s"' % name)
    return found


def _pairs(conns) -> list:
    conns = conns or []
    return [[a, b] for a, b in zip(conns[0::2], conns[1::2])]


def probe_curve_node(curve: str) -> dict:
    """Attributes of an animCurve node relevant to H-MY-1/9 (read-only)."""
    info = {"attributes": _safe(cmds.listAttr, curve)}
    for side in ("pre", "post"):
        flag = {"pre": "preInfinite", "post": "postInfinite"}[side]
        info["%s_infinity" % side] = {
            "setInfinity_query": _safe(cmds.setInfinity, curve, q=True, **{flag: True}),
            "getAttr_asString": _safe(cmds.getAttr, "%s.%sInfinity" % (curve, side), asString=True),
        }
    return info


def probe_scene_warp() -> dict:
    """H-MY-1/2/3/9 on the existing Scene Time Warp, read-only."""
    try:
        curve, plug = scene_timewarp.find_curve()
    except scene_timewarp.SceneTimeWarpNotFound as exc:
        return {"found": False, "message": str(exc)}
    result = {"found": True, "curve": curve, "plug": plug,
              "enabled": scene_timewarp.is_enabled(),
              "node": probe_curve_node(curve),
              "raw": _safe(anim_curve.read_raw, curve)}
    raw = result["raw"]
    if "error" in raw:
        return result
    checks = []
    for t, v in list(zip(raw["times"], raw["values"]))[:10]:
        checks.append({
            "time": t, "valueChange": v,
            "keyframe_eval": _safe(cmds.keyframe, curve, q=True, eval=True, time=(t, t)),
            "getAttr_curve_output": _safe(cmds.getAttr, curve + ".output", time=t),
            "getAttr_curve_apply": _safe(cmds.getAttr, curve + ".apply", time=t),
            "getAttr_time1_outTime": _safe(cmds.getAttr, TIME_NODE + ".outTime", time=t),
            "getAttr_time1_unwarpedTime": _safe(cmds.getAttr, TIME_NODE + ".unwarpedTime", time=t),
        })
    result["unit_checks"] = checks
    read = _safe(anim_curve.read_curve, curve)
    result["calibration"] = read if isinstance(read, dict) else read[2]
    return result


def probe_write_roundtrip() -> list:
    """Write each reference curve to a temp animCurveTT and compare Maya's evaluation.

    Tests H-MY-4/5/6 and the codec end to end. Each candidate weight scale is
    tried for weighted curves; the matching one confirms H-MY-5.
    """
    fps = anim_curve.scene_fps()
    spf = fps.frame_duration
    results = []
    for name, make in testcurves.PROBE_CURVES.items():
        curve_s = make()
        native = maya_codec.encode(curve_s, fps.to_json())
        scales = list(anim_curve.WEIGHT_SCALE_CANDIDATES) if native["weighted"] \
            else [anim_curve.DEFAULT_WEIGHT_SCALE]
        for scale in scales:
            node = None
            entry = {"curve": name, "weighted": native["weighted"], "weight_scale": scale}
            try:
                node = cmds.createNode("animCurveTT", name="syncbridgeProbe_" + name)
                anim_curve.write_curve(node, native, scale)
                raw = anim_curve.read_raw(node)
                frames = anim_curve.sample_frames(raw, oversample=8)
                values = anim_curve.sample(node, frames)
                rep = compare_samples([f * spf for f in frames], [v * spf for v in values],
                                      curve_s.evaluate, fps.to_json(), 0.01)
                entry["maya_vs_expected"] = rep.to_json()
                entry["read_back_types"] = [raw["inTangentType"], raw["outTangentType"]]
            except Exception:
                entry["error"] = traceback.format_exc()
            finally:
                if node and cmds.objExists(node):
                    cmds.delete(node)
            results.append(entry)
    return results


def run(path: str = None) -> dict:
    report = {
        "environment": _safe(probe_environment),
        "time_node": _safe(probe_time_node),
        "commands": _safe(probe_commands),
        "scene_warp": _safe(probe_scene_warp),
        "write_roundtrip": _safe(probe_write_roundtrip),
    }
    if path:
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
    _print_summary(report, path)
    return report


def _print_summary(report: dict, path: str):
    print("=== SyncBridge Maya probe ===")
    env = report["environment"]
    print("Maya", env.get("maya_version"), "| unit", env.get("time_unit"), "| PySide2", env.get("pyside2"))
    tn = report["time_node"]
    if isinstance(tn, dict) and "warp_attributes" in tn:
        print("time1 warp attributes:", sorted(tn["warp_attributes"]))
        print("animCurveTT nodes:", [c["node"] for c in tn["animCurveTT_nodes"]])
    sw = report["scene_warp"]
    if isinstance(sw, dict):
        if sw.get("found"):
            print("Scene Time Warp: %s -> %s, enabled=%s" % (sw["curve"], sw["plug"], sw["enabled"]))
            node = sw.get("node", {})
            print("  infinity query: pre=%s post=%s" % (node.get("pre_infinity"), node.get("post_infinity")))
            cal = sw.get("calibration") or sw.get("raw") or {}
            if "error" in cal:
                print("  read ERROR", cal["error"])
            else:
                print("  decode vs Maya:", cal["weight_scale"],
                      "max %.5f f" % cal["decode_vs_maya"]["max_error_frames"])
        else:
            print("Scene Time Warp:", sw.get("message") or sw.get("error"))
    for r in report["write_roundtrip"] if isinstance(report["write_roundtrip"], list) else []:
        if r.get("error"):
            print("  write %-20s %-14s ERROR %s" % (r["curve"], r["weight_scale"],
                                                  r["error"].strip().splitlines()[-1]))
        else:
            m = r["maya_vs_expected"]
            print("  write %-20s %-14s %s max %.5f f" % (r["curve"], r["weight_scale"],
                                                       "PASS" if m["passed"] else "FAIL",
                                                       m["max_error_frames"]))
    if path:
        print("full report:", path)
