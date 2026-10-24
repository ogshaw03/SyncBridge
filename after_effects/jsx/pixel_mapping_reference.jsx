// SyncBridge Pixel Mapping, Phase 1: AE reference frames (docs/PIXEL_MAPPING.md).
//
// Run in After Effects 2024+: File > Scripts > Run Script File... and pick this file.
//   1. pick testgrid_6000x4000.png (tools/pixel_mapping/make_testgrid.py makes it)
//   2. pick an empty folder for the results
// It makes the comp "SB_PixelMapping_Test" (1920 x 1080, square pixels, 24 fps) with the BG as a 2D
// layer (anchor = image center, Best quality, no motion blur) whose Position is held at one test
// case per frame, writes pixel_mapping_cases.json (the cases) and tries to save each frame as
// ae_ref_<frame>.png with CompItem.saveFrameToPng (H-AE-25: not yet run). If that is not available,
// render the comp from the Render Queue as a PNG sequence named ae_ref_[####].png into the same folder.
// Then: py -3 tools/pixel_mapping/check_reference.py <folder>
//
// ExtendScript (ES3), ASCII only; standalone (no #include).
(function () {
    var CASES = [[960, 540], [2194, -237], [960.5, 540.5], [659.75, 660.75], [2960, 1840],
                 [961, 540], [960.25, 540], [960, 540.75]];
    var FPS = 24;
    var W = 1920, H = 1080;

    function pad(n) {
        var s = String(n);
        while (s.length < 4) { s = '0' + s; }
        return s;
    }

    function num(v) {
        return String(Math.round(v * 1e6) / 1e6);
    }

    var img = File.openDialog('SyncBridge: select testgrid_6000x4000.png', 'PNG:*.png');
    if (!img) { return; }
    var out = Folder.selectDialog('SyncBridge: select an empty folder for the AE reference frames');
    if (!out) { return; }

    app.beginUndoGroup('SyncBridge pixel mapping test');
    var footage = app.project.importFile(new ImportOptions(img));
    var comp = app.project.items.addComp('SB_PixelMapping_Test', W, H, 1.0, CASES.length / FPS, FPS);
    comp.resolutionFactor = [1, 1];
    comp.motionBlur = false;
    var layer = comp.layers.add(footage);
    layer.quality = LayerQuality.BEST;
    layer.motionBlur = false;
    var transform = layer.property('ADBE Transform Group');
    transform.property('ADBE Anchor Point').setValue([footage.width / 2, footage.height / 2]);
    var pos = transform.property('ADBE Position');
    var i, k;
    for (i = 0; i < CASES.length; i++) {
        k = pos.addKey(i / FPS);
        pos.setValueAtKey(k, CASES[i]);
    }
    for (k = 1; k <= pos.numKeys; k++) {
        pos.setInterpolationTypeAtKey(k, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
    }
    app.endUndoGroup();

    // the cases, read by check_reference.py
    var lines = [];
    for (i = 0; i < CASES.length; i++) {
        lines.push('    {"frame": ' + i + ', "position": [' + num(CASES[i][0]) + ', ' + num(CASES[i][1]) + ']}');
    }
    var anchor = transform.property('ADBE Anchor Point').value;
    var json = '{\n  "comp": {"width": ' + W + ', "height": ' + H + ', "pixelAspect": ' + num(comp.pixelAspect) +
        ', "frameRate": ' + num(comp.frameRate) + '},\n' +
        '  "source": {"name": "' + footage.name.replace(/[\\"]/g, '_') + '", "width": ' + footage.width +
        ', "height": ' + footage.height + '},\n' +
        '  "layer": {"anchorPoint": [' + num(anchor[0]) + ', ' + num(anchor[1]) + '], "scale": [100, 100], ' +
        '"rotation": 0, "quality": "best"},\n' +
        '  "aeVersion": "' + app.version + '",\n' +
        '  "cases": [\n' + lines.join(',\n') + '\n  ]\n}\n';
    var f = new File(out.fsName + '/pixel_mapping_cases.json');
    f.encoding = 'UTF-8';
    f.open('w');
    f.write(json);
    f.close();

    var saved = 0, problem = '';
    if (typeof comp.saveFrameToPng === 'function') {
        for (i = 0; i < CASES.length; i++) {
            try {
                comp.saveFrameToPng(i / FPS, new File(out.fsName + '/ae_ref_' + pad(i) + '.png'));
                saved++;
            } catch (e) {
                problem = e.toString();
                break;
            }
        }
    } else {
        problem = 'CompItem.saveFrameToPng is not available in this version';
    }
    if (saved === CASES.length) {
        alert('SyncBridge: saved ' + saved + ' frames and pixel_mapping_cases.json in\n' + out.fsName +
              '\n\n(saveFrameToPng may finish writing a moment later.)');
    } else {
        alert('SyncBridge: the comp "SB_PixelMapping_Test" and pixel_mapping_cases.json are ready, but the frames ' +
              'were not saved (' + problem + ').\n\nRender the comp from the Render Queue as a PNG sequence ' +
              'named ae_ref_[####].png into\n' + out.fsName);
    }
}());
