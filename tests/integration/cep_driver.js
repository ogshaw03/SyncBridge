/*
 * Test driver: runs the AE panel client (after_effects/panel/js/sbclient.js) in Node
 * with Node's WebSocket and a fake ExtendScript host. Used by test_cep_client.py.
 *
 *   node cep_driver.js <port> <token> <export.json|ERROR> serve
 *   node cep_driver.js <port> <token> <export.json|ERROR> request <maya2ae|ae2maya>
 *   node cep_driver.js <port> <token> <export.json|ERROR> guide     (comp guide; ERROR = no comp)
 *   node cep_driver.js <port> <token> <export.json|ERROR> markers   (key markers; ERROR = no layer)
 *   node cep_driver.js <port> <token> <export.json|ERROR> settings <maya2ae|ae2maya>   (D-21)
 *   node cep_driver.js <port> <token> <export.json|ERROR> timesync  (D-22: switch on, then scrub to 2 s)
 *   node cep_driver.js <port> <token> <export.json|ERROR> pixelmap  (D-24; ERROR = layer without an image)
 *
 * The fake host keeps one comp (COMP) for the scene settings and the current time.
 * Prints one JSON object per line: {event: "connected"|"peers"|"apply"|"result"|"log", ...}.
 * "serve" runs until stdin closes.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const SBPanelClient = require(path.join(__dirname, '..', '..', 'after_effects', 'panel', 'js', 'sbclient.js'));

const [port, token, exportFile, mode, direction] = process.argv.slice(2);
const out = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');

const COMP = {
    comp: 'Comp 1', frameRate: 24, frameDuration: 1 / 24, duration: 4, displayStartTime: 0,
    workAreaStart: 0, workAreaDuration: 4, pixelAspect: 1, width: 1920, height: 1080, time: 0
};

const host = {
    call(name, args, callback) {
        // Round-trip through jsxCall like CEP does: the call string must evaluate to the same args.
        const script = SBPanelClient.jsxCall(name, args);
        let received;
        const SBCep = new Proxy({}, { get: (_, fn) => (...a) => { received = { fn, args: a }; } });
        eval(script);  // eslint-disable-line no-eval
        if (received.fn !== name || JSON.stringify(received.args) !== JSON.stringify(args.map(String))) {
            throw new Error('jsxCall round trip failed for ' + name);
        }
        setTimeout(() => {
            if (name === 'exportSelected') {
                if (exportFile === 'ERROR') {
                    // What syncbridge_cep_host.jsx returns for SB.userError(..., 'select_one_layer', ...)
                    callback({ error: 'Select exactly one layer in comp "Comp 1"', user: true,
                               code: 'select_one_layer', params: { comp: 'Comp 1', count: 0 } });
                } else {
                    callback(JSON.parse(fs.readFileSync(exportFile, 'utf8')));
                }
            } else if (name === 'compInfo') {
                if (exportFile === 'ERROR') {
                    callback({ error: 'Open a composition first', user: true, code: 'no_comp', params: null });
                } else {
                    callback({ name: 'Comp 1', width: 1920, height: 1080, pixelAspect: 1 });
                }
            } else if (name === 'pixelMapInfo') {
                if (exportFile === 'ERROR') {
                    callback({ error: 'Layer "Solid 1" has no image source.', user: true, code: 'no_source',
                               params: { layer: 'Solid 1' } });
                } else {
                    callback({ comp: { id: 12, name: 'Comp 1', width: 1920, height: 1080, pixelAspect: 1, time: 0.5 },
                               layer: { id: 345, name: 'BG', position: [1083.25, 492.5], anchorPoint: [3000, 2000],
                                        scale: [100, 100], rotation: 0, threeD: false, parent: null, effects: [],
                                        source: 'bg.png', source_width: 6000, source_height: 4000 } });
                }
            } else if (name === 'layersInfo') {
                callback({ comp: { id: 12, name: 'Comp 1', width: 1920, height: 1080, frameRate: 24, duration: 4, time: 0 },
                           layers: [{ id: 345, index: 1, name: 'BG', kind: 'still', source: 'bg.png' },
                                    { id: 346, index: 2, name: 'CHAR_A', kind: 'sequence', source: 'char_a_[0001-0096].png' }] });
            } else if (name === 'layerMotion') {
                const query = JSON.parse(args[0]);
                callback({ comp: { id: 12, name: 'Comp 1', width: 1920, height: 1080, pixelAspect: 1, time: 0 },
                           layer: { id: query.layer_id, name: query.layer, threeD: false, parent: null, effects: [],
                                    source_width: 6000, source_height: 4000 },
                           samples: query.times.map((t) => ({ t, position: [960 + 100 * t, 540],
                                                              anchorPoint: [3000, 2000], scale: [100, 100], rotation: 0 })) });
            } else if (name === 'sceneSettings') {
                callback(Object.assign({}, COMP));
            } else if (name === 'applySceneSettings') {
                const plan = JSON.parse(args[0]);
                out({ event: 'applySettings', apply: plan.apply, message: args[1] });
                Object.assign(COMP, plan.apply);
                callback({ status: 'applied', backup: '(test)', after: Object.assign({}, COMP) });
            } else if (name === 'compTime') {
                callback({ time: COMP.time, frameDuration: COMP.frameDuration, comp: COMP.comp });
            } else if (name === 'setTime') {
                COMP.time = Number(args[0]);
                out({ event: 'setTime', t: COMP.time });
                callback({ time: COMP.time });
            } else if (name === 'applyEnvelope') {
                const env = JSON.parse(args[0]);
                out({ event: 'apply', keys: env.data.keys.length, kind: env.kind, origin: args[1] });
                callback({ status: 'applied', backup: '(test)', after: null });
            } else {
                callback({ error: 'unexpected ' + name, user: false });
            }
        }, 10);
    }
};

const client = new SBPanelClient({
    host,
    WebSocketImpl: WebSocket,
    onLog: (text) => {
        out({ event: 'log', text });
        if (mode === 'request' && text.startsWith('connection closed')) { process.exit(3); }
    },
    onState: () => {
        if (client.connected()) {
            out({ event: 'peers', peers: client.peers.map((p) => p.app) });
        }
    },
    version: 'node-test',
    document: 'cep-driver'
});
client.connect({ port: Number(port), token });

const whenMaya = (fn) => {
    const timer = setInterval(() => {
        if (client.connected() && client.hasPeer('maya')) { clearInterval(timer); fn(); }
    }, 50);
};

if (mode === 'pixelmap') {
    whenMaya(() => {
        client.sendPixelMap({}, (reply) => {
            out({ event: 'result', reply });
            client.disconnect();
            setTimeout(() => process.exit(0), 100);
        });
    });
} else if (mode === 'settings') {
    whenMaya(() => {
        client.sendSettings(direction, ['fps', 'playback_range', 'animation_range', 'pixel_aspect'], { origin: 1 },
            (reply) => {
                out({ event: 'result', reply });
                client.disconnect();
                setTimeout(() => process.exit(0), 100);
            });
    });
} else if (mode === 'timesync') {
    whenMaya(() => {
        client.setTimeSync(true, false);
        out({ event: 'switched' });
        setTimeout(() => { COMP.time = 2; out({ event: 'scrubbed', t: 2 }); }, 600);
    });
    process.stdin.on('data', () => {});
    process.stdin.on('end', () => { client.disconnect(); setTimeout(() => process.exit(0), 100); });
} else if (mode === 'markers') {
    const timer = setInterval(() => {
        if (client.connected() && client.hasPeer('maya')) {
            clearInterval(timer);
            client.sendMarkers({ origin: 1001 }, (reply) => {
                out({ event: 'result', reply });
                client.disconnect();
                setTimeout(() => process.exit(0), 100);
            });
        }
    }, 50);
} else if (mode === 'guide') {
    const timer = setInterval(() => {
        if (client.connected() && client.hasPeer('maya')) {
            clearInterval(timer);
            client.sendGuide((reply) => {
                out({ event: 'result', reply });
                client.disconnect();
                setTimeout(() => process.exit(0), 100);
            });
        }
    }, 50);
} else if (mode === 'request') {
    const timer = setInterval(() => {
        if (client.connected() && client.hasPeer('maya')) {
            clearInterval(timer);
            client.transfer(direction, { origin: 1 }, (reply) => {
                out({ event: 'result', reply });
                client.disconnect();
                setTimeout(() => process.exit(0), 100);
            });
        }
    }, 50);
} else {
    process.stdin.on('data', () => {});
    process.stdin.on('end', () => { client.disconnect(); setTimeout(() => process.exit(0), 100); });
}
setTimeout(() => { out({ event: 'timeout' }); process.exit(2); }, 30000);
