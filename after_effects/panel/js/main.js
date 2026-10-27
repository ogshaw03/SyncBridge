/*
 * SyncBridge panel UI: builds the panel and connects SBPanelClient to CEP.
 * Layout (UI/UX proposal, 2026-10-27): state, the selected layer, Origin frame, then the sections
 * time warp / send to Maya / sync / scene settings. Mode and Tolerance are folded under "詳細".
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

    function section(title, children) {
        return el('div', { 'class': 'section' }, [el('div', { 'class': 'section-title', text: title })].concat(children));
    }

    var ui = {
        connect: el('button', { text: '接続' }),
        logo: el('img', { 'class': 'logo', src: 'img/syncbridge_logo.png', alt: '', title: 'SyncBridge' }),
        // state: one look tells what is connected and what is on
        serverState: el('span', { 'class': 'off', text: 'サーバー: 未接続' }),
        mayaState: el('span', { 'class': 'off', text: 'Maya: -' }),
        timeState: el('span', { 'class': 'off', text: 'タイムスライダー同期' }),
        liveState: el('span', { 'class': 'off', text: 'リアルタイム同期' }),
        targetName: el('b', { text: '-' }),
        targetNote: el('span', { 'class': 'muted' }),
        refresh: el('button', { title: '選択中のコンポとレイヤーを読み直す', text: '↻' }),
        mode: el('select', {}, [el('option', { value: 'editable', text: 'editable' }),
                               el('option', { value: 'precision', text: 'precision' })]),
        origin: el('input', { type: 'number', step: '1', value: '1',
                              title: 'このコンポの 0 秒にあたる Maya のフレーム（ふつうはレンダーの開始フレーム）。' +
                                     'Maya のシーンに保存され、Maya のパネルと共通です（どちらで変えても両方に反映）' }),
        tolerance: el('input', { type: 'number', step: '0.05', min: '0.001', value: '0.1' }),
        detail: el('details', { 'class': 'fold' }),
        detailSummary: el('summary'),
        toAe: el('button', { 'class': 'send primary', text: '← Maya から読み込む',
                             title: 'Maya の Scene Time Warp を、選択中のレイヤーのタイムリマップにします（確認してから適用）' }),
        toMaya: el('button', { 'class': 'send primary', text: 'Maya へ送る →',
                               title: '選択中のレイヤーのタイムリマップを、Maya の Scene Time Warp にします（Maya で確認してから適用）' }),
        pixelMap: el('button', { 'class': 'full', text: 'レイヤーの初期位置を Maya へ',
                                 title: '選択中のレイヤーの今の位置を、Maya のレイヤーマップでつないだカメラの基準にします' +
                                        '（Pixel Mapping。相対モードの最初の 1 回は基準の記録、そのあとは位置の差をカメラに足します）' }),
        guide: el('button', { 'class': 'half', text: '解像度の枠',
                              title: 'アクティブなコンポの幅と高さを、Maya のビューに枠で表示します（レンダー解像度の中央に等倍）' }),
        markers: el('button', { 'class': 'half', text: 'キーのマーカー',
                                title: '選択中のレイヤーのタイムリマップのキーの位置を、Maya のタイムスライダー（ブックマーク）と' +
                                       'ビューにマーカーで表示します。Maya のシーンに保存されます（Origin frame を使います）' }),
        // scene settings (D-21) and time slider sync (D-22)
        settingChecks: {},
        settingsToAe: el('button', { 'class': 'half', text: '← Maya から',
                                     title: 'Maya のシーンの設定（チェックした項目）を、このコンポに適用します（確認してから適用）' }),
        settingsToMaya: el('button', { 'class': 'half', text: 'Maya へ →',
                                       title: 'このコンポの設定（チェックした項目）を、Maya のシーンに送ります（Maya で確認してから適用）' }),
        timeSync: el('input', { type: 'checkbox' }),
        liveSync: el('input', { type: 'checkbox' }),      // D-41
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
    ui.detail.appendChild(ui.detailSummary);
    ui.detail.appendChild(field('モード', ui.mode));
    ui.detail.appendChild(field('許容誤差（フレーム）', ui.tolerance));

    var app = document.getElementById('app');
    [
        el('div', { 'class': 'row' }, [ui.logo, el('b', { 'class': 'grow', text: 'SyncBridge' }), ui.connect]),
        el('div', { 'class': 'state' }, [ui.serverState, ui.mayaState, ui.timeState, ui.liveState]),
        el('div', { 'class': 'target row' }, [
            el('div', { 'class': 'grow' }, [el('span', { text: '選択中 ' }), ui.targetName, el('br'), ui.targetNote]),
            ui.refresh]),
        field('Origin frame', ui.origin),
        el('div', { 'class': 'muted note', text: '＝ このコンポの 0 秒（Maya と共通）' }),
        section('タイムワープ（選択中のレイヤーのタイムリマップ）', [
            el('div', { 'class': 'row' }, [ui.toAe, ui.toMaya]),
            ui.detail]),
        section('Maya へ送る', [
            ui.pixelMap,
            el('div', { 'class': 'row' }, [ui.guide, ui.markers])]),
        section('同期', [
            el('div', { 'class': 'row' }, [
                check(ui.timeSync, 'タイムスライダー',
                      'Maya と AE のどちらで時間を動かしても、もう片方が同じ時間に移ります（Maya のパネルと共通のスイッチ。' +
                      'Maya の Origin frame = このコンポの 0 秒）'),
                check(ui.follow, 'Maya の再生中も追従', 'オフ: Maya の再生中は送らず、止めた位置だけを送ります')]),
            check(ui.liveSync, 'リアルタイム同期（AE → Maya）',
                  'Maya のレイヤーマップでつないだレイヤーを見張り、位置・キーを変え終えたら、Maya の専用カメラに自動で反映します' +
                  '（Maya のパネル・レイヤーマップ・ビューアーと共通のスイッチ）')]),
        section('シーン設定', [
            checks,
            el('div', { 'class': 'row' }, [ui.settingsToAe, ui.settingsToMaya])]),
        ui.log
    ].forEach(function (node) { app.appendChild(node); });

    function log(text) {
        var line = el('div', { text: new Date().toLocaleTimeString() + '  ' + text });
        ui.log.appendChild(line);
        while (ui.log.childNodes.length > 300) { ui.log.removeChild(ui.log.firstChild); }
        ui.log.scrollTop = ui.log.scrollHeight;
    }

    function showDetail() {
        ui.detailSummary.textContent = '詳細（モード: ' + ui.mode.value + '、許容誤差: ' + ui.tolerance.value + ' フレーム）';
    }

    function showState(node, text, on) {
        node.textContent = text;
        node.className = on ? 'on' : 'off';
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
        showDetail();
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
    var layerSelected = false;
    var compOk = false;
    var client = new SBPanelClient({
        host: host,
        WebSocketImpl: window.WebSocket,
        onLog: log,
        onState: refresh,
        onOrigin: function (origin) {             // the shared Origin frame from Maya's scene (D-38)
            if (parseFloat(ui.origin.value) !== origin) {
                ui.origin.value = String(origin);
                saveOptions();
                log('Origin frame を ' + origin + ' にしました（Maya のシーンと共通）');
            }
        },
        onTimeSync: function (state) {
            log('タイムスライダーの同期: ' + (state.enabled ? 'オン' + (state.follow_playback ? '（Maya の再生中も追従）' : '') : 'オフ'));
            refresh();
        },
        onLiveSync: function (state) {
            log('リアルタイム同期（AE → Maya）: ' + (state.enabled
                ? 'オン（見張るレイヤー ' + state.layers.length + ' 個）' : 'オフ'));
            refresh();
        },
        onSettingsApplied: function (status, plan) {
            log(status === 'applied'
                ? 'Maya の設定をこのコンポに適用しました: ' + SBPanelClient.describeChanges(plan.changes) + '。元に戻すときは取り消しを 1 回。'
                : 'Maya からの設定はキャンセルしました（何も変更していません）');
        },
        document: 'After Effects'
    });

    function refresh() {
        var connected = client.connected();
        showState(ui.serverState, connected ? 'サーバー: 接続中' : 'サーバー: 未接続', connected);
        ui.serverState.title = connected ? 'ID ' + client.clientId : '';
        ui.connect.textContent = connected || client.ws ? '切断' : '接続';
        var maya = connected ? client.peers.filter(function (p) { return p.app === 'maya'; }) : [];
        showState(ui.mayaState, maya.length ? 'Maya: 接続中' : 'Maya: 未接続', maya.length > 0);
        ui.mayaState.title = maya.length ? (maya[maya.length - 1].document || maya[maya.length - 1].client_id) : '';
        var enabled = connected && maya.length > 0 && layerOk && !busy;
        ui.toAe.disabled = !enabled;
        ui.toMaya.disabled = !enabled;
        ui.guide.disabled = !(connected && maya.length > 0 && compOk && !busy);
        ui.markers.disabled = !enabled;
        ui.pixelMap.disabled = !(connected && maya.length > 0 && layerSelected && !busy);
        var settingsEnabled = connected && maya.length > 0 && compOk && !busy;
        ui.settingsToAe.disabled = !settingsEnabled;
        ui.settingsToMaya.disabled = !settingsEnabled;
        ui.timeSync.disabled = !connected;
        ui.follow.disabled = !connected;
        ui.timeSync.checked = client.timeSync.enabled;
        ui.follow.checked = client.timeSync.follow_playback;
        ui.timeSync.parentNode.classList.toggle('sync-on', client.timeSync.enabled);
        showState(ui.timeState, 'タイムスライダー同期', connected && client.timeSync.enabled);
        ui.liveSync.disabled = !(connected && maya.length > 0);
        ui.liveSync.checked = client.liveSync.enabled;
        ui.liveSync.parentNode.classList.toggle('sync-on', client.liveSync.enabled);
        showState(ui.liveState, 'リアルタイム同期', connected && client.liveSync.enabled);
        if (!connected) { busy = false; }
    }

    function showTarget(name, note) {
        ui.targetName.textContent = name;
        ui.targetNote.textContent = note;
    }

    function updateInfo() {
        host.call('info', [], function (info) {
            if (info.error) {
                showTarget('-', SBPanelClient.userMessage(info));
                layerOk = compOk = layerSelected = false;
                refresh();
                return;
            }
            client.version = info.aeVersion;
            client.document = info.project;
            compOk = !!info.comp;
            layerSelected = !!info.layer;
            if (!info.comp) {
                showTarget('-', 'コンポジションを開いてください');
                layerOk = false;
            } else if (!info.layer) {
                showTarget('-', 'コンポ ' + info.comp.name + '（レイヤーを 1 つ選択してください。' +
                    (info.selectedLayers || 0) + ' 個選択中）');
                layerOk = false;
            } else if (!info.layer.canSetTimeRemapEnabled) {
                showTarget(info.layer.name, 'コンポ ' + info.comp.name + '（タイムリマップを使えないレイヤーです）');
                layerOk = false;
            } else {
                showTarget(info.layer.name, 'コンポ ' + info.comp.name +
                    (info.layer.timeRemapEnabled ? '' : '（タイムリマップ無効: 適用時に有効化）'));
                layerOk = true;
            }
            refresh();
        });
    }

    function connect() {
        host.call('readSession', [], function (session) {
            if (session.error) { log(SBPanelClient.userMessage(session)); return; }
            log('サーバー（ポート ' + session.port + '）に接続しています...');
            client.connect(session);
            refresh();
        });
    }

    function transfer(direction) {
        saveOptions();
        busy = true;
        refresh();
        log(direction === 'maya2ae' ? 'Maya から読み込み: 確認ダイアログを待っています...'
                                    : 'Maya へ送る: Maya で確認してください...');
        try {
            client.transfer(direction, options(), function (reply) {
                busy = false;
                if (reply.kind === 'error') {
                    log('転送できませんでした: ' + reply.data.message);
                } else {
                    log(SBPanelClient.describe(reply.data));
                    if (reply.data.message) { log(reply.data.message); }
                    ((reply.data.report || {}).warnings || []).forEach(function (w) { log('注意: ' + w); });
                }
                refresh();
            });
        } catch (e) {
            busy = false;
            log('転送を始められませんでした: ' + e.message);
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
        log(direction === 'maya2ae' ? '設定を Maya から: 確認ダイアログを待っています...'
                                    : '設定を Maya へ: Maya で確認してください...');
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

    function sendPixelMap() {
        busy = true;
        refresh();
        try {
            client.sendPixelMap({}, function (reply) {
                busy = false;
                var d = reply.data;
                if (reply.kind === 'error') {
                    log('レイヤーの初期位置を送れませんでした: ' + d.message);
                } else if (d.status === 'applied') {
                    log((d.created ? '［新しい対応付け］' : '') + 'レイヤーの位置を Maya のカメラに設定しました: ' + d.mapping.text +
                        '（ずれ ' + d.shift_px[0].toFixed(3) + ', ' + d.shift_px[1].toFixed(3) + ' px）');
                    (d.warnings || []).forEach(function (w) { log('注意: ' + w); });
                } else {
                    log('Maya でキャンセルされました（カメラは変えていません）');
                }
                refresh();
            });
        } catch (e) {
            busy = false;
            log('レイヤーの初期位置を送れませんでした: ' + e.message);
            refresh();
        }
    }

    ui.pixelMap.addEventListener('click', sendPixelMap);
    ui.settingsToAe.addEventListener('click', function () { sendSettings('maya2ae'); });
    ui.settingsToMaya.addEventListener('click', function () { sendSettings('ae2maya'); });
    ui.timeSync.addEventListener('change', function () { switchTimeSync(ui.timeSync.checked); });
    ui.liveSync.addEventListener('change', function () {
        try {
            client.setLiveSync(ui.liveSync.checked);
        } catch (e) {
            log('リアルタイム同期を切り替えられませんでした: ' + e.message);
        }
        refresh();
    });
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
    [ui.mode, ui.tolerance].forEach(function (input) { input.addEventListener('change', showDetail); });
    ui.origin.addEventListener('change', function () {          // one Origin frame with Maya (D-38)
        client.setOrigin(parseFloat(ui.origin.value));
    });

    loadOptions();
    refresh();
    updateInfo();
    setInterval(updateInfo, INFO_INTERVAL_MS);
    connect();
}());
