// SyncBridge for After Effects - Phase 0 file-based Time Remap transfer.
//
// File > Scripts > Run Script File... with one layer selected in the active comp.
//   Export : Time Remap keys + AE-evaluated samples -> JSON ("ae.timeremap.export")
//   Apply  : JSON from the CLI ("ae.timeremap.apply") -> Time Remap keys
// Apply asks for confirmation, writes a JSON backup of the current keys,
// runs in one undo group, and writes "<apply file>_after.json" for
// `python -m syncbridge.cli readback <apply> <after>`.

#include "syncbridge_ae_lib.jsxinc"

(function () {
    function doExport(comp, layer) {
        var file = SB.askWorkFile('SyncBridge: export Time Remap', 'ae_export.json');
        if (!file) { return; }
        var env = SB.buildExport(comp, layer, 4);
        SB.writeJSON(file, env);
        alert('SyncBridge: exported ' + env.data.keys.length + ' keys\n' + file.fsName);
    }

    function doApply(comp, layer) {
        // Apply files written by the CLI (maya2ae), excluding the *_after.json readback files.
        var file = SB.pickFile('SyncBridge: apply Time Remap', SB.listWorkFiles(/apply/i, /_after\.json$/i));
        if (!file) { return; }
        var data = SB.checkEnvelope(SB.readJSON(file), 'ae.timeremap.apply');
        var result = SB.applyToLayer(comp, layer, data, null), after;
        if (result.status !== 'applied') { return; }

        after = new File(file.fsName.replace(/\.json$/i, '') + '_after.json');
        SB.writeJSON(after, result.after);
        alert('SyncBridge: applied ' + data.keys.length + ' keys.\n' +
            (result.backup ? 'Backup: ' + result.backup + '\n' : '') +
            'Readback: ' + after.fsName);
    }

    try {
        var sel = SB.activeCompAndLayer();
        var dlg = new Window('dialog', 'SyncBridge (Phase 0)');
        dlg.add('statictext', undefined, 'Layer: ' + sel.layer.name);
        var row = dlg.add('group');
        var bExport = row.add('button', undefined, 'Export');
        var bApply = row.add('button', undefined, 'Apply...');
        row.add('button', undefined, 'Cancel', { name: 'cancel' });
        var choice = null;
        bExport.onClick = function () { choice = 'export'; dlg.close(); };
        bApply.onClick = function () { choice = 'apply'; dlg.close(); };
        dlg.show();
        if (choice === 'export') { doExport(sel.comp, sel.layer); }
        if (choice === 'apply') { doApply(sel.comp, sel.layer); }
    } catch (e) {
        SB.alertError('SyncBridge', e);
    }
}());
