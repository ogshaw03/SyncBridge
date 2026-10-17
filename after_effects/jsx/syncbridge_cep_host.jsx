// SyncBridge CEP panel host script (Phase 1-C). Loaded by CSXS/manifest.xml <ScriptPath>.
//
// The panel (panel/js) calls these through evalScript. Every function returns a
// JSON string: the result object, or {"error": message, "user": true|false}
// ("user" = caused by the current state in AE, show it as guidance).
//
// Verification status (docs/PHASE1_PLAN.md): not yet run in After Effects.
//   H-AE-15: evalScript from the panel can call functions defined here.
//   H-AE-16: confirm() called from an evalScript call shows a modal dialog in AE.

#include "syncbridge_ae_lib.jsxinc"

var SBCep = (function () {
    function ok(value) { return SBJSON.stringify(value); }

    function fail(e) {
        return SBJSON.stringify({
            error: (e && e.message) ? e.message : String(e),
            user: !!(e && e.sbUser),
            code: (e && e.sbCode) ? e.sbCode : null,
            params: (e && e.sbParams) ? e.sbParams : null,
            line: (e && e.line) ? e.line : null
        });
    }

    // %LOCALAPPDATA%/SyncBridge/session.json written by the server ({port, token, ...}).
    function sessionFile() {
        var base = $.getenv('SYNCBRIDGE_SESSION_DIR');
        if (!base) {
            base = $.getenv('LOCALAPPDATA');
            if (!base) { throw SB.userError('LOCALAPPDATA is not set'); }
            base = base + '/SyncBridge';
        }
        return new File(base + '/session.json');
    }

    function readSession() {
        try {
            var f = sessionFile();
            if (!f.exists) {
                return fail(SB.userError('The SyncBridge server is not running (no ' + f.fsName + ').\n' +
                    'Start it from the Maya panel (Connect) or with syncbridge-server.cmd.', 'no_server'));
            }
            return ok(SB.readJSON(f));
        } catch (e) { return fail(e); }
    }

    function info() {
        try {
            var comp = app.project.activeItem, out = {
                aeVersion: app.version,
                project: app.project.file ? app.project.file.displayName : 'untitled',
                comp: null, layer: null
            };
            if (comp instanceof CompItem) {
                out.comp = { name: comp.name, frameRate: comp.frameRate, width: comp.width, height: comp.height };
                if (comp.selectedLayers.length === 1) {
                    out.layer = {
                        name: comp.selectedLayers[0].name,
                        timeRemapEnabled: comp.selectedLayers[0].timeRemapEnabled,
                        canSetTimeRemapEnabled: comp.selectedLayers[0].canSetTimeRemapEnabled
                    };
                } else {
                    out.selectedLayers = comp.selectedLayers.length;
                }
            }
            return ok(out);
        } catch (e) { return fail(e); }
    }

    // export.request: the selected layer's Time Remap (Phase 0 export format).
    // Time Remap may be off: then keys are [] (enough for a Maya -> AE target; the
    // server refuses AE -> Maya without keys).
    function exportSelected() {
        try {
            var sel = SB.activeCompAndLayer();
            return ok(SB.buildExport(sel.comp, sel.layer, 4, true));
        } catch (e) { return fail(e); }
    }

    // apply.request: `text` is the "ae.timeremap.apply" envelope as JSON text.
    function applyEnvelope(text, origin) {
        try {
            var data = SB.checkEnvelope(SBJSON.parse(text), 'ae.timeremap.apply');
            var sel = SB.activeCompAndLayer();
            return ok(SB.applyToLayer(sel.comp, sel.layer, data, origin || 'Maya'));
        } catch (e) { return fail(e); }
    }

    // guide.request (D-16): size of the active comp, shown as a frame in the Maya view.
    // CompItem.width / height / pixelAspect (H-AE-20, documented; not yet run).
    function compInfo() {
        try {
            var comp = app.project.activeItem;
            if (!(comp instanceof CompItem)) {
                throw SB.userError('Open a composition first (click its timeline).', 'no_comp');
            }
            return ok({ name: comp.name, width: comp.width, height: comp.height, pixelAspect: comp.pixelAspect });
        } catch (e) { return fail(e); }
    }

    return {
        readSession: readSession,
        info: info,
        exportSelected: exportSelected,
        applyEnvelope: applyEnvelope,
        compInfo: compInfo
    };
}());
