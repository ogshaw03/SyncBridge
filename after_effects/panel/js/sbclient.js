/*
 * SyncBridge panel client (Phase 1-C): WebSocket connection to the Local Sync Server.
 *
 * Independent of CEP and of the DOM so it can be tested in Node (tests/integration):
 *   host.call(name, args, callback)  runs SBCep[name](...args) in ExtendScript and
 *                                    calls back with the parsed JSON result
 *   WebSocketImpl                    the browser's WebSocket (or Node's)
 * Protocol: docs/API.md (same envelopes as syncbridge/protocol.py).
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.SBPanelClient = factory();
    }
}(this, function () {
    'use strict';

    var SCHEMA = 'syncbridge.exchange';
    var SCHEMA_VERSION = '0.1';
    var PROTOCOL_VERSION = 1;

    function uuid() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) { return crypto.randomUUID(); }
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            var r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    function message(kind, data, replyTo) {
        var msg = {
            schema: SCHEMA, schema_version: SCHEMA_VERSION, kind: kind, event_id: uuid(),
            source_id: 'ae', revision: 0, created: new Date().toISOString(), app: {}, data: data || {}
        };
        if (replyTo) { msg.reply_to = replyTo; }
        return msg;
    }

    // An ExtendScript call `SBCep.name(arg, ...)` whose string literals are pure ASCII
    // (ExtendScript rejects some raw characters such as U+2028 in source text).
    function jsxCall(name, args) {
        var parts = (args || []).map(function (a) {
            return JSON.stringify(String(a)).replace(/[\u007f-￿]/g, function (c) {
                return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
            });
        });
        return 'SBCep.' + name + '(' + parts.join(',') + ')';
    }

    // Messages for user errors reported by ExtendScript (SB.userError codes in
    // jsx/syncbridge_ae_lib.jsxinc). Shown in this panel and sent to Maya.
    var MESSAGES = {
        no_comp: function () {
            return 'コンポジションを開いてください（タイムラインをクリックしてアクティブにしてから、もう一度送ってください）。';
        },
        select_one_layer: function (p) {
            return 'コンポ「' + p.comp + '」でレイヤーを 1 つだけ選択してから、もう一度送ってください' +
                '（現在 ' + p.count + ' 個選択中）。';
        },
        cannot_remap: function (p) {
            return 'レイヤー「' + p.layer + '」はタイムリマップを使えません' +
                '（平面・テキスト・シェイプ・カメラ・ライトは不可）。フッテージかプリコンポジションのレイヤーを選択してください。';
        },
        remap_off: function (p) {
            return 'レイヤー「' + p.layer + '」のタイムリマップが有効になっていません。';
        },
        out_of_source: function (p) {
            return 'レイヤー「' + p.layer + '」の素材は ' + Number(p.duration).toFixed(2) + ' 秒ですが、送られてきたキーには素材の ' +
                Number(p.min).toFixed(2) + '〜' + Number(p.max).toFixed(2) + ' 秒が必要です。' +
                '素材が短いか、原点フレームが合っていません。何も変更していません。';
        },
        no_server: function () {
            return 'SyncBridge サーバーが起動していません。Maya のパネルで Connect を押すか、syncbridge-server.cmd で起動してください。';
        }
    };

    // Text for an ExtendScript result {error, user, code, params}: localized when the code is known.
    function userMessage(result) {
        var fn = result.code && MESSAGES[result.code];
        if (fn) {
            try { return fn(result.params || {}); } catch (e) { /* fall back to the English text */ }
        }
        return (result.user ? '' : 'ExtendScript error: ') + result.error;
    }

    function describe(data) {
        var parts = [data.direction || '', data.status || ''];
        var conv = (data.report || {}).conversion;
        if (conv) { parts.push('conversion ' + conv.max_error_frames.toFixed(4) + ' f'); }
        if (data.readback) {
            parts.push('readback ' + data.readback.max_error_frames.toFixed(4) + ' f' +
                (data.readback.passed ? '' : ' FAIL'));
        }
        return parts.filter(function (p) { return p; }).join(' ');
    }

    function SBPanelClient(opts) {
        this.host = opts.host;
        this.WebSocketImpl = opts.WebSocketImpl;
        this.onState = opts.onState || function () {};
        this.onLog = opts.onLog || function () {};
        this.version = opts.version || '';
        this.document = opts.document || '';
        this.ws = null;
        this.clientId = null;
        this.peers = [];
        this.pending = {};
        this.closing = false;
    }

    SBPanelClient.prototype.connected = function () {
        return !!this.clientId && this.ws && this.ws.readyState === 1;
    };

    SBPanelClient.prototype.hasPeer = function (app) {
        return this.peers.some(function (p) { return p.app === app; });
    };

    SBPanelClient.prototype.connect = function (session) {
        var self = this;
        if (this.ws) { return; }
        this.closing = false;
        var ws = new this.WebSocketImpl('ws://127.0.0.1:' + session.port + '/ws');
        this.ws = ws;
        ws.onopen = function () {
            ws.send(JSON.stringify(message('hello', {
                token: session.token, app: 'ae', version: self.version, document: self.document,
                protocol: PROTOCOL_VERSION
            })));
        };
        ws.onmessage = function (ev) { self._onMessage(ev.data); };
        ws.onerror = function () { self.onLog('connection error (is the server running?)'); };
        ws.onclose = function (ev) {
            var reason = self.closing ? 'disconnected by this panel' : 'connection closed (code ' + ev.code + ')';
            self.ws = null;
            self.clientId = null;
            self.peers = [];
            var pending = self.pending;
            self.pending = {};
            Object.keys(pending).forEach(function (id) {
                pending[id](message('error', { code: 'peer_disconnected', message: reason }, id));
            });
            self.onLog(reason);
            self.onState();
        };
    };

    SBPanelClient.prototype.disconnect = function () {
        this.closing = true;
        if (this.ws) { this.ws.close(1000); }
    };

    SBPanelClient.prototype.transfer = function (direction, options, callback) {
        if (!this.connected()) { throw new Error('not connected'); }
        var msg = message('transfer.request', { direction: direction, options: options || {} });
        this.pending[msg.event_id] = callback;
        this.ws.send(JSON.stringify(msg));
        return msg.event_id;
    };

    // Comp guide (D-16): the active comp's size, drawn as a frame in the Maya view.
    // callback(reply) gets guide.result or error; a problem in AE (no comp) comes back
    // as an error message without asking the server.
    SBPanelClient.prototype.sendGuide = function (callback) {
        var self = this;
        if (!this.connected()) { throw new Error('not connected'); }
        this.host.call('compInfo', [], function (comp) {
            if (comp.error) {
                callback(message('error', { code: 'app_error', message: userMessage(comp) }));
                return;
            }
            if (!self.connected()) {
                callback(message('error', { code: 'peer_disconnected', message: 'not connected' }));
                return;
            }
            var msg = message('guide.request', { comp: comp });
            self.pending[msg.event_id] = callback;
            self.ws.send(JSON.stringify(msg));
        });
    };

    // Key markers (D-18): the selected layer's Time Remap keys, marked on the Maya timeline and
    // view. `options` = transfer options (origin, ...). Same reply handling as sendGuide.
    SBPanelClient.prototype.sendMarkers = function (options, callback) {
        var self = this;
        if (!this.connected()) { throw new Error('not connected'); }
        this.host.call('exportSelected', [], function (exported) {
            if (exported.error) {
                callback(message('error', { code: 'app_error', message: userMessage(exported) }));
                return;
            }
            if (!self.connected()) {
                callback(message('error', { code: 'peer_disconnected', message: 'not connected' }));
                return;
            }
            var msg = message('markers.request', { 'export': exported, options: options || {} });
            self.pending[msg.event_id] = callback;
            self.ws.send(JSON.stringify(msg));
        });
    };

    SBPanelClient.prototype._send = function (msg) {
        if (this.ws && this.ws.readyState === 1) { this.ws.send(JSON.stringify(msg)); }
    };

    SBPanelClient.prototype._onMessage = function (text) {
        var msg, cb;
        try { msg = JSON.parse(text); } catch (e) { this.onLog('bad message from the server'); return; }
        if (msg.reply_to && this.pending[msg.reply_to]) {
            cb = this.pending[msg.reply_to];
            delete this.pending[msg.reply_to];
            cb(msg);
            return;
        }
        switch (msg.kind) {
        case 'welcome':
            this.clientId = msg.data.client_id;
            this.onLog('connected as ' + this.clientId);
            this.onState();
            break;
        case 'peers':
            var hadMaya = this.hasPeer('maya');
            this.peers = msg.data.clients || [];
            if (hadMaya !== this.hasPeer('maya')) {
                this.onLog('Maya ' + (this.hasPeer('maya') ? 'connected' : 'disconnected'));
            }
            this.onState();
            break;
        case 'export.request':
            this._export(msg);
            break;
        case 'apply.request':
            this._apply(msg);
            break;
        case 'error':
            this.onLog('error: ' + msg.data.message);
            break;
        default:
            this._send(message('error', { code: 'bad_message', message: 'AE panel cannot handle ' + msg.kind }, msg.event_id));
        }
    };

    SBPanelClient.prototype._hostError = function (request, result) {
        var text = userMessage(result);
        this._send(message('error', { code: 'app_error', message: text }, request.event_id));
        this.onLog(text);
    };

    SBPanelClient.prototype._export = function (request) {
        var self = this;
        this.host.call('exportSelected', [], function (result) {
            if (result.error) { self._hostError(request, result); return; }
            self._send(message('export.result', { 'export': result }, request.event_id));
        });
    };

    SBPanelClient.prototype._apply = function (request) {
        var self = this;
        var env = request.data.apply;
        this.onLog('Maya → AE: confirm the dialog in After Effects...');
        this.host.call('applyEnvelope', [JSON.stringify(env), 'Maya'], function (result) {
            if (result.error) { self._hostError(request, result); return; }
            var reply = { status: result.status };
            if (result.backup) { reply.backup = result.backup; }
            if (result.after) { reply.after = result.after; }
            self._send(message('apply.result', reply, request.event_id));
            self.onLog(result.status === 'applied'
                ? 'Maya → AE applied ' + env.data.keys.length + ' keys. Undo once to revert.'
                : 'Maya → AE cancelled (nothing changed)');
        });
    };

    SBPanelClient.jsxCall = jsxCall;
    SBPanelClient.userMessage = userMessage;
    SBPanelClient.describe = describe;
    SBPanelClient.message = message;
    return SBPanelClient;
}));
