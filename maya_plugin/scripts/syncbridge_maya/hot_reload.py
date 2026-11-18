"""Switch to a newly installed version without restarting Maya (D-56).

The installer (packaging/installer/install.ps1) replaces the files while Maya runs (H-UPD-1) and writes
install.json last. The panel watches it (`pending()`) and offers "切り替える", which calls `switch()`:

  1. the running (old) code takes down what it made (`_take_down`): its windows, the connection, the time
     sync and marker callbacks, the layer stack plug-in, and the guide plug-in when its file changed and
     no node uses it
  2. the syncbridge* modules are dropped from sys.modules
  3. the new code's `start_after_reload(state)` puts things back: the panel, the viewer and the layer map
     when they were open, the connection and the time slider sync

`state` is the contract between versions: a dict of plain values. A newer `start_after_reload` must accept
the state of an older switch (a missing key = its default), and an older one ignores keys it does not know.
Each version takes down only what it made itself, so the old code's `_take_down` is always the right one.

    from syncbridge_maya import hot_reload
    hot_reload.pending()      # "0.1.21" when another version is installed than the one running
    hot_reload.switch()
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import traceback
from typing import List, Optional

from maya import cmds

STATE_VERSION = 1
WINDOWS = (("panel", "SyncBridgePanel"), ("layer_map", "SyncBridgeLayerMap"), ("viewer", "SyncBridgeViewer"))
PACKAGES = ("syncbridge", "syncbridge_maya")
PLUGIN_DIGESTS_KEY = "_syncbridge_plugin_digests"   # __main__: {file name: sha256 of the file when loaded}
GUIDE_PLUGIN = "syncbridge_guide"
LAYER_STACK_PLUGIN = "syncbridge_layer_stack"
LAYER_STACK_OVERRIDE = "SyncBridgeLayerStack"


# -- is another version installed? ----------------------------------------------------------------------
def install_root() -> Optional[str]:
    """The installed SyncBridge folder this code runs from (<root>/maya/scripts/syncbridge_maya), or None
    (the repository while developing: no install.json)."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return root if os.path.isfile(os.path.join(root, "install.json")) else None


def installed_version(root: Optional[str] = None) -> Optional[str]:
    root = root or install_root()
    if not root:
        return None
    try:
        with open(os.path.join(root, "install.json"), encoding="utf-8-sig") as f:
            return str(json.load(f).get("version") or "") or None
    except (OSError, ValueError, AttributeError):        # being written by the installer
        return None


def pending() -> Optional[str]:
    """The installed version when it is not the running one."""
    from syncbridge import __version__
    found = installed_version()
    return found if found and found != __version__ else None


# -- the plug-ins ---------------------------------------------------------------------------------------
def file_digest(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _plugin_path(name: str) -> Optional[str]:
    try:
        if cmds.pluginInfo(name, q=True, loaded=True):
            return cmds.pluginInfo(name, q=True, path=True)
    except RuntimeError:
        pass
    return None


def _plugin_changed(name: str, path: str) -> bool:
    """The file differs from the loaded one. The plug-ins remember their digest when loaded (0.1.21 on);
    one loaded by an older version remembers none: changed."""
    import __main__
    loaded = (getattr(__main__, PLUGIN_DIGESTS_KEY, None) or {}).get(name)
    return loaded is None or loaded != file_digest(path)


def _unload_layer_stack(notes: List[str]) -> None:
    """The views drawing with the layer stack go back to Viewport 2.0 first; the viewer loads it again."""
    for panel in cmds.getPanel(type="modelPanel") or []:
        try:
            if cmds.modelEditor(panel, q=True, rendererOverrideName=True) == LAYER_STACK_OVERRIDE:
                cmds.modelEditor(panel, e=True, rendererOverrideName="")
        except RuntimeError:
            pass
    if _plugin_path(LAYER_STACK_PLUGIN):
        try:
            cmds.unloadPlugin(LAYER_STACK_PLUGIN + ".py")
        except RuntimeError as exc:
            notes.append(u"レイヤーを重ねて描くプラグインを入れ替えられませんでした（%s）。Maya を開き直すと新しくなります。" % exc)


def _unload_guide(state: dict) -> Optional[str]:
    """Unload the guide plug-in when its file changed; returns its path to load again after the switch.
    Maya refuses while a guide or key marker node is in the scene or in the undo queue (H-UPD-3). The frames and
    the marker overlay are display only (made outside the undo queue, D-16 / D-18): they are taken out as for a
    save and put back by the new version (state "guides" / "marker_overlay"). A node in the undo queue keeps
    the old plug-in (the undo queue is never flushed for this)."""
    notes = state["notes"]
    path = _plugin_path(GUIDE_PLUGIN)
    if not path or not _plugin_changed(GUIDE_PLUGIN, path):
        return None
    from . import comp_guide, key_markers
    guides, overlay = [], False
    try:
        guides = comp_guide.take_out_for_save()
        overlay = key_markers.take_out_for_save()
    except Exception as exc:
        notes.append(u"AE のコンプの枠とマーカーを外せませんでした: %s" % exc)
    try:
        cmds.unloadPlugin(GUIDE_PLUGIN + ".py")
    except RuntimeError:
        try:
            comp_guide.put_back_after_save(guides)
            key_markers.put_back_after_save(overlay)
        except Exception as exc:
            notes.append(u"AE のコンプの枠とマーカーを戻せませんでした: %s" % exc)
        notes.append(u"AE のコンプの枠とマーカーを描くプラグインは、取り消しの履歴で使っているため、"
                     u"前の版のままです。Maya を開き直すと新しくなります。")
        return None
    state["guides"], state["marker_overlay"] = guides, overlay
    return path


# -- the switch -----------------------------------------------------------------------------------------
def _open_windows():
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PySide2 import QtWidgets
    app = QtWidgets.QApplication.instance()
    found = []
    if app is None:
        return found
    names = dict((name, key) for key, name in WINDOWS)
    for w in app.topLevelWidgets():
        try:
            if w.objectName() in names and w.isVisible():
                found.append((names[w.objectName()], w))
        except RuntimeError:                     # deleted by Qt meanwhile
            pass
    return found


def _geometry(widget) -> Optional[List[int]]:
    try:
        g = widget.geometry()
        return [g.x(), g.y(), g.width(), g.height()]
    except RuntimeError:
        return None


def _place(widget, geometry) -> None:
    """Put a reopened window where the user had it (the new one would open at its default place)."""
    if widget is None or not geometry or len(geometry) != 4:
        return
    try:
        widget.setGeometry(*[int(v) for v in geometry])
        widget.raise_()
    except (RuntimeError, TypeError, ValueError):
        pass


def _close(widgets) -> None:
    # Find first, then close: closing the viewer deletes its model panel's menus (dev_reload.py).
    for _key, w in widgets:
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass


def _take_down() -> dict:
    """Take down what this version made; returns the state for the new version's start_after_reload."""
    from syncbridge import __version__
    from . import maya_markers, service

    notes: List[str] = []
    windows = _open_windows()
    state = {
        "state_version": STATE_VERSION,
        "from_version": __version__,
        "windows": [key for key, _w in windows],
        "geometry": dict((key, _geometry(w)) for key, w in windows),
        "connected": bool(service.is_connected()),
        "time_sync": dict(service.time_sync_state()),
        "notes": notes,
        "load_plugins": [],
        "guides": [],                 # comp_guide.take_out_for_save(): plain dicts, put back by the new version
        "marker_overlay": False,
    }
    _close(windows)
    for step in (service.shutdown, maya_markers.unwatch):
        try:
            step()
        except Exception as exc:                 # go on: the new version is what matters now
            notes.append(u"前の版の後片付けで問題がありました: %s" % exc)
    _unload_layer_stack(notes)
    guide = _unload_guide(state)
    if guide:
        state["load_plugins"].append(guide)
    return state


def _drop_modules() -> None:
    for name in [n for n in sys.modules if n.split(".")[0] in PACKAGES]:
        del sys.modules[name]
    importlib.invalidate_caches()        # the installer replaced the folders: new files must be found


def switch() -> bool:
    """Take down this version and start the installed one. Call it outside the panel's own slots (the panel
    is closed here): maya.utils.executeDeferred(hot_reload.switch). Returns False when the new version could
    not start (the reason is printed; Maya has to be restarted then)."""
    state = _take_down()
    _drop_modules()
    for path in state.get("load_plugins") or []:
        try:
            cmds.loadPlugin(path, quiet=True)
        except RuntimeError as exc:
            state["notes"].append(u"プラグイン %s を読み込めませんでした: %s" % (os.path.basename(path), exc))
    try:
        new = importlib.import_module("syncbridge_maya.hot_reload")
        start = getattr(new, "start_after_reload", None)
        if start is not None:
            start(state)
        else:                                    # a version without this module (older than 0.1.21)
            importlib.import_module("syncbridge_maya.ui").show()
    except Exception:
        traceback.print_exc()
        cmds.warning(u"SyncBridge: 新しい版を読み込めませんでした（スクリプトエディタに理由）。Maya を開き直してください。")
        return False
    return True


def start_after_reload(state: dict) -> None:
    """The new version's side of `switch` (run with the new modules)."""
    from syncbridge import __version__
    from . import service, ui

    panel = ui.show()
    panel.write(u"SyncBridge %s に切り替えました（%s から。Maya は開いたままです）。" % (
        __version__, state.get("from_version") or u"前の版"))
    for note in state.get("notes") or []:
        panel.write(note)
    from . import comp_guide, key_markers
    try:                                         # taken out to reload the guide plug-in (_unload_guide)
        comp_guide.put_back_after_save(list(state.get("guides") or []))
        key_markers.put_back_after_save(bool(state.get("marker_overlay")))
    except Exception as exc:
        panel.write(u"AE のコンプの枠とマーカーを戻せませんでした: %s" % exc)
    if state.get("connected"):
        panel.toggle_connection()                # the installer stopped the server: this starts the new one
        time_sync = state.get("time_sync") or {}
        if service.is_connected() and time_sync.get("enabled"):
            try:
                service.set_time_sync(True, bool(time_sync.get("follow_playback")))
            except Exception as exc:
                panel.write(u"タイムスライダーの同期を戻せませんでした: %s" % exc)
        panel.refresh()
    windows = state.get("windows") or []
    geometry = state.get("geometry") or {}
    if "layer_map" in windows:
        from . import layer_map_window
        _place(layer_map_window.show(), geometry.get("layer_map"))
    if "viewer" in windows:
        from . import viewer_window
        _place(viewer_window.show(), geometry.get("viewer"))
    if "panel" in windows:
        _place(panel, geometry.get("panel"))       # last: on top, where the user presses things
