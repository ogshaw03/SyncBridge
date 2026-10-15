"""SyncBridge command line (Phase 0 file-based transfer hub).

    python -m syncbridge.cli maya2ae  maya_export.json -o ae_apply.json [--ae-export ae_export.json]
    python -m syncbridge.cli ae2maya  ae_export.json   -o maya_apply.json --maya-fps 24
    python -m syncbridge.cli readback apply.json export_after_apply.json
    python -m syncbridge.cli probe-vectors -o ae_probe_vectors.json
    python -m syncbridge.cli verify-ae-probe ae_probe_results.json
    python -m syncbridge.cli selftest

Run with `src` on PYTHONPATH (or `pip install -e .`).
"""
from __future__ import annotations

import argparse
import json
import sys

from .core import ae_codec, envelope, maya_codec, testcurves, transfer
from .core.mapping import MappingContext
from .core.timebase import FrameRate
from .core.validation import DEFAULT_TOLERANCE_FRAMES, compare_samples


def _add_mapping_args(p):
    g = p.add_argument_group("time mapping (docs/SPEC.md 3.3)")
    g.add_argument("--origin", type=float, default=None,
                   help="sets both --maya-in-origin and --maya-out-origin (e.g. render start frame)")
    g.add_argument("--maya-in-origin", type=float, default=None,
                   help="Maya scene frame that maps to the comp time --comp-offset")
    g.add_argument("--maya-out-origin", type=float, default=None,
                   help="warped Maya frame that maps to source time --source-offset")
    g.add_argument("--comp-offset", type=float, default=None,
                   help="AE comp seconds for --maya-in-origin (default: layer startTime if known, else 0)")
    g.add_argument("--source-offset", type=float, default=0.0, help="AE source seconds for --maya-out-origin")
    g.add_argument("--source-scale", type=float, default=1.0,
                   help="AE source seconds per Maya warped second (footage interpretation)")
    p.add_argument("--mode", choices=transfer.MODES, default=transfer.EDITABLE)
    p.add_argument("--tol", type=float, default=DEFAULT_TOLERANCE_FRAMES, help="tolerance in frames")
    p.add_argument("--key-subdivision", type=int, default=1,
                   help="Precision mode: key candidates per frame (1 = whole frames)")


def _ctx(args, maya_fps, layer_start=None) -> MappingContext:
    origin = args.origin if args.origin is not None else 0.0
    comp_offset = args.comp_offset
    if comp_offset is None:
        comp_offset = layer_start if layer_start is not None else 0.0
    return MappingContext(
        maya_fps=FrameRate(maya_fps).to_json(),
        maya_input_origin_frame=args.maya_in_origin if args.maya_in_origin is not None else origin,
        maya_output_origin_frame=args.maya_out_origin if args.maya_out_origin is not None else origin,
        ae_comp_time_offset=comp_offset,
        ae_source_time_offset=args.source_offset,
        source_time_scale=args.source_scale,
    )


def cmd_maya2ae(args) -> int:
    data = envelope.load(args.input, "maya.timewarp.export")["data"]
    native = data["native"]
    target_fps = native["fps"]
    layer_start = None
    if args.ae_export:
        ae = envelope.load(args.ae_export, "ae.timeremap.export")["data"]
        target_fps = ae["comp"]["frameRate"]
        layer_start = ae["layer"]["startTime"]
    ctx = _ctx(args, native["fps"], layer_start)
    result = transfer.maya_to_ae(native, ctx, args.mode, args.tol, target_fps,
                                 data.get("samples"), args.key_subdivision)
    out = envelope.make("ae.timeremap.apply", {
        "mode": args.mode,
        "context": ctx.to_json(),
        "comp_fps": FrameRate(target_fps).to_json(),
        "keys": result.native,
        "report": result.to_json(),
    })
    envelope.save(args.output, out)
    _print_result(result)
    return 0 if result.passed else 2


def cmd_ae2maya(args) -> int:
    data = envelope.load(args.input, "ae.timeremap.export")["data"]
    maya_fps = args.maya_fps
    if args.maya_export:
        maya_fps = envelope.load(args.maya_export, "maya.timewarp.export")["data"]["scene"]["fps"]
    if maya_fps is None:
        print("error: --maya-fps or --maya-export is required", file=sys.stderr)
        return 1
    ctx = _ctx(args, maya_fps, data["layer"]["startTime"])
    result = transfer.ae_to_maya(data["keys"], ctx, args.mode, args.tol,
                                 data.get("samples"), args.key_subdivision)
    out = envelope.make("maya.timewarp.apply", {
        "mode": args.mode,
        "context": ctx.to_json(),
        "native": result.native,
        "report": result.to_json(),
    })
    envelope.save(args.output, out)
    _print_result(result)
    return 0 if result.passed else 2


def cmd_readback(args) -> int:
    """Compare what the target app evaluates after apply with what was sent."""
    with open(args.apply, encoding="utf-8") as f:
        apply_env = json.load(f)
    data = envelope.check(apply_env)
    kind = apply_env["kind"]
    if kind == "ae.timeremap.apply":
        after = envelope.load(args.after, "ae.timeremap.export")["data"]
        expected = ae_codec.decode(data["keys"])
        fps = data["comp_fps"]
        times, values = after["samples"]["times"], after["samples"]["values"]
    elif kind == "maya.timewarp.apply":
        after = envelope.load(args.after, "maya.timewarp.export")["data"]
        expected = maya_codec.decode(data["native"])
        fps = data["native"]["fps"]
        spf = FrameRate(fps).frame_duration
        times = [t * spf for t in after["samples"]["times"]]
        values = [v * spf for v in after["samples"]["values"]]
    else:
        print("error: %s is not an apply file" % args.apply, file=sys.stderr)
        return 1
    lo, hi = expected.domain
    pairs = [(t, v) for t, v in zip(times, values) if lo <= t <= hi]
    report = compare_samples([p[0] for p in pairs], [p[1] for p in pairs],
                             expected.evaluate, fps, args.tol)
    print("readback:", report.summary())
    for t, err in report.exceedances[:10]:
        print("  t=%.5f s  error=%.5f f" % (t, err))
    return 0 if report.passed else 2


def cmd_probe_vectors(args) -> int:
    vectors = []
    for name, make_curve in testcurves.PROBE_CURVES.items():
        report = ae_codec.EncodeReport()
        vectors.append({"name": name, "keys": ae_codec.encode(make_curve(), report),
                        "warnings": report.warnings})
    out = envelope.make("ae.probe.vectors", {
        "comp_fps": FrameRate(args.fps).to_json(),
        "sample_oversample": args.oversample,
        "vectors": vectors,
    })
    envelope.save(args.output, out)
    print("wrote %d probe vectors to %s" % (len(vectors), args.output))
    return 0


def cmd_verify_ae_probe(args) -> int:
    """Check hypotheses H-AE-* using samples AE evaluated for the probe vectors."""
    data = envelope.load(args.input, "ae.probe.results")["data"]
    fps = data["comp_fps"]
    ok = True
    print("%-22s %-48s %s" % ("vector", "sent keys vs AE valueAtTime", "AE-read keys vs AE"))
    for r in data["results"]:
        if r.get("error"):
            ok = False
            print("%-22s ERROR %s" % (r["name"], r["error"]))
            continue
        sent = ae_codec.decode(r["sentKeys"])
        read = ae_codec.decode(r["readKeys"])
        rep_sent = compare_samples(r["times"], r["values"], sent.evaluate, fps, args.tol)
        rep_read = compare_samples(r["times"], r["values"], read.evaluate, fps, args.tol)
        ok = ok and rep_sent.passed and rep_read.passed
        print("%-22s %-48s %s" % (r["name"], _short(rep_sent), _short(rep_read)))
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


def cmd_selftest(args) -> int:
    """Round-trip every reference curve through both directions and modes (no DCC)."""
    fps = FrameRate(args.fps)
    ok = True
    print("%-22s %-10s %-9s %-44s %s" % ("curve", "mode", "direction", "conversion", "notes"))
    for name, make_curve in testcurves.CURVES.items():
        curve_s = make_curve()
        maya_native = maya_codec.encode(curve_s, fps)
        ctx = MappingContext(maya_fps=fps.to_json(), maya_input_origin_frame=1001,
                             maya_output_origin_frame=1001, ae_comp_time_offset=0.0)
        for mode in transfer.MODES:
            to_ae = transfer.maya_to_ae(maya_native, ctx, mode, args.tol, fps.to_json())
            to_maya = transfer.ae_to_maya(to_ae.native, ctx, mode, args.tol)
            for direction, res in (("maya>ae", to_ae), ("ae>maya", to_maya)):
                ok = ok and res.passed
                print("%-22s %-10s %-9s %-44s %s" % (name, mode, direction, _short(res.conversion),
                                                     "; ".join(res.warnings)[:60]))
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


def _short(report) -> str:
    return "%s max=%.5f f" % ("PASS" if report.passed else "FAIL", report.max_error_frames)


def _print_result(result: transfer.TransferResult):
    print("mode:", result.mode, "->", result.target_app)
    if result.source_fidelity is not None:
        print("source fidelity:", result.source_fidelity.summary())
    print("conversion     :", result.conversion.summary())
    print("keys emitted   :", len(result.curve.keys))
    for w in result.warnings:
        print("warning:", w)
    if result.unreachable:
        print("tolerance not reachable on the key grid in %d interval(s); "
              "raise --key-subdivision" % len(result.unreachable))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="syncbridge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("maya2ae", help="Maya export -> AE apply payload")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--ae-export", help="AE export of the target layer (comp fps, layer start)")
    _add_mapping_args(p)
    p.set_defaults(func=cmd_maya2ae)

    p = sub.add_parser("ae2maya", help="AE export -> Maya apply payload")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--maya-fps", help="Maya scene fps, e.g. 24 or 24000/1001")
    p.add_argument("--maya-export", help="Maya export file to take the scene fps from")
    _add_mapping_args(p)
    p.set_defaults(func=cmd_ae2maya)

    p = sub.add_parser("readback", help="verify the target app evaluates what was applied")
    p.add_argument("apply")
    p.add_argument("after")
    p.add_argument("--tol", type=float, default=DEFAULT_TOLERANCE_FRAMES)
    p.set_defaults(func=cmd_readback)

    p = sub.add_parser("probe-vectors", help="write AE probe test vectors")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--fps", default="24")
    p.add_argument("--oversample", type=int, default=8)
    p.set_defaults(func=cmd_probe_vectors)

    p = sub.add_parser("verify-ae-probe", help="evaluate AE probe results")
    p.add_argument("input")
    p.add_argument("--tol", type=float, default=0.01)
    p.set_defaults(func=cmd_verify_ae_probe)

    p = sub.add_parser("selftest", help="offline round-trip of all reference curves")
    p.add_argument("--fps", default="24")
    p.add_argument("--tol", type=float, default=DEFAULT_TOLERANCE_FRAMES)
    p.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
