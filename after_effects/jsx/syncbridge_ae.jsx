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
        var file = File.saveDialog('SyncBridge: export Time Remap', 'JSON:*.json');
        if (!file) { return; }
        var env = SB.buildExport(comp, layer, 4);
        SB.writeJSON(file, env);
        alert('SyncBridge: exported ' + env.data.keys.length + ' keys\n' + file.fsName);
    }

    function doApply(comp, layer) {
        var file = File.openDialog('SyncBridge: apply Time Remap', 'JSON:*.json');
        if (!file) { return; }
        var data = SB.checkEnvelope(SB.readJSON(file), 'ae.timeremap.apply');
        var keys = data.keys, msg, stamp, backup, after;

        if (!layer.canSetTimeRemapEnabled) {
            throw new Error('Time Remap cannot be enabled on layer "' + layer.name + '".');
        }
        if (Math.abs(comp.frameRate - data.comp_fps[0] / data.comp_fps[1]) > 1e-3) {
            msg = 'Comp frame rate ' + comp.frameRate + ' differs from the payload (' +
                data.comp_fps[0] + '/' + data.comp_fps[1] + '). Continue?';
            if (!confirm(msg)) { return; }
        }
        if (layer.stretch !== 100) {
            if (!confirm('Layer stretch is ' + layer.stretch + '% (Phase 0 assumes 100%). Continue?')) { return; }
        }
        msg = 'Replace Time Remap of layer "' + layer.name + '" with ' + keys.length +
            ' keys (' + data.mode + ' mode)?' +
            (layer.timeRemapEnabled ? '' : '\nTime Remap will be enabled.') +
            '\nA JSON backup is written first.';
        if (!confirm(msg)) { return; }

        stamp = SB.isoNow().replace(/[:\-]/g, '').replace('+0000', '');
        if (layer.timeRemapEnabled) {
            backup = new File(SB.backupFolder().fsName + '/timeremap_' + stamp + '.json');
            SB.writeJSON(backup, SB.buildExport(comp, layer, 4));
        }

        app.beginUndoGroup('SyncBridge apply Time Remap');
        try {
            if (!layer.timeRemapEnabled) { layer.timeRemapEnabled = true; }
            SB.applyKeys(SB.timeRemapProp(layer), keys);
        } finally {
            app.endUndoGroup();
        }

        after = new File(file.fsName.replace(/\.json$/i, '') + '_after.json');
        SB.writeJSON(after, SB.buildExport(comp, layer, 8));
        alert('SyncBridge: applied ' + keys.length + ' keys.\n' +
            (backup ? 'Backup: ' + backup.fsName + '\n' : '') +
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
        alert('SyncBridge error:\n' + e.toString() + (e.line ? '\n(line ' + e.line + ')' : ''));
    }
}());
