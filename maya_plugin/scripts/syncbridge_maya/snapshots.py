"""Save / restore / retime the Scene Time Warp (so a tuned time warp is never lost).

    save(name)                      the current Scene Time Warp -> <userAppDir>/SyncBridge/snapshots/<name>.json
    entries()                       saved snapshots and the automatic backups (newest first)
    restore(path, new_range=None)   write a saved warp back into the current Scene Time Warp,
                                    optionally stretched to new_range (scene frames)
    retime_current(start, end)      stretch / move the current warp along scene time

Files are "maya.timewarp.export" envelopes, the same format as the automatic
backups written before every apply, so backups can be restored too. Writing
goes through exchange.apply_envelope: confirmation, backup, one undo, readback.
Must run on Maya's main thread.
"""
from __future__ import annotations

import datetime
import os
import re
from typing import List, Optional, Tuple

from maya import cmds

from syncbridge.core import envelope, warp_edit
from . import anim_curve, exchange

KIND_SNAPSHOT = "snapshot"
KIND_BACKUP = "backup"


def snapshot_dir() -> str:
    d = os.path.join(cmds.internalVar(userAppDir=True), "SyncBridge", "snapshots")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def _safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", name.strip()).strip("._")
    return name[:80]


def default_name() -> str:
    scene = os.path.splitext(os.path.basename(cmds.file(q=True, sn=True) or "untitled"))[0]
    return "%s_%s" % (scene, datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))


def save(name: Optional[str] = None) -> str:
    """Save the current Scene Time Warp. Returns the file path."""
    env = exchange.build_export(allow_missing=True)
    if env["data"]["native"] is None:
        raise RuntimeError(u"このシーンには Scene Time Warp がありません。")
    base = _safe_name(name or "") or default_name()
    folder = snapshot_dir()
    path = os.path.join(folder, base + ".json")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, "%s_%d.json" % (base, n))
        n += 1
    env["data"]["snapshot_name"] = os.path.splitext(os.path.basename(path))[0]
    envelope.save(path, env)
    print("SyncBridge: saved the Scene Time Warp to %s" % path)
    return path


def _describe(path: str, kind: str) -> Optional[dict]:
    try:
        env = envelope.load(path, "maya.timewarp.export")
    except (OSError, ValueError):
        return None
    data = env["data"]
    native = data.get("native")
    if not native or not native.get("keys"):
        return None
    return {
        "path": path,
        "kind": kind,
        "name": data.get("snapshot_name") or os.path.splitext(os.path.basename(path))[0],
        "modified": datetime.datetime.fromtimestamp(os.path.getmtime(path)),
        "keys": len(native["keys"]),
        "frames": warp_edit.key_range(native),
        "values": warp_edit.value_range(native),
        "fps": native["fps"],
        "scene": os.path.basename((env.get("app") or {}).get("scene") or ""),
    }


def entries() -> List[dict]:
    """Snapshots and automatic backups, newest first."""
    found = []
    for folder, kind in ((snapshot_dir(), KIND_SNAPSHOT), (exchange.backup_dir(), KIND_BACKUP)):
        for name in os.listdir(folder):
            if name.lower().endswith(".json"):
                entry = _describe(os.path.join(folder, name), kind)
                if entry:
                    found.append(entry)
    found.sort(key=lambda e: e["modified"], reverse=True)
    return found


def _apply_native(native: dict, origin: str, confirm: bool) -> dict:
    apply_env = envelope.make("maya.timewarp.apply", {"mode": "editable", "native": native}, "maya")
    return exchange.apply_envelope(apply_env, confirm=confirm, origin=origin)


def restore(path: str, new_range: Optional[Tuple[float, float]] = None, confirm: bool = True) -> dict:
    """Write a saved warp into the current Scene Time Warp (converted to the scene fps)."""
    env = envelope.load(path, "maya.timewarp.export")
    native = env["data"]["native"]
    if not native:
        raise RuntimeError(u"このファイルにはタイムワープが入っていません: %s" % path)
    native = warp_edit.to_scene_fps(native, anim_curve.scene_fps().to_json())
    label = env["data"].get("snapshot_name") or os.path.splitext(os.path.basename(path))[0]
    origin = u"保存したタイムワープ「%s」" % label
    if new_range is not None:
        native = warp_edit.retime(native, new_range[0], new_range[1])
        origin += u"（%g〜%g フレームに合わせたもの）" % new_range
    return _apply_native(native, origin, confirm)


def retime_current(new_start: float, new_end: float, confirm: bool = True) -> dict:
    """Stretch / move the current Scene Time Warp so its keys span new_start..new_end."""
    env = exchange.build_export(allow_missing=True)
    native = env["data"]["native"]
    if not native:
        raise RuntimeError(u"このシーンには Scene Time Warp がありません。")
    old = warp_edit.key_range(native)
    retimed = warp_edit.retime(native, new_start, new_end)
    origin = u"範囲の変更（%g〜%g → %g〜%g フレーム）" % (old[0], old[1], new_start, new_end)
    return _apply_native(retimed, origin, confirm)


def current_key_range() -> Optional[Tuple[float, float]]:
    env = exchange.build_export(allow_missing=True)
    native = env["data"]["native"]
    return warp_edit.key_range(native) if native else None
