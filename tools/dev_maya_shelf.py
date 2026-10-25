"""Development: drag this file onto a Maya viewport to add a "SB Dev" button to the current shelf.

The button opens the SyncBridge panel from THIS repository and reloads its code every time
(syncbridge* modules are dropped from sys.modules first, the open SyncBridge windows are closed, the
layer stack plug-in is unloaded after the views using it are put back to Viewport 2.0),
so a change in the repository is picked up without restarting Maya. The release's button
(drag_to_maya_SyncBridge.py / Install.bat) is left alone.

The hub is started from the repository's .venv (client/launcher.py). A hub that is already running
keeps answering: stop it from the monitor after changing server code.
"""
from __future__ import annotations

import os

BUTTON_LABEL = "SB Dev"
BUTTON_TAG = "SyncBridgeDev"

COMMAND = u"""import sys
p = r'{scripts}'
if p not in sys.path:
    sys.path.insert(0, p)
try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets
for w in QtWidgets.QApplication.topLevelWidgets():
    if w.objectName() in ('SyncBridgePanel', 'SyncBridgeLayerMap', 'SyncBridgeViewer'):
        w.close()
        w.deleteLater()
from maya import cmds
for p in cmds.getPanel(type='modelPanel') or []:
    try:
        if cmds.modelEditor(p, q=True, rendererOverrideName=True) == 'SyncBridgeLayerStack':
            cmds.modelEditor(p, e=True, rendererOverrideName='')
    except RuntimeError:
        pass
if cmds.pluginInfo('syncbridge_layer_stack.py', q=True, loaded=True):
    cmds.unloadPlugin('syncbridge_layer_stack.py')   # loaded again with the new code when used
for name in [n for n in sys.modules if n.split('.')[0] in ('syncbridge', 'syncbridge_maya')]:
    del sys.modules[name]
import syncbridge_maya.ui
syncbridge_maya.ui.show()
print('SyncBridge (dev): reloaded from ' + p)
"""


def _repo_scripts():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "maya_plugin", "scripts")).replace("\\", "/")


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
                     sourceType="python", command=COMMAND.format(scripts=scripts))
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
