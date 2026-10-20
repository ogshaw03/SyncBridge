/*
 * Test driver: runs the AE panel client (after_effects/panel/js/sbclient.js) in Node
 * with Node's WebSocket and a fake ExtendScript host. Used by test_cep_client.py.
 *
 *   node cep_driver.js <port> <token> <export.json|ERROR> serve
 *   node cep_driver.js <port> <token> <export.json|ERROR> request <maya2ae|ae2maya>
 *   node cep_driver.js <port> <token> <export.json|ERROR> guide     (comp guide; ERROR = no comp)
 *   node cep_driver.js <port> <token> <export.json|ERROR> markers   (key markers; ERROR = no layer)
 *
 * Prints one JSON object per line: {event: "connected"|"peers"|"apply"|"result"|"log", ...}.
 * "serve" runs until stdin closes.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const SBPanelClient = require(path.join(__dirname, '..', '..', 'after_effects', 'panel', 'js', 'sbclient.js'));

const [port, token, exportFile, mode, direction] = process.argv.slice(2);
const out = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');

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

if (mode === 'markers') {
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
