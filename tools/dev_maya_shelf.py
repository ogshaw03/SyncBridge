"""Development: drag this file onto a Maya viewport to add a "SB Dev" button to the current shelf.

The button opens the SyncBridge panel from THIS repository and reloads its code every time
(syncbridge* modules are dropped from sys.modules first, the open SyncBridge windows are closed, the
layer stack plug-in is unloaded after the views using it are put back to Viewport 2.0),
so a change in the repository is picked up without restarting Maya. The work is in tools/dev_reload.py,
which the button runs from the repository (a change there needs no new button). The release's button
(drag_to_maya_SyncBridge.py / Install.bat) is left alone.

The hub is started from the repository's .venv (client/launcher.py). A hub that is already running
keeps answering: stop it from the monitor after changing server code.
"""
from __future__ import annotations

import os

BUTTON_LABEL = "SB Dev"
BUTTON_TAG = "SyncBridgeDev"

COMMAND = u"""exec(compile(open(r'{reload}', encoding='utf-8').read(), r'{reload}', 'exec'), dict(__file__=r'{reload}', __name__='__sb_dev__'))
"""   # the work is in tools/dev_reload.py: changing it needs no new button


def _repo_scripts():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "maya_plugin", "scripts")).replace("\\", "/")


def _reload_script():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev_reload.py").replace("\\", "/")


def install():
    from maya import cmds, mel

    scripts = _repo_scripts()
    if not os.path.isfile(os.path.join(scripts, "syncbridge_maya", "ui.py")):
        cmds.confirmDialog(title="SyncBridge", message=u"リポジトリの maya_plugin/scripts が見つかりません: %s" % scripts,
                           button=["OK"])
        return False
    icon = os.path.join(os.path.dirname(scripts), "icons", "syncbridge_shelf.png").replace("\\", "/")
    shelf = cmds.tabLayout(mel.eval("$_sb_tmp = $gShelfTopLevel"), q=True, selectTab=True)
    for button in cmds.shelfLayout(shelf, q=True, childArray=True) or []:
        if cmds.objectTypeUI(button) == "shelfButton" and \
                cmds.shelfButton(button, q=True, docTag=True) == BUTTON_TAG:
            cmds.deleteUI(button)
    cmds.shelfButton(parent=shelf, label=BUTTON_LABEL, imageOverlayLabel="Dev",
                     annotation=u"SyncBridge（開発用）: リポジトリの最新のコードを読み直してパネルを開く",
                     image=icon if os.path.isfile(icon) else "pythonFamily.png", docTag=BUTTON_TAG,
                     sourceType="python", command=COMMAND.format(reload=_reload_script()))
    mel.eval("saveAllShelves $gShelfTopLevel")
    cmds.confirmDialog(title="SyncBridge",
                       message=u"シェルフ「%s」に開発用のボタン（Dev）を追加しました。\n"
                               u"押すたびにリポジトリの最新のコードでパネルを開き直します。" % shelf,
                       button=["OK"])
    print("SyncBridge (dev): shelf button added to '%s' (scripts: %s)" % (shelf, scripts))
    return True


_done = []


def onMayaDroppedPythonFile(*args):
    if not _done:
        _done.append(True)
        install()


if __name__ == "__main__":
    onMayaDroppedPythonFile()
