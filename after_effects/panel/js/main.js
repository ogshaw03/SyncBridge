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
        logo: el('img', { 'class': 'logo', src: 'img/syncbridge_logo.png', alt: '', title: 'SyncBridge' }),
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
        markers: el('button', { title: '選択中のレイヤーのタイムリマップのキーの位置を、Maya のタイムスライダー（ブックマーク）と' +
                                       'ビューにマーカーで表示します。Maya のシーンに保存されます（Origin frame を使います）',
                                text: 'キーのマーカーを Maya へ' }),
        // scene settings (D-21) and time slider sync (D-22)
        settingChecks: {},
        settingsToAe: el('button', { 'class': 'half', text: '設定 Maya → AE',
                                     title: 'Maya のシーンの設定（チェックした項目）を、このコンプに適用します（確認してから適用）' }),
        settingsToMaya: el('button', { 'class': 'half', text: '設定 AE → Maya',
                                       title: 'このコンプの設定（チェックした項目）を、Maya のシーンに送ります（Maya で確認してから適用）' }),
        timeSync: el('input', { type: 'checkbox' }),
        follow: el('input', { type: 'checkbox' }),
        log: el('div', { id: 'log' })
    };
    var SETTING_ITEMS = [['fps', 'FPS'], ['playback_range', '再生範囲'],
                         ['animation_range', 'アニメーション範囲'], ['pixel_aspect', 'ピクセル縦横比']];

    function check(input, text, title) {
        return el('label', { 'class': 'check', title: title || '' }, [input, el('span', { text: text })]);
    }

    var checks = el('div', { 'class': 'checks' });
    SETTING_ITEMS.forEach(function (item) {
        var input = el('input', { type: 'checkbox' });
        input.checked = true;
        ui.settingChecks[item[0]] = input;
        checks.appendChild(check(input, item[1]));
    });
    var syncSection = el('div', { 'class': 'section' }, [
        el('div', { 'class': 'section-title', text: 'シーン設定と時間の同期' }),
        checks,
        el('div', { 'class': 'row' }, [ui.settingsToAe, ui.settingsToMaya]),
        el('div', { 'class': 'row' }, [
            check(ui.timeSync, 'タイムスライダーを同期',
                  'Maya と AE のどちらで時間を動かしても、もう片方が同じ時間に移ります（Maya のパネルと共通のスイッチ。' +
                  'Maya の Origin frame = このコンプの 0 秒）'),
            check(ui.follow, 'Maya の再生中も追従', 'オフ: Maya の再生中は送らず、止めた位置だけを送ります')
        ])
    ]);

    var app = document.getElementById('app');
    [
        el('div', { 'class': 'row' }, [ui.logo, ui.status, ui.connect]),
        ui.peer,
        el('div', { 'class': 'row' }, [ui.target, ui.refresh]),
        field('Mode', ui.mode),
        field('Origin frame (Maya)', ui.origin),
        field('Tolerance (frames)', ui.tolerance),
        el('div', { 'class': 'row' }, [ui.toAe, ui.toMaya]),
        el('div', { 'class': 'row' }, [ui.guide, ui.markers]),
        syncSection,
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
            if (saved.settingItems) {
                SETTING_ITEMS.forEach(function (item) {
                    ui.settingChecks[item[0]].checked = saved.settingItems.indexOf(item[0]) >= 0;
                });
            }
        } catch (e) { /* storage unavailable: defaults */ }
    }

    function settingItems() {
        return SETTING_ITEMS.map(function (item) { return item[0]; })
            .filter(function (name) { return ui.settingChecks[name].checked; });
    }

    function saveOptions() {
        try {
            window.localStorage.setItem(STORE_KEY, JSON.stringify({
                mode: ui.mode.value, origin: ui.origin.value, tolerance: ui.tolerance.value,
                settingItems: settingItems() }));
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
        onTimeSync: function (state) {
            log('タイムスライダーの同期: ' + (state.enabled ? 'オン' + (state.follow_playback ? '（Maya の再生中も追従）' : '') : 'オフ'));
            refresh();
        },
        onSettingsApplied: function (status, plan) {
            log(status === 'applied'
                ? 'Maya の設定をこのコンプに適用しました: ' + SBPanelClient.describeChanges(plan.changes) + '。元に戻すときは取り消しを 1 回。'
                : 'Maya → AE の設定はキャンセルしました（何も変更していません）');
        },
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
        ui.markers.disabled = !enabled;
        var settingsEnabled = connected && maya.length > 0 && compOk && !busy;
        ui.settingsToAe.disabled = !settingsEnabled;
        ui.settingsToMaya.disabled = !settingsEnabled;
        ui.timeSync.disabled = !connected;
        ui.follow.disabled = !connected;
        ui.timeSync.checked = client.timeSync.enabled;
        ui.follow.checked = client.timeSync.follow_playback;
        ui.timeSync.parentNode.classList.toggle('sync-on', client.timeSync.enabled);
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

    function sendMarkers() {
        saveOptions();
        busy = true;
        refresh();
        try {
            client.sendMarkers({ origin: parseFloat(ui.origin.value) }, function (reply) {
                busy = false;
                if (reply.kind === 'error') {
                    log('キーのマーカーを送れませんでした: ' + reply.data.message);
                } else {
                    var d = reply.data;
                    log('キーのマーカー ' + d.count + ' 個を Maya に送りました（フレーム ' + d.first + '〜' + d.last +
                        '、タイムスライダーのブックマーク付き。Maya のシーンに保存されます）');
                }
                refresh();
            });
        } catch (e) {
            busy = false;
            log('キーのマーカーを送れませんでした: ' + e.message);
            refresh();
        }
    }

    function sendSettings(direction) {
        var items = settingItems();
        saveOptions();
        if (!items.length) { log('送る設定を 1 つ以上チェックしてください。'); return; }
        busy = true;
        refresh();
        log(direction === 'maya2ae' ? '設定 Maya → AE: 確認ダイアログを待っています...'
                                    : '設定 AE → Maya: Maya で確認してください...');
        try {
            client.sendSettings(direction, items, { origin: parseFloat(ui.origin.value) }, function (reply) {
                busy = false;
                var arrow = direction === 'maya2ae' ? 'Maya → AE' : 'AE → Maya';
                if (reply.kind === 'error') {
                    log('設定を送れませんでした: ' + reply.data.message);
                } else if (reply.data.status === 'applied') {
                    log('設定 ' + arrow + ' を適用しました: ' + SBPanelClient.describeChanges(reply.data.changes));
                    if (reply.data.message) { log(reply.data.message); }
                } else if (reply.data.status === 'unchanged') {
                    log('設定 ' + arrow + ': ' + (reply.data.message || '変更はありません。'));
                } else {
                    log('設定 ' + arrow + ' はキャンセルされました（何も変更していません）');
                }
                ((reply.data || {}).warnings || []).forEach(function (w) { log('注意: ' + w); });
                refresh();
            });
        } catch (e) {
            busy = false;
            log('設定を送れませんでした: ' + e.message);
            refresh();
        }
    }

    function switchTimeSync(enabled) {
        try {
            client.setTimeSync(enabled, ui.follow.checked);
        } catch (e) {
            log('タイムスライダーの同期を切り替えられませんでした: ' + e.message);
        }
        refresh();
    }

    ui.settingsToAe.addEventListener('click', function () { sendSettings('maya2ae'); });
    ui.settingsToMaya.addEventListener('click', function () { sendSettings('ae2maya'); });
    ui.timeSync.addEventListener('change', function () { switchTimeSync(ui.timeSync.checked); });
    ui.follow.addEventListener('change', function () { client.setFollowPlayback(ui.follow.checked); });
    Object.keys(ui.settingChecks).forEach(function (name) {
        ui.settingChecks[name].addEventListener('change', saveOptions);
    });
    ui.guide.addEventListener('click', sendGuide);
    ui.markers.addEventListener('click', sendMarkers);
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
