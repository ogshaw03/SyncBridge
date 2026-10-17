/*
 * SyncBridge panel UI (Phase 1-C): builds the panel and connects SBPanelClient to CEP.
 *
 * CEP bridge: window.__adobe_cep__.evalScript(script, callback) runs ExtendScript in AE
 * (what CSInterface.evalScript wraps; H-AE-15). Functions are in jsx/syncbridge_cep_host.jsx.
 */
(function () {
    'use strict';

    var STORE_KEY = 'syncbridge.panel.options';
    var INFO_INTERVAL_MS = 3000;

    // -- ExtendScript bridge ----------------------------------------------------
    var host = {
        call: function (name, args, callback) {
            var cep = window.__adobe_cep__;
            if (!cep) {
                callback({ error: 'Not running inside After Effects (CEP)', user: true });
                return;
            }
            cep.evalScript(SBPanelClient.jsxCall(name, args), function (text) {
                var result;
                try {
                    result = JSON.parse(text);
                } catch (e) {
                    result = { error: 'ExtendScript returned: ' + text, user: false };
                }
                callback(result);
            });
        }
    };

    // -- DOM ---------------------------------------------------------------------
    function el(tag, attrs, children) {
        var node = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) {
            if (k === 'text') { node.textContent = attrs[k]; } else { node.setAttribute(k, attrs[k]); }
        });
        (children || []).forEach(function (c) { node.appendChild(c); });
        return node;
    }

    function field(label, input) {
        return el('label', { 'class': 'field' }, [el('span', { text: label }), input]);
    }

    var ui = {
        status: el('span', { 'class': 'grow', text: 'Server: not connected' }),
        connect: el('button', { text: 'Connect' }),
        peer: el('div', { 'class': 'muted', text: 'Maya: -' }),
        target: el('span', { 'class': 'grow muted', text: 'Layer: -' }),
        refresh: el('button', { title: 'Refresh the selected comp and layer', text: '↻' }),
        mode: el('select', {}, [el('option', { value: 'editable', text: 'editable' }),
                               el('option', { value: 'precision', text: 'precision' })]),
        origin: el('input', { type: 'number', step: '1', value: '1',
                              title: 'Maya frame for AE comp time 0 and source time 0 (usually the render start frame)' }),
        tolerance: el('input', { type: 'number', step: '0.05', min: '0.001', value: '0.1' }),
        toAe: el('button', { 'class': 'send', text: 'Maya → AE' }),
        toMaya: el('button', { 'class': 'send', text: 'AE → Maya' }),
        guide: el('button', { title: 'アクティブなコンポの幅と高さを、Maya のビューに枠で表示します（レンダー解像度の中央に等倍）',
                              text: '解像度の枠を Maya へ' }),
        log: el('div', { id: 'log' })
    };

    var app = document.getElementById('app');
    [
        el('div', { 'class': 'row' }, [ui.status, ui.connect]),
        ui.peer,
        el('div', { 'class': 'row' }, [ui.target, ui.refresh]),
        field('Mode', ui.mode),
        field('Origin frame (Maya)', ui.origin),
        field('Tolerance (frames)', ui.tolerance),
        el('div', { 'class': 'row' }, [ui.toAe, ui.toMaya]),
        el('div', { 'class': 'row' }, [ui.guide]),
        ui.log
    ].forEach(function (node) { app.appendChild(node); });

    function log(text) {
        var line = el('div', { text: new Date().toLocaleTimeString() + '  ' + text });
        ui.log.appendChild(line);
        while (ui.log.childNodes.length > 300) { ui.log.removeChild(ui.log.firstChild); }
        ui.log.scrollTop = ui.log.scrollHeight;
    }

    // -- options (per-panel convenience, localStorage) ------------------------------
    function loadOptions() {
        try {
            var saved = JSON.parse(window.localStorage.getItem(STORE_KEY) || '{}');
            if (saved.mode) { ui.mode.value = saved.mode; }
            if (saved.origin !== undefined) { ui.origin.value = saved.origin; }
            if (saved.tolerance !== undefined) { ui.tolerance.value = saved.tolerance; }
        } catch (e) { /* storage unavailable: defaults */ }
    }

    function saveOptions() {
        try {
            window.localStorage.setItem(STORE_KEY, JSON.stringify({
                mode: ui.mode.value, origin: ui.origin.value, tolerance: ui.tolerance.value }));
        } catch (e) { /* ignore */ }
    }

    function options() {
        return { mode: ui.mode.value, origin: parseFloat(ui.origin.value),
                 tolerance_frames: parseFloat(ui.tolerance.value) };
    }

    // -- client ----------------------------------------------------------------------
    var busy = false;
    var layerOk = false;
    var compOk = false;
    var client = new SBPanelClient({
        host: host,
        WebSocketImpl: window.WebSocket,
        onLog: log,
        onState: refresh,
        document: 'After Effects'
    });

    function refresh() {
        var connected = client.connected();
        ui.status.textContent = connected ? 'Server: connected (' + client.clientId + ')' : 'Server: not connected';
        ui.connect.textContent = connected || client.ws ? 'Disconnect' : 'Connect';
        var maya = client.peers.filter(function (p) { return p.app === 'maya'; });
        ui.peer.textContent = !connected ? 'Maya: -'
            : (maya.length ? 'Maya: connected (' + (maya[maya.length - 1].document || maya[maya.length - 1].client_id) + ')'
                           : 'Maya: not connected');
        var enabled = connected && maya.length > 0 && layerOk && !busy;
        ui.toAe.disabled = !enabled;
        ui.toMaya.disabled = !enabled;
        ui.guide.disabled = !(connected && maya.length > 0 && compOk && !busy);
        if (!connected) { busy = false; }
    }

    function updateInfo() {
        host.call('info', [], function (info) {
            if (info.error) {
                ui.target.textContent = SBPanelClient.userMessage(info);
                layerOk = compOk = false;
                refresh();
                return;
            }
            client.version = info.aeVersion;
            client.document = info.project;
            compOk = !!info.comp;
            if (!info.comp) {
                ui.target.textContent = 'コンポジションを開いてください';
                layerOk = false;
            } else if (!info.layer) {
                ui.target.textContent = info.comp.name + ': レイヤーを 1 つ選択してください（' +
                    (info.selectedLayers || 0) + ' 個選択中）';
                layerOk = false;
            } else if (!info.layer.canSetTimeRemapEnabled) {
                ui.target.textContent = info.layer.name + ': タイムリマップを使えないレイヤーです';
                layerOk = false;
            } else {
                ui.target.textContent = info.comp.name + ' / ' + info.layer.name +
                    (info.layer.timeRemapEnabled ? '' : '（タイムリマップ無効: 適用時に有効化）');
                layerOk = true;
            }
            refresh();
        });
    }

    function connect() {
        host.call('readSession', [], function (session) {
            if (session.error) { log(SBPanelClient.userMessage(session)); return; }
            log('connecting to port ' + session.port + '...');
            client.connect(session);
            refresh();
        });
    }

    function transfer(direction) {
        saveOptions();
        busy = true;
        refresh();
        log(direction === 'maya2ae' ? 'Maya → AE requested' : 'AE → Maya requested: confirm in Maya');
        try {
            client.transfer(direction, options(), function (reply) {
                busy = false;
                if (reply.kind === 'error') {
                    log('failed: ' + reply.data.message);
                } else {
                    log(SBPanelClient.describe(reply.data));
                    if (reply.data.message) { log(reply.data.message); }
                    ((reply.data.report || {}).warnings || []).forEach(function (w) { log('warning: ' + w); });
                }
                refresh();
            });
        } catch (e) {
            busy = false;
            log('cannot start the transfer: ' + e.message);
            refresh();
        }
    }

    function sendGuide() {
        busy = true;
        refresh();
        try {
            client.sendGuide(function (reply) {
                busy = false;
                if (reply.kind === 'error') {
                    log('解像度の枠を送れませんでした: ' + reply.data.message);
                } else {
                    var d = reply.data;
                    log('解像度の枠（' + d.comp[0] + 'x' + d.comp[1] + '）を Maya のカメラ ' + d.camera +
                        ' に表示しました（Maya のレンダー ' + d.render[0] + 'x' + d.render[1] + '）');
                    (d.warnings || []).forEach(function (w) { log('注意: ' + w); });
                }
                refresh();
            });
        } catch (e) {
            busy = false;
            log('解像度の枠を送れませんでした: ' + e.message);
            refresh();
        }
    }

    ui.guide.addEventListener('click', sendGuide);
    ui.connect.addEventListener('click', function () {
        if (client.ws) { client.disconnect(); } else { connect(); }
    });
    ui.refresh.addEventListener('click', updateInfo);
    ui.toAe.addEventListener('click', function () { transfer('maya2ae'); });
    ui.toMaya.addEventListener('click', function () { transfer('ae2maya'); });
    [ui.mode, ui.origin, ui.tolerance].forEach(function (input) { input.addEventListener('change', saveOptions); });

    loadOptions();
    refresh();
    updateInfo();
    setInterval(updateInfo, INFO_INTERVAL_MS);
    connect();
}());
