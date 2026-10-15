// SyncBridge Phase 0 After Effects probe: checks hypotheses H-AE-1..5.
//
// 1. python -m syncbridge.cli probe-vectors -o probe_results/ae_probe_vectors.json
// 2. In AE: File > Scripts > Run Script File... > probe_ae.jsx, pick the vectors file.
//    The probe creates two temporary comps (SB_probe_inner / SB_probe_outer),
//    applies every vector to a time-remapped precomp layer, samples it with
//    valueAtTime, then deletes both comps. Existing comps are not touched.
// 3. python -m syncbridge.cli verify-ae-probe probe_results/ae_probe_results.json

#include "syncbridge_ae_lib.jsxinc"

(function () {
    var START_OFFSET = 0.5; // layer startTime used for the H-AE-1 variant

    function runVector(layer, comp, vec, oversample, nameSuffix) {
        var prop = SB.timeRemapProp(layer), keys, range, s;
        var result = { name: vec.name + (nameSuffix || ''), sentKeys: vec.keys };
        try {
            SB.applyKeys(prop, vec.keys);
            keys = SB.readKeys(prop);
            range = SB.keyRange(vec.keys, layer);
            s = SB.sample(prop, range[0], range[1], comp.frameDuration, oversample);
            result.readKeys = keys;
            result.times = s.times;
            result.values = s.values;
            result.numKeys = prop.numKeys;
        } catch (e) {
            result.error = e.toString() + (e.line ? ' (line ' + e.line + ')' : '');
        }
        return result;
    }

    function shiftKeys(keys, dt) {
        var out = [], i, k;
        for (i = 0; i < keys.length; i++) {
            k = keys[i];
            out.push({ time: k.time + dt, value: k.value, inInterp: k.inInterp, outInterp: k.outInterp,
                inEase: k.inEase, outEase: k.outEase });
        }
        return out;
    }

    var HOW_TO = 'Create it on the PC first (in the repository folder):\n' +
        '  .\\syncbridge.cmd probe-vectors -o probe_results\\ae_probe_vectors.json';

    // Default: <repo>/probe_results/ae_probe_vectors.json next to this script's repository.
    function pickVectorsFile() {
        var repo = new File($.fileName).parent.parent.parent;
        var def = new File(repo.fsName + '/probe_results/ae_probe_vectors.json');
        if (def.exists) {
            if (confirm('SyncBridge probe: use this vectors file?\n' + def.fsName)) { return def; }
        } else {
            alert('SyncBridge probe: ae_probe_vectors.json was not found at\n' + def.fsName + '\n\n' +
                HOW_TO + '\n\nYou can also pick the file manually in the next dialog.');
        }
        var picked = File.openDialog('SyncBridge probe: select ae_probe_vectors.json', 'JSON:*.json');
        if (!picked) { alert('SyncBridge probe: cancelled (no vectors file selected).\n\n' + HOW_TO); }
        return picked;
    }

    try {
        var vf = pickVectorsFile();
        if (!vf) { return; }
        var data = SB.checkEnvelope(SB.readJSON(vf), 'ae.probe.vectors');
        var fps = data.comp_fps[0] / data.comp_fps[1];
        if (!confirm('SyncBridge probe will create and delete two temporary comps ' +
                '(SB_probe_inner / SB_probe_outer). Continue?')) { return; }

        var inner = app.project.items.addComp('SB_probe_inner', 640, 360, 1, 60, fps);
        var outer = app.project.items.addComp('SB_probe_outer', 640, 360, 1, 60, fps);
        var results = [], env = {}, i, layer, vec;
        app.beginUndoGroup('SyncBridge probe');
        try {
            layer = outer.layers.add(inner);
            env.canSetTimeRemapEnabled = layer.canSetTimeRemapEnabled;
            layer.timeRemapEnabled = true;
            env.defaultKeysAfterEnable = SB.readKeys(SB.timeRemapProp(layer));

            for (i = 0; i < data.vectors.length; i++) {
                results.push(runVector(layer, outer, data.vectors[i], data.sample_oversample));
            }

            // H-AE-1: with layer startTime != 0, are key times still comp times?
            layer.startTime = START_OFFSET;
            for (i = 0; i < data.vectors.length; i++) {
                vec = data.vectors[i];
                if (vec.name === 'slowmo_linear' || vec.name === 'speed_ramp_bezier') {
                    results.push(runVector(layer, outer,
                        { name: vec.name, keys: shiftKeys(vec.keys, START_OFFSET) },
                        data.sample_oversample, '@startTime' + START_OFFSET));
                }
            }
            env.layerAfter = SB.layerInfo(layer);
        } finally {
            app.endUndoGroup();
            outer.remove();
            inner.remove();
        }

        env.aeVersion = app.version;
        env.extendScript = $.version;
        env.os = $.os;
        var out = new File(vf.fsName.replace(/vectors(\.json)?$/i, 'results.json'));
        if (out.fsName === vf.fsName) { out = new File(vf.fsName.replace(/\.json$/i, '') + '_results.json'); }
        SB.writeJSON(out, SB.makeEnvelope('ae.probe.results', {
            comp_fps: data.comp_fps, environment: env, results: results
        }));
        var errors = 0;
        for (i = 0; i < results.length; i++) { if (results[i].error) { errors++; } }
        alert('SyncBridge probe finished: ' + results.length + ' runs, ' + errors + ' errors.\n' + out.fsName);
    } catch (e) {
        SB.alertError('SyncBridge probe', e);
    }
}());
