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
        no_source: function (p) {
            return 'レイヤー「' + p.layer + '」には画像がありません。BG の画像（フッテージ）のレイヤーを選んでください。';
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

    // Time slider sync (D-22): how often AE's current time is read (0.15 s lagged noticeably,
    // user's test 2026-10-23), and how long reading pauses after Maya moved AE: evalScript calls
    // run one at a time in AE, so a read queued before setTime delays it.
    var TIME_POLL_MS = 50;
    var QUIET_AFTER_SET_MS = 300;

    function SBPanelClient(opts) {
        this.host = opts.host;
        this.WebSocketImpl = opts.WebSocketImpl;
        this.onState = opts.onState || function () {};
        this.onLog = opts.onLog || function () {};
        this.onTimeSync = opts.onTimeSync || function () {};
        this.onSettingsApplied = opts.onSettingsApplied || function () {};
        this.setInterval = opts.setInterval || function (fn, ms) { return setInterval(fn, ms); };
        this.clearInterval = opts.clearInterval || function (id) { clearInterval(id); };
        this.now = opts.now || function () { return Date.now(); };
        this._quietUntil = 0;
        this.stats = {};                // delays in ms while the sync is on (reported when it is switched off)
        this._lastPollStart = null;
        this.version = opts.version || '';
        this.document = opts.document || '';
        this.ws = null;
        this.clientId = null;
        this.peers = [];
        this.pending = {};
        this.closing = false;
        this.timeSync = { enabled: false, follow_playback: false };
        this._timer = null;
        this._polling = false;
        this._setting = false;
        this._wantTime = null;
        this._lastApplied = null;
        this._lastSent = null;
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
            self._setTimeState({ enabled: false, follow_playback: false });
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

    // Pixel Mapping (D-24): the selected BG layer's position at the current time, put on the Maya camera
    // mapped to it. options {method?} (used when Maya makes the mapping). Same reply handling as sendGuide.
    SBPanelClient.prototype.sendPixelMap = function (options, callback) {
        var self = this;
        if (!this.connected()) { throw new Error('not connected'); }
        this.host.call('pixelMapInfo', [], function (info) {
            if (info.error) {
                callback(message('error', { code: 'app_error', message: userMessage(info) }));
                return;
            }
            if (!self.connected()) {
                callback(message('error', { code: 'peer_disconnected', message: 'not connected' }));
                return;
            }
            var msg = message('pixelmap.request', { info: info, options: options || {} });
            self.pending[msg.event_id] = callback;
            self.ws.send(JSON.stringify(msg));
        });
    };

    // Scene settings (D-21): FPS / ranges / pixel aspect between Maya and the active comp.
    // direction 'maya2ae' | 'ae2maya'; items: subset of fps, playback_range, animation_range,
    // pixel_aspect; options {origin}. callback(reply) gets settings.result or error.
    SBPanelClient.prototype.sendSettings = function (direction, items, options, callback) {
        if (!this.connected()) { throw new Error('not connected'); }
        var msg = message('settings.request', { direction: direction, items: items, options: options || {} });
        this.pending[msg.event_id] = callback;
        this.ws.send(JSON.stringify(msg));
        return msg.event_id;
    };

    // Time slider sync (D-22): one switch shared with Maya through the hub. Switching it on
    // here makes AE's current time lead.
    SBPanelClient.prototype.setTimeSync = function (enabled, followPlayback) {
        if (!this.connected()) { throw new Error('not connected'); }
        this._send(message('time.sync', { enabled: !!enabled, follow_playback: !!followPlayback }));
        if (enabled) { this._lastSent = null; this._lastApplied = null; this._pollTime(true); }
    };

    SBPanelClient.prototype.setFollowPlayback = function (followPlayback) {
        if (!this.connected() || !this.timeSync.enabled) { return; }
        this._send(message('time.sync', { enabled: true, follow_playback: !!followPlayback }));
    };

    SBPanelClient.prototype._setTimeState = function (state) {
        var wasOn = this.timeSync.enabled;
        this.timeSync = { enabled: !!state.enabled, follow_playback: !!state.follow_playback, by: state.by || null };
        if (this.timeSync.enabled && !this._timer) {
            var self = this;
            this._timer = this.setInterval(function () { self._pollTime(false); }, TIME_POLL_MS);
        } else if (!this.timeSync.enabled && this._timer) {
            this.clearInterval(this._timer);
            this._timer = null;
        }
        if (wasOn !== this.timeSync.enabled || state.by !== undefined) { this.onTimeSync(this.timeSync); }
        if (wasOn && !this.timeSync.enabled) {
            var summary = this.statsSummary();
            if (summary) { this.onLog('同期の計測（AE）: ' + summary); }
            this.stats = {};
            this._lastPollStart = null;
        }
    };

    // Measured delays (D-22; the user felt a lag in both directions, 2026-10-23).
    var STAT_LABELS = [['recv', 'Maya から受け取るまで'], ['set', 'AE で時間を設定'],
                       ['read', 'AE の時間の読み取り'], ['gap', '読みに行った間隔']];

    SBPanelClient.prototype._stat = function (name, ms) {
        var list = this.stats[name] || (this.stats[name] = []);
        list.push(ms);
        if (list.length > 500) { list.shift(); }
    };

    SBPanelClient.prototype.statsSummary = function () {
        var self = this;
        return STAT_LABELS.filter(function (s) { return (self.stats[s[0]] || []).length; }).map(function (s) {
            var v = self.stats[s[0]], sum = v.reduce(function (a, b) { return a + b; }, 0);
            return s[1] + ' 平均 ' + Math.round(sum / v.length) + ' ms（最大 ' +
                Math.round(Math.max.apply(null, v)) + '、' + v.length + ' 回）';
        }).join('、');
    };

    // Read AE's current time; send it when the user moved it (not when SyncBridge set it).
    SBPanelClient.prototype._pollTime = function (force) {
        var self = this;
        if (this._polling || this._setting) { return; }
        if (!force && this.now() < this._quietUntil) { return; }      // Maya is leading right now
        this._polling = true;
        var started = this.now();
        if (!force && this._lastPollStart !== null) { this._stat('gap', started - this._lastPollStart); }
        this._lastPollStart = started;
        this.host.call('compTime', [], function (r) {
            self._polling = false;
            self._stat('read', self.now() - started);
            if (r.error || r.time === null || r.time === undefined) { return; }
            if (!force && !self.timeSync.enabled) { return; }
            var half = (r.frameDuration || 1 / 24) / 2;
            if (!force && self._lastApplied !== null) {
                if (Math.abs(r.time - self._lastApplied) < half) { return; }     // still where Maya put it
                self._lastApplied = null;
            }
            if (!force && self._lastSent !== null && Math.abs(r.time - self._lastSent) < half) { return; }
            self._lastSent = r.time;
            self._send(message('time.update', { t: r.time, sent_at: self.now() }));
        });
    };

    // time.set from Maya: move AE's current time (only the latest one is applied).
    SBPanelClient.prototype._applyTime = function (t, sentAt) {
        var self = this;
        if (!this.timeSync.enabled) { return; }
        if (sentAt) { this._stat('recv', this.now() - sentAt); }
        this._wantTime = t;
        this._quietUntil = this.now() + QUIET_AFTER_SET_MS;
        if (this._setting) { return; }
        this._setting = true;
        var started = this.now();
        this.host.call('setTime', [t], function (r) {
            self._setting = false;
            self._stat('set', self.now() - started);
            var now = (r && typeof r.time === 'number') ? r.time : t;
            self._lastApplied = now;
            self._lastSent = now;
            if (self._wantTime !== t) { self._applyTime(self._wantTime); }
        });
    };

    SBPanelClient.prototype._settingsExport = function (request) {
        var self = this;
        this.host.call('sceneSettings', [], function (result) {
            if (result.error) { self._hostError(request, result); return; }
            self._send(message('settings.export.result', { settings: result }, request.event_id));
        });
    };

    SBPanelClient.prototype._settingsApply = function (request) {
        var self = this, plan = request.data.plan;
        this.onLog('Maya → AE の設定: After Effects の確認ダイアログで選んでください...');
        this.host.call('applySceneSettings', [JSON.stringify(plan), request.data.message || ''], function (result) {
            if (result.error) { self._hostError(request, result); return; }
            var reply = { status: result.status };
            if (result.backup) { reply.backup = result.backup; }
            if (result.after) { reply.after = result.after; }
            self._send(message('settings.apply.result', reply, request.event_id));
            self.onSettingsApplied(result.status, plan);
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
        case 'settings.export.request':
            this._settingsExport(msg);
            break;
        case 'settings.apply.request':
            this._settingsApply(msg);
            break;
        case 'time.sync.state':
            this._setTimeState(msg.data);
            break;
        case 'time.set':
            this._applyTime(msg.data.t, msg.data.sent_at);
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

    // 'FPS 24 → 30、再生範囲 1〜48 → 1〜60' from the changes of a settings plan / result.
    function describeChanges(changes) {
        return (changes || []).map(function (c) {
            return c.label + ' ' + c.before + ' → ' + c.after;
        }).join('、') || '変更なし';
    }

    SBPanelClient.describeChanges = describeChanges;
    SBPanelClient.TIME_POLL_MS = TIME_POLL_MS;
    SBPanelClient.QUIET_AFTER_SET_MS = QUIET_AFTER_SET_MS;
    SBPanelClient.jsxCall = jsxCall;
    SBPanelClient.userMessage = userMessage;
    SBPanelClient.describe = describe;
    SBPanelClient.message = message;
    return SBPanelClient;
}));
