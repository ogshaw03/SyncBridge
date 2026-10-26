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

    // ---- scene settings (D-21) and time slider sync (D-22) ----------------------------------
    // Not yet run in After Effects (docs/PHASE0_RESEARCH.md):
    //   H-AE-21: setting comp.frameRate / duration / displayStartTime / workAreaStart /
    //            workAreaDuration / pixelAspect inside one undo group; one undo restores them.
    //   H-AE-22: displayStartTime only changes the frame numbers AE shows; comp.time, layer
    //            times and Time Remap key times stay relative to the comp start (time 0).
    //   H-AE-23: setting comp.time from the panel moves the current time indicator and the viewer.
    function activeComp() {
        var comp = app.project.activeItem;
        if (!(comp instanceof CompItem)) {
            throw SB.userError('Open a composition first (click its timeline).', 'no_comp');
        }
        return comp;
    }

    function settingsOf(comp) {
        return {
            comp: comp.name, frameRate: comp.frameRate, frameDuration: comp.frameDuration,
            duration: comp.duration, displayStartTime: comp.displayStartTime,
            workAreaStart: comp.workAreaStart, workAreaDuration: comp.workAreaDuration,
            pixelAspect: comp.pixelAspect, width: comp.width, height: comp.height, time: comp.time
        };
    }

    function sceneSettings() {
        try {
            return ok(settingsOf(activeComp()));
        } catch (e) { return fail(e); }
    }

    // settings.apply.request: `planText` = the plan (core.scene_sync) as JSON text, `message` =
    // the question in Japanese made by the hub (passed with \u escapes, see jsxCall).
    function applySceneSettings(planText, message) {
        try {
            var comp = activeComp(), values = SBJSON.parse(planText).apply, stamp, backup;
            if (!confirm(message)) { return ok({ status: 'cancelled' }); }
            stamp = SB.isoNow().replace(/[:\-]/g, '').replace('+0000', '');
            backup = new File(SB.backupFolder().fsName + '/settings_' + stamp + '.json');
            SB.writeJSON(backup, { syncbridge: 'ae comp settings backup', settings: settingsOf(comp) });
            app.beginUndoGroup('SyncBridge scene settings');
            try {
                if (values.frameRate !== undefined) { comp.frameRate = values.frameRate; }
                if (values.workAreaStart !== undefined) { comp.workAreaStart = 0; }
                if (values.duration !== undefined) { comp.duration = values.duration; }
                if (values.displayStartTime !== undefined) { comp.displayStartTime = values.displayStartTime; }
                if (values.workAreaDuration !== undefined) { comp.workAreaDuration = values.workAreaDuration; }
                if (values.workAreaStart !== undefined) { comp.workAreaStart = values.workAreaStart; }
                if (values.pixelAspect !== undefined) { comp.pixelAspect = values.pixelAspect; }
            } finally {
                app.endUndoGroup();
            }
            return ok({ status: 'applied', backup: backup.fsName, after: settingsOf(comp) });
        } catch (e) { return fail(e); }
    }

    // Polled by the panel while the time slider sync is on: {time, frameDuration, comp} or {time: null}.
    function compTime() {
        try {
            var comp = app.project.activeItem;
            if (!(comp instanceof CompItem)) { return ok({ time: null }); }
            return ok({ time: comp.time, frameDuration: comp.frameDuration, comp: comp.name });
        } catch (e) { return fail(e); }
    }

    function setTime(t) {
        try {
            var comp = app.project.activeItem;
            if (!(comp instanceof CompItem)) { return ok({ time: null }); }
            comp.time = Number(t);
            return ok({ time: comp.time });
        } catch (e) { return fail(e); }
    }

    // ---- Pixel Mapping (D-24) -------------------------------------------------------------------
    // The selected layer's 2D transform at the current time, for the mapped Maya camera.
    //   H-AE-26: Layer.id / CompItem.id are persistent ids (Layer.id: AE 22+); null when missing.
    //   H-AE-27: with separated dimensions, X / Y Position are read from 'ADBE Position_0' / '_1'.
    function v2(prop, t) {
        var v = prop.valueAtTime(t, false);
        return [v[0], v[1]];
    }

    // position / anchorPoint / scale / rotation of a 2D layer at comp time t (expressions applied)
    function transformAt(layer, t) {
        var tr = layer.property('ADBE Transform Group'), pos = tr.property('ADBE Position'), position;
        if (pos.dimensionsSeparated) {
            position = [tr.property('ADBE Position_0').valueAtTime(t, false),
                        tr.property('ADBE Position_1').valueAtTime(t, false)];
        } else {
            position = v2(pos, t);
        }
        return { position: position, anchorPoint: v2(tr.property('ADBE Anchor Point'), t),
                 scale: v2(tr.property('ADBE Scale'), t), rotation: tr.property('ADBE Rotate Z').valueAtTime(t, false) };
    }

    // the parent's transform, its parent's, ... at comp time t (a null that pans the layers, H-AE-30)
    function parentChain(layer, t) {
        var out = [], p = layer.parent, tr;
        while (p) {
            tr = transformAt(p, t);
            tr.name = p.name;
            tr.threeD = p.threeDLayer;
            out.push(tr);
            p = p.parent;
        }
        return out;
    }

    function imageSource(layer) {
        var src = layer.source;
        if (!src || !(src.width > 0)) {
            throw SB.userError('Layer "' + layer.name + '" has no image source.', 'no_source', { layer: layer.name });
        }
        return src;
    }

    function effectNames(layer) {
        var effects = [], fx = layer.property('ADBE Effect Parade'), i;
        if (fx) {
            for (i = 1; i <= fx.numProperties; i++) {
                if (fx.property(i).enabled) { effects.push(fx.property(i).name); }
            }
        }
        return effects;
    }

    function layerInfo(layer, src, t) {
        var out = transformAt(layer, t);
        out.id = (layer.id !== undefined) ? layer.id : null;
        out.name = layer.name;
        out.index = layer.index;
        out.threeD = layer.threeDLayer;
        out.parent = layer.parent ? layer.parent.name : null;
        out.parents = parentChain(layer, t);
        out.effects = effectNames(layer);
        out.source = src.name;
        out.source_id = src.id;
        out.source_width = src.width;
        out.source_height = src.height;
        return out;
    }

    function compSummary(comp, t) {
        return { id: comp.id, name: comp.name, width: comp.width, height: comp.height,
                 pixelAspect: comp.pixelAspect, frameRate: comp.frameRate, time: t };
    }

    function pixelMapInfo() {
        try {
            var sel = SB.activeCompAndLayer(), comp = sel.comp, layer = sel.layer, t = comp.time;
            return ok({ comp: compSummary(comp, t), layer: layerInfo(layer, imageSource(layer), comp.time) });
        } catch (e) { return fail(e); }
    }

    // ---- Phase 3 (D-30): one layer's transform at many comp times, asked by Maya ---------------------
    //   argsText = {comp_id, comp, layer_id, layer, times: [seconds]} as JSON text.
    //   H-AE-29: app.project.itemByID(id) finds the comp by its id; Layer.id finds the layer.
    function findComp(compId, compName) {
        var comp = null, i, item;
        if (compId !== null && compId !== undefined) {
            try { comp = app.project.itemByID(Number(compId)); } catch (e1) { comp = null; }
        }
        if (!(comp instanceof CompItem)) {
            for (i = 1; i <= app.project.numItems; i++) {
                item = app.project.item(i);
                if (item instanceof CompItem && item.name === compName) { comp = item; break; }
            }
        }
        if (!(comp instanceof CompItem)) {
            throw SB.userError('Comp "' + compName + '" was not found.', 'no_comp_named', { comp: compName });
        }
        return comp;
    }

    function findLayerIn(comp, layerId, layerName) {
        var i;
        if (layerId !== null && layerId !== undefined) {
            for (i = 1; i <= comp.numLayers; i++) {
                if (comp.layer(i).id === Number(layerId)) { return comp.layer(i); }
            }
        }
        for (i = 1; i <= comp.numLayers; i++) {
            if (comp.layer(i).name === layerName) { return comp.layer(i); }
        }
        throw SB.userError('Layer "' + layerName + '" was not found in comp "' + comp.name + '".',
                           'no_layer_named', { comp: comp.name, layer: layerName });
    }

    // args.via = the precomp layers from the top comp down to the layer's comp (D-37):
    // [{comp_id, comp, layer_id, layer}, ...], empty for a layer of the top comp itself
    function findLayer(args) {
        var via = args.via || [], top, comp, containers = [], i, holder;
        if (via.length === 0) {
            comp = findComp(args.comp_id, args.comp);
            return { top: comp, containers: [], layer: findLayerIn(comp, args.layer_id, args.layer) };
        }
        top = findComp(via[0].comp_id, via[0].comp);
        comp = top;
        for (i = 0; i < via.length; i++) {
            holder = findLayerIn(comp, via[i].layer_id, via[i].layer);
            if (!(holder.source instanceof CompItem)) {
                throw SB.userError('Layer "' + holder.name + '" is not a precomp.', 'no_layer_named',
                                   { comp: comp.name, layer: holder.name });
            }
            containers.push(holder);
            comp = holder.source;
        }
        return { top: top, containers: containers, layer: findLayerIn(comp, args.layer_id, args.layer) };
    }

    // The time inside a precomp layer's source at time t of the comp it is in. H-AE-31: there is no
    // AVLayer.sourceTime in AE 26.5 ("undefined", the user, 2026-10-25): time remap when on, else
    // (t - startTime) * 100 / stretch.
    function sourceTimeOf(layer, t) {
        if (layer.timeRemapEnabled) {
            return layer.property('ADBE Time Remapping').valueAtTime(t, false);
        }
        return (t - layer.startTime) * 100 / layer.stretch;
    }

    // The containers' transforms at top comp time t, and the time inside the innermost comp.
    function throughContainers(containers, t) {
        var out = [], i, tr, layerTime = t;
        for (i = 0; i < containers.length; i++) {
            tr = transformAt(containers[i], layerTime);
            tr.name = containers[i].name;
            tr.threeD = containers[i].threeDLayer;
            tr.parents = parentChain(containers[i], layerTime);
            out.push(tr);
            layerTime = sourceTimeOf(containers[i], layerTime);
        }
        return { containers: out, time: layerTime };
    }

    function layerMotion(argsText) {
        try {
            var args = SBJSON.parse(argsText), found = findLayer(args), layer = found.layer;
            var src = imageSource(layer), samples = [], i, t, s, inner;
            for (i = 0; i < args.times.length; i++) {
                t = Number(args.times[i]);
                inner = throughContainers(found.containers, t);
                s = transformAt(layer, inner.time);
                s.t = t;
                s.parents = parentChain(layer, inner.time);
                s.containers = inner.containers;
                samples.push(s);
            }
            inner = throughContainers(found.containers, found.top.time);
            return ok({ comp: compSummary(found.top, found.top.time), layer: layerInfo(layer, src, inner.time),
                        samples: samples });
        } catch (e) { return fail(e); }
    }

    // ---- layer map (D-28): the active comp's layers for Maya's node editor ---------------------------
    //   H-AE-28: FootageItem.mainSource is a FileSource (isStill: still or sequence / movie), a
    //            SolidSource or a PlaceholderSource; CompItem sources are precomps.
    var SEQ_EXT = /\.(png|jpe?g|tiff?|exr|dpx|tga|psd|bmp|cin|hdr|sgi|iff|webp)$/i;

    function layerKind(layer) {
        var src = layer.source;
        if (layer instanceof CameraLayer) { return 'camera'; }
        if (layer instanceof LightLayer) { return 'light'; }
        if (layer instanceof TextLayer) { return 'text'; }
        if (layer instanceof ShapeLayer) { return 'shape'; }
        if (layer.nullLayer) { return 'null'; }
        if (!src) { return 'other'; }
        if (src instanceof CompItem) { return 'comp'; }
        if (src.mainSource instanceof SolidSource) { return 'solid'; }
        if (src.mainSource instanceof FileSource) {
            if (src.mainSource.isStill) { return 'still'; }
            return (src.file && SEQ_EXT.test(src.file.name)) ? 'sequence' : 'movie';
        }
        return 'other';
    }

    function keyed(group, name) {
        var p = group.property(name);
        return !!(p && p.numKeys > 0);
    }

    var MAX_DEPTH = 3;          // precomps inside precomps listed (D-37)

    // The comp's layers, and the layers of its precomps under them (via = the precomp layers above).
    // selected: the layer is selected in the comp open in AE (activeId); a selection left in another comp
    // is not used. H-AE-32: Layer.selected is the layer's selection in its own comp.
    function listLayers(comp, via, out, activeId) {
        var i, layer, tr, src, kind;
        for (i = 1; i <= comp.numLayers; i++) {
            layer = comp.layer(i);
            src = layer.source;
            tr = layer.property('ADBE Transform Group');
            kind = layerKind(layer);
            out.push({
                id: (layer.id !== undefined) ? layer.id : null, index: i, name: layer.name,
                kind: kind, enabled: layer.enabled, comp_id: comp.id, comp: comp.name, via: via,
                source: src ? src.name : null, source_id: src ? src.id : null,
                width: (src && src.width) ? src.width : null, height: (src && src.height) ? src.height : null,
                inPoint: layer.inPoint, outPoint: layer.outPoint, threeD: !!layer.threeDLayer,
                parent: layer.parent ? layer.parent.name : null,
                selected: comp.id === activeId && !!layer.selected,
                keyed: {position: keyed(tr, 'ADBE Position'), scale: keyed(tr, 'ADBE Scale'),
                        rotation: keyed(tr, 'ADBE Rotate Z')}
            });
            if (kind === 'comp' && via.length < MAX_DEPTH) {
                listLayers(src, via.concat([{ comp_id: comp.id, comp: comp.name, layer_id: layer.id,
                                              layer: layer.name }]), out, activeId);
            }
        }
    }

    //   argsText = {main_comp_id, main_comp} as JSON text, or empty: the comp the layer map is built on.
    //   Without it the active comp is the main comp. With it, the main comp is listed even while a precomp
    //   inside it is open in AE (to select a BG in there), so the layers keep their path from the main
    //   comp and the precomps' motion (the camera work) is not lost.
    function layersInfo(argsText) {
        try {
            var args = argsText ? SBJSON.parse(argsText) : {}, comp, out = [], active = app.project.activeItem;
            if (!(active instanceof CompItem)) { active = null; }
            if (args.main_comp_id !== undefined && args.main_comp_id !== null) {
                comp = findComp(args.main_comp_id, args.main_comp);
            } else {
                comp = activeComp();
            }
            listLayers(comp, [], out, active ? active.id : null);
            // H-AE-33: CompItem.usedIn = the comps that use this comp as a precomp. Maya asks to take the
            // outer comp as the main comp (a precomp read as the main comp lost the PAN, the user, 2026-10-26).
            var usedIn = [], j;
            for (j = 0; j < comp.usedIn.length; j++) {
                usedIn.push({ id: comp.usedIn[j].id, name: comp.usedIn[j].name });
            }
            return ok({
                comp: { id: comp.id, name: comp.name, width: comp.width, height: comp.height,
                        frameRate: comp.frameRate, duration: comp.duration, time: comp.time, usedIn: usedIn },
                active: active ? { id: active.id, name: active.name, selected: active.selectedLayers.length } : null,
                layers: out
            });
        } catch (e) { return fail(e); }
    }

    return {
        readSession: readSession,
        pixelMapInfo: pixelMapInfo,
        layersInfo: layersInfo,
        layerMotion: layerMotion,
        info: info,
        exportSelected: exportSelected,
        applyEnvelope: applyEnvelope,
        compInfo: compInfo,
        sceneSettings: sceneSettings,
        applySceneSettings: applySceneSettings,
        compTime: compTime,
        setTime: setTime
    };
}());
