"""SyncBridge: drag this file onto a Maya viewport to add the SyncBridge button to the shelf.

Maya calls onMayaDroppedPythonFile() of a .py dropped on the viewport (H-MY-17).
It also works when run from the Script Editor (File > Source Script / exec).

Layout (release install and repository):
    <maya folder>/drag_to_maya_SyncBridge.py     (this file)
    <maya folder>/scripts/syncbridge_maya, scripts/syncbridge
    <maya folder>/icons/syncbridge_shelf.png
The installed copy (%LOCALAPPDATA%/Programs/SyncBridge/maya) is preferred so the
button keeps working after the downloaded zip is deleted.

The button adds the scripts folder to sys.path and opens the SyncBridge panel.
Run again to update the button (an existing SyncBridge button is replaced).
"""
from __future__ import annotations

import os
import sys

BUTTON_LABEL = "SyncBridge"
BUTTON_TAG = "SyncBridge"          # docTag used to find our button again


def _candidate_roots():
    roots = []
    base = os.environ.get("LOCALAPPDATA")
    if base:
        roots.append(os.path.join(base, "Programs", "SyncBridge", "maya"))
    try:
        roots.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:   # __file__ may be undefined depending on how Maya runs the file
        pass
    return roots


def find_maya_folder():
    """The folder that contains scripts/syncbridge_maya, or None."""
    for root in _candidate_roots():
        if os.path.isfile(os.path.join(root, "scripts", "syncbridge_maya", "ui.py")):
            return os.path.normpath(root)
    return None


def button_command(scripts_dir):
    return ("import sys\n"
            "p = r'%s'\n"
            "if p not in sys.path:\n"
            "    sys.path.insert(0, p)\n"
            "import syncbridge_maya.ui\n"
            "syncbridge_maya.ui.show()\n" % scripts_dir)


def install():
    from maya import cmds, mel

    folder = find_maya_folder()
    if folder is None:
        cmds.confirmDialog(
            title="SyncBridge",
            message=u"SyncBridge のファイルが見つかりませんでした。\n"
                    u"先に配布フォルダの Install.bat を実行してから、もう一度ドラッグしてください。",
            button=["OK"])
        return False
    scripts_dir = os.path.join(folder, "scripts")
    icon = os.path.join(folder, "icons", "syncbridge_shelf.png").replace("\\", "/")

    # The panel must import before we offer a button for it.
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import syncbridge_maya.ui  # noqa: F401

    shelf_top = mel.eval("$_sb_tmp = $gShelfTopLevel")
    shelf = cmds.tabLayout(shelf_top, q=True, selectTab=True)
    for button in cmds.shelfLayout(shelf, q=True, childArray=True) or []:
        if cmds.objectTypeUI(button) == "shelfButton" and \
                cmds.shelfButton(button, q=True, docTag=True) == BUTTON_TAG:
            cmds.deleteUI(button)
    cmds.shelfButton(
        parent=shelf, label=BUTTON_LABEL, annotation=u"SyncBridge パネルを開く（Maya ⇔ After Effects タイムワープ転送）",
        image=icon if os.path.isfile(icon) else "pythonFamily.png", docTag=BUTTON_TAG,
        sourceType="python", command=button_command(scripts_dir))
    mel.eval("saveAllShelves $gShelfTopLevel")

    cmds.confirmDialog(
        title="SyncBridge",
        message=u"シェルフ「%s」に SyncBridge のボタンを追加しました。\n"
                u"ボタンを押すとパネルが開きます。" % shelf,
        button=["OK"])
    print("SyncBridge: shelf button added to '%s' (scripts: %s)" % (shelf, scripts_dir))
    return True


_done = []   # Maya may run this file as __main__ and also call onMayaDroppedPythonFile


def _install_once():
    if not _done:
        _done.append(True)
        install()


def onMayaDroppedPythonFile(*args):
    _install_once()


if __name__ == "__main__":
    _install_once()
