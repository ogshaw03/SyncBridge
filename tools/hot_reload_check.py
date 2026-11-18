"""Check: switch to a newly installed version without restarting Maya (D-56; H-UPD-1, H-UPD-2, H-UPD-3).

    py -3 tools\\hot_reload_check.py [--maya 2023] [--scenario free|shown|undo|used]

Everything happens in a temporary folder; the real install, the user's Maya prefs, AE and the Start menu
are never touched (LOCALAPPDATA, MAYA_APP_DIR, -CepRoot and -ProgramsDir point into it).

1. install.ps1 installs this repository as version A (the running one).
2. mayapy (Qt offscreen) runs from that install: the panel, the guide plug-in, a Maya marker (which makes the
   view overlay node, D-55). Scenario "free": no frame; "shown": a frame shown as the panel does (outside the
   undo queue); "undo": a guide node made with createNode and deleted (only in the undo queue); "used": one
   made with createNode stays (in the scene and the undo queue).
3. While mayapy runs, install.ps1 installs version B (0.1.99, a changed guide plug-in) over it.
4. The panel shows the bar; the switch runs (hot_reload.switch, as the bar's button does).
5. The new modules run, the panel is new, the markers are followed again, the guide plug-in is reloaded with
   the frame and the overlay taken out and put back (free, shown) or kept with a note (undo, used: Maya refuses
   to unload it, H-UPD-3).

Prints "OK" / "NG" per check and "RESULT PASS" / "RESULT FAIL"; the full log and the panel's pictures go to
probe_results/hot_reload_<scenario>/.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
NEW_VERSION = "0.1.99"


# -- the driver (py -3) ---------------------------------------------------------------------------------
def _write_ps1(src, dst):
    """As the release build does: UTF-8 with BOM (PowerShell 5.1 and Japanese text), CRLF."""
    with open(src, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n").replace("\n", "\r\n")
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)


def make_payload(path, version=None):
    sys.path.insert(0, os.path.join(REPO, "packaging"))
    import build_release
    build_release.build_maya(path)
    os.makedirs(os.path.join(path, "ae"))
    with zipfile.ZipFile(os.path.join(path, "ae", "com.syncbridge.panel.zxp"), "w") as z:
        z.writestr("CSXS/manifest.xml", '<ExtensionManifest ExtensionBundleId="com.syncbridge.panel"/>')
    shutil.copy2(os.path.join(REPO, "version.json"), path)
    for name in ("install.ps1", "uninstall.ps1"):
        _write_ps1(os.path.join(REPO, "packaging", "installer", name), os.path.join(path, name))
    if version:
        init = os.path.join(path, "maya", "scripts", "syncbridge", "__init__.py")
        with open(init, encoding="utf-8") as f:
            text = f.read()
        import re
        text = re.sub(r'__version__ = "[^"]*"', '__version__ = "%s"' % version, text)
        with open(init, "w", encoding="utf-8") as f:
            f.write(text)
        with open(os.path.join(path, "version.json"), "w", encoding="utf-8") as f:
            json.dump({"version": version}, f)
        with open(os.path.join(path, "maya", "plug-ins", "syncbridge_guide.py"), "a", encoding="utf-8") as f:
            f.write("\n# changed by tools/hot_reload_check.py\n")


def install_command(work, payload):
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(payload, "install.ps1"),
            "-CepRoot", os.path.join(work, "cep"), "-ProgramsDir", os.path.join(work, "start"),
            "-MayaAppDir", os.path.join(work, "maya_app"), "-Quiet"]


def driver(argv):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--maya", default="2023")
    parser.add_argument("--scenario", default="free", choices=("free", "shown", "undo", "used"))
    args = parser.parse_args(argv)
    out = os.path.join(REPO, "probe_results", "hot_reload_%s" % args.scenario)
    shutil.rmtree(out, True)
    os.makedirs(out)
    work = tempfile.mkdtemp(prefix="sb_hot_reload_")
    try:
        os.makedirs(os.path.join(work, "maya_app", args.maya, "prefs"))
        os.makedirs(os.path.join(work, "Local"))
        payload_a, payload_b = os.path.join(work, "payload_a"), os.path.join(work, "payload_b")
        make_payload(payload_a)
        make_payload(payload_b, NEW_VERSION)
        env = dict(os.environ, LOCALAPPDATA=os.path.join(work, "Local"), MAYA_APP_DIR=os.path.join(work, "maya_app"),
                   QT_QPA_PLATFORM="offscreen", QT_QPA_FONTDIR="C:/Windows/Fonts")
        for key in ("PYTHONPATH", "PYTHONHOME", "SYNCBRIDGE_SERVER_EXE"):
            env.pop(key, None)
        first = subprocess.run(install_command(work, payload_a), env=env, capture_output=True, timeout=300)
        if first.returncode != 0:
            print(first.stdout.decode("mbcs", "replace"), first.stderr.decode("mbcs", "replace"))
            return 1
        mayapy = r"C:\Program Files\Autodesk\Maya%s\bin\mayapy.exe" % args.maya
        result = subprocess.run([mayapy, os.path.abspath(__file__), "--inner", work, payload_b, out, args.scenario],
                                env=env, capture_output=True, timeout=600)
        text = result.stdout.decode("mbcs", "replace") + "\n--- stderr\n" + result.stderr.decode("mbcs", "replace")
        with open(os.path.join(out, "log.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        for line in text.splitlines():
            if line.startswith(("OK ", "NG ", "RESULT", "NOTE ")):
                print(line.encode("cp932", "replace").decode("cp932"))
        return 0 if "RESULT PASS" in text else 1
    finally:
        shutil.rmtree(work, True)


# -- inside mayapy --------------------------------------------------------------------------------------
def inner(work, payload_b, out, scenario):
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PySide2 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])    # before Maya (CLAUDE.md)
    import maya.standalone
    maya.standalone.initialize()
    from maya import cmds
    import __main__

    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print("%s  %s  %s" % ("OK" if ok else "NG", name, detail))
        sys.stdout.flush()

    root = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "SyncBridge")
    sys.path.insert(0, os.path.join(root, "maya", "scripts"))
    import syncbridge
    old_version = syncbridge.__version__
    check("A is installed and runs from the install", syncbridge.__file__.startswith(root), syncbridge.__file__)

    cmds.loadPlugin(os.path.join(root, "maya", "plug-ins", "syncbridge_guide.py"))
    from syncbridge_maya import comp_guide, hot_reload, key_markers, maya_markers, ui
    if scenario == "shown":
        comp_guide.show_size(1920, 1080, "persp")                  # as the panel does: outside the undo queue
    elif scenario in ("undo", "used"):
        guide = cmds.createNode("syncBridgeCompGuide", name="SB_CHECK_GUIDEShape")      # in the undo queue
        cmds.connectAttr("perspShape.worldMatrix[0]", guide + ".cameraMatrix")
        if scenario == "undo":
            cmds.delete(cmds.listRelatives(guide, parent=True) or guide)   # in the undo queue only
    cmds.currentTime(10)
    maya_markers.add()
    maya_markers._run()                                            # executeDeferred does not run in mayapy
    check("the Maya marker makes the view overlay", bool(key_markers.overlays()), str(key_markers.overlays()))
    panel = ui.show()
    app.processEvents()
    check("no bar before the install", panel.check_installed() is None and not panel.update_bar.isVisible())

    # install B while this Maya runs (H-UPD-1)
    second = subprocess.run(install_command(work, payload_b), capture_output=True, timeout=300)
    detail = (second.stdout.decode("mbcs", "replace") + second.stderr.decode("mbcs", "replace")).strip()
    check("install.ps1 replaces the files while Maya runs (H-UPD-1)", second.returncode == 0, detail[-300:])
    print("NOTE installer message: " + detail.replace("\r", " ").replace("\n", " ")[:400])

    found = panel.check_installed()
    app.processEvents()
    panel.grab().save(os.path.join(out, "panel_bar.png"))
    check("the bar shows the new version", found == NEW_VERSION and panel.update_bar.isVisible(),
          panel.update_label.text())

    old_panel = panel
    ok = hot_reload.switch()
    app.processEvents()
    check("switch() succeeded", ok)
    import syncbridge as new_syncbridge
    check("the new modules run", new_syncbridge.__version__ == NEW_VERSION and new_syncbridge is not syncbridge,
          "%s -> %s" % (old_version, new_syncbridge.__version__))
    new_ui = sys.modules["syncbridge_maya.ui"]
    new_panel = new_ui._window
    check("a new panel of the new version", new_panel is not None and new_panel is not old_panel
          and NEW_VERSION in new_panel.windowTitle(), new_panel.windowTitle() if new_panel else "")
    try:
        old_visible = old_panel.isVisible()
    except RuntimeError:
        old_visible = False
    check("the old panel is closed", not old_visible)
    log = new_panel.log.toPlainText() if new_panel else ""
    print("NOTE panel log: " + log.replace("\n", " | "))
    check("the panel says it switched", (u"%s に切り替えました" % NEW_VERSION) in log)
    check("no bar after the switch", not new_panel.update_bar.isVisible() and new_panel.check_installed() is None)
    new_panel.grab().save(os.path.join(out, "panel_after.png"))

    state = getattr(__main__, "_syncbridge_maya_markers", {})
    check("the markers are followed again (new callbacks)", len(state.get("callbacks") or []) >= 2,
          str(len(state.get("callbacks") or [])))
    new_markers = sys.modules["syncbridge_maya.maya_markers"]
    check("the marker is still there", new_markers.frames() == [10.0], str(new_markers.frames()))

    guide_path = os.path.join(root, "maya", "plug-ins", "syncbridge_guide.py")
    digests = getattr(__main__, "_syncbridge_plugin_digests", {})
    loaded = cmds.pluginInfo("syncbridge_guide", q=True, loaded=True)
    new_hot = sys.modules["syncbridge_maya.hot_reload"]
    reloaded = digests.get("syncbridge_guide") == new_hot.file_digest(guide_path)
    new_markers_overlay = sys.modules["syncbridge_maya.key_markers"].overlays()
    new_guides = sys.modules["syncbridge_maya.comp_guide"].existing()
    if scenario in ("free", "shown", "used"):      # used: once taken out, only its creation is in the undo queue
        check("the changed guide plug-in is reloaded (the overlay and frames taken out and put back)",
              loaded and reloaded)
        check("no note about restarting Maya", u"前の版のまま" not in log)
    else:
        check("the guide plug-in in use stays loaded (old)", loaded and not reloaded)
        check("the panel says Maya must be restarted for it", u"前の版のまま" in log)
    check("the marker overlay is shown again", bool(new_markers_overlay), str(new_markers_overlay))
    if scenario in ("shown", "used"):
        check("the frame is shown again", len(new_guides) == 1, str(new_guides))
    # The undo queue still has the steps of the old version (the marker key, a createNode): undoing them all
    # must not crash Maya nor leave the overlay without its plug-in.
    undone = 0
    while undone < 20 and cmds.undoInfo(q=True, undoName=True):
        cmds.undo()
        undone += 1
    check("undoing the old steps after the switch works", True, "%d undone" % undone)
    cmds.currentTime(10)
    cmds.currentTime(11)
    check("the plug-in still draws after the undo (no error)", cmds.pluginInfo("syncbridge_guide", q=True, loaded=True))

    print("RESULT %s" % ("PASS" if all(results) else "FAIL"))
    sys.stdout.flush()
    # Leaving Maya with our widgets open crashed at exit and wrote a recovery scene to %TEMP%: close first
    for w in QtWidgets.QApplication.topLevelWidgets():
        w.close()
    app.processEvents()
    cmds.file(new=True, force=True)
    maya.standalone.uninitialize()
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--inner":
        try:
            inner(*sys.argv[2:6])
        except Exception:
            import traceback
            traceback.print_exc()
            print("RESULT FAIL")
            sys.stdout.flush()
            os._exit(1)
    else:
        sys.exit(driver(sys.argv[1:]))
