/*
 * About SyncBridge / update, from the panel's menu bar (D-46, TEMPORARY: the update steps may change).
 *
 * The list and the download run in Python (syncbridge.updater, the same as Maya's About window):
 * the installed SyncServer.exe with "update list" / "update install <tag>", or in the development
 * setup (this panel is a link into the repository) the repository's .venv with -m syncbridge.updater.
 * They are started through CEP's Node.js (manifest: --enable-nodejs, H-AE-19) and print JSON lines.
 *
 *   SBAbout.open()            show the window (the menu bar's "SyncBridge について / 更新…")
 *   SBAbout.render(result)    show a "list" result (mocks, tests)
 */
var SBAbout = (function () {
    'use strict';

    var KIND_TEXT = { exe: 'インストーラー', zip: 'zip' };
    var RELATION_TEXT = { current: '使用中', newer: '新しい版', older: '' };
    var PAGE_URL = 'https://github.com/ogshaw03/SyncBridge/releases';

    // -- Node and the updater command -----------------------------------------------------------
    function nodeRequire() {
        if (window.cep_node && window.cep_node.require) { return window.cep_node.require; }
        return typeof require === 'function' ? require : null;
    }

    function extensionPath() {
        var cep = window.__adobe_cep__;
        if (!cep || !cep.getSystemPath) { return null; }
        var path = cep.getSystemPath('extension');               // as CSInterface.getSystemPath
        if (navigator.platform === 'Win32') { path = path.replace('file:///', ''); }
        return decodeURI(path);
    }

    /* {cmd, args, env} of the updater, or null: SYNCBRIDGE_SERVER_EXE, then the repository's .venv when
       this panel is the development link, then the installed SyncServer.exe (client/launcher.py's order). */
    function updaterCommand(req) {
        var fs = req('fs');
        var pathMod = req('path');
        var proc = (window.cep_node && window.cep_node.process) || req('process');
        var env = {};
        Object.keys(proc.env).forEach(function (k) { env[k] = proc.env[k]; });
        ['PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP'].forEach(function (k) { delete env[k]; });
        var exe = env.SYNCBRIDGE_SERVER_EXE;
        if (exe && fs.existsSync(exe)) { return { cmd: exe, args: ['update'], env: env }; }
        var ext = extensionPath();
        if (ext) {
            try {
                var repo = pathMod.dirname(fs.realpathSync(ext));
                var python = pathMod.join(repo, '.venv', 'Scripts', 'python.exe');
                if (fs.existsSync(python) && fs.existsSync(pathMod.join(repo, 'src', 'syncbridge', 'updater'))) {
                    env.PYTHONPATH = pathMod.join(repo, 'src');
                    return { cmd: python, args: ['-m', 'syncbridge.updater'], env: env };
                }
            } catch (e) { /* not the development link */ }
        }
        exe = pathMod.join(env.LOCALAPPDATA || '', 'Programs', 'SyncBridge', 'server', 'SyncServer.exe');
        return fs.existsSync(exe) ? { cmd: exe, args: ['update'], env: env } : null;
    }

    /* Run the updater; onLine(obj) for each JSON line, onExit(code). Returns an error text or null. */
    function runUpdater(args, onLine, onExit) {
        var req = nodeRequire();
        if (!req) { return 'この画面では使えません（After Effects の中で開いてください）。'; }
        var command = updaterCommand(req);
        if (!command) {
            return 'SyncBridge のインストール先が見つかりません（%LOCALAPPDATA%\\Programs\\SyncBridge）。' +
                'インストーラーか Install.bat でインストールし直してください。';
        }
        var child = req('child_process').spawn(command.cmd, command.args.concat(args),
                                               { env: command.env, windowsHide: true });
        var buffer = '';
        child.stdout.on('data', function (data) {
            buffer += data.toString('utf8');
            var lines = buffer.split(/\r?\n/);
            buffer = lines.pop();
            lines.forEach(function (line) {
                if (!line) { return; }
                try { onLine(JSON.parse(line)); } catch (e) { /* not ours */ }
            });
        });
        child.on('error', function (e) { onLine({ error: '更新の処理を起動できませんでした: ' + e.message }); });
        child.on('close', function (code) { onExit(code); });
        return null;
    }

    function openPage(url) {
        if (window.cep && window.cep.util && window.cep.util.openURLInDefaultBrowser) {
            window.cep.util.openURLInDefaultBrowser(url);
            return;
        }
        window.open(url);
    }

    // -- the window ----------------------------------------------------------------------------
    var state = { result: null, selected: 0, busy: false };
    var nodes = null;

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) { node.className = cls; }
        if (text !== undefined) { node.textContent = text; }
        return node;
    }

    function build() {
        var overlay = el('div', 'about-overlay');
        var box = el('div', 'about');
        var head = el('div', 'row');
        var logo = el('img', 'logo');
        logo.src = 'img/syncbridge_logo.png';
        var title = el('div', 'grow');
        var name = el('b', null, 'SyncBridge ');
        var version = el('span', 'muted', '');
        title.appendChild(name);
        title.appendChild(version);
        title.appendChild(el('div', 'muted', 'Maya と After Effects をつなぐツール'));
        var close = el('button', null, '閉じる');
        close.onclick = function () { overlay.style.display = 'none'; };
        head.appendChild(logo);
        head.appendChild(title);
        head.appendChild(close);
        var list = el('div', 'about-list');
        var notes = el('div', 'about-notes muted');
        var status = el('div', 'about-status muted');
        var confirmBox = el('div', 'about-confirm');
        var update = el('button', 'primary', 'インストール');
        var page = el('button', null, 'リリースのページ');
        var reload = el('button', null, '再読み込み');
        update.onclick = askUpdate;
        page.onclick = function () { openPage((state.result && state.result.page) || PAGE_URL); };
        reload.onclick = load;
        var buttons = el('div', 'row');
        [update, page, reload].forEach(function (b) { buttons.appendChild(b); });
        [head, el('div', 'section-title', 'GitHub のリリース'), list, notes, status, confirmBox, buttons]
            .forEach(function (n) { box.appendChild(n); });
        overlay.appendChild(box);
        document.body.appendChild(overlay);
        nodes = { overlay: overlay, version: version, list: list, notes: notes, status: status,
                  confirm: confirmBox, buttons: buttons, update: update, reload: reload };
    }

    function say(text, warn) {
        nodes.status.textContent = text;
        nodes.status.className = 'about-status ' + (warn ? 'warn' : 'muted');
    }

    function selected() {
        var items = (state.result && state.result.releases) || [];
        return items[state.selected] || null;
    }

    function showButtons() {
        var item = selected();
        nodes.update.disabled = state.busy || !item || !item.asset || item.relation === 'current';
        nodes.reload.disabled = state.busy;
        nodes.notes.textContent = item ? (item.notes || '') : '';
    }

    function render(result) {
        if (!nodes) { build(); }
        state.result = result;
        state.selected = 0;
        nodes.version.textContent = result.current || '';
        nodes.list.textContent = '';
        nodes.confirm.textContent = '';
        nodes.buttons.style.display = '';
        var items = result.releases || [];
        items.forEach(function (item, index) {
            var row = el('div', 'about-row' + (item.relation === 'current' ? ' current' : ''));
            row.appendChild(el('span', 'v', item.version));
            row.appendChild(el('span', 'd', item.date || ''));
            row.appendChild(el('span', 'k', item.asset ? KIND_TEXT[item.asset.kind] : '（なし）'));
            row.appendChild(el('span', 'r', RELATION_TEXT[item.relation] || ''));
            row.onclick = function () {
                state.selected = index;
                Array.prototype.forEach.call(nodes.list.childNodes, function (n, i) {
                    n.className = n.className.replace(' selected', '') + (i === index ? ' selected' : '');
                });
                nodes.confirm.textContent = '';
                nodes.buttons.style.display = '';
                showButtons();
            };
            if (index === 0) { row.className += ' selected'; }
            nodes.list.appendChild(row);
        });
        var newer = items.filter(function (i) { return i.relation === 'newer'; });
        if (!items.length) { say('GitHub にリリースがありません。'); }
        else if (newer.length) { say('新しい版があります: ' + newer[0].version); }
        else { say('使用中の ' + (result.current || '') + ' が最新です（古い版に戻すこともできます）。'); }
        nodes.overlay.style.display = '';
        showButtons();
    }

    function load() {
        if (!nodes) { build(); }
        nodes.overlay.style.display = '';
        state.busy = true;
        showButtons();
        say('GitHub からリリースの一覧を取得しています…');
        var got = null;
        var error = runUpdater(['list'], function (obj) {
            if (obj.error) { say(obj.error, true); } else if (obj.releases) { got = obj; }
        }, function () {
            state.busy = false;
            if (got) { render(got); } else { showButtons(); }
        });
        if (error) {
            state.busy = false;
            say(error, true);
            showButtons();
        }
    }

    function confirmText(item) {
        var older = item.relation === 'older';
        var lines = ['SyncBridge ' + item.version + ' をインストールします（今は ' + (state.result.current || '?') +
                     (older ? '。古い版に戻ります' : '') + '）。'];
        if (item.asset.kind === 'exe') {
            lines.push('インストーラーをダウンロードして開きます。インストーラーが開いたら、After Effects と Maya を終了してから' +
                       '「インストール」を押してください。');
        } else {
            lines.push('zip をダウンロードして展開し、Install.bat を実行します（すぐにインストールが始まります）。' +
                       '終わったら After Effects と Maya を再起動してください。');
        }
        lines.push('インストール中は SyncBridge のサーバーが止まり、接続が切れます。');
        if (item.has_updater === false) {
            lines.push('※ ' + item.version + ' にはこの更新のメニューがありません。あとで新しい版にするときは、' +
                       'インストーラーか zip を自分で実行してください。');
        }
        return lines;
    }

    function askUpdate() {
        var item = selected();
        if (!item || !item.asset) { return; }
        nodes.confirm.textContent = '';
        confirmText(item).forEach(function (line) { nodes.confirm.appendChild(el('div', null, line)); });
        var row = el('div', 'row');
        var ok = el('button', 'primary', 'インストール');
        var cancel = el('button', null, 'やめる');
        function closeConfirm() {
            nodes.confirm.textContent = '';
            nodes.buttons.style.display = '';
        }
        ok.onclick = function () { closeConfirm(); runInstall(item); };
        cancel.onclick = closeConfirm;
        nodes.buttons.style.display = 'none';             // one "インストール" at a time
        row.appendChild(ok);
        row.appendChild(cancel);
        nodes.confirm.appendChild(row);
    }

    function runInstall(item) {
        state.busy = true;
        showButtons();
        say(item.asset.name + ' をダウンロードしています…');
        var launched = null;
        var failed = false;
        var error = runUpdater(['install', item.tag], function (obj) {
            if (obj.error) { failed = true; say(obj.error, true); }
            else if (obj.progress) {
                say('ダウンロード中 ' + (obj.progress[0] / 1e6).toFixed(1) + ' / ' + (obj.progress[1] / 1e6).toFixed(1) + ' MB');
            } else if (obj.launching) { launched = obj.launching; }
        }, function () {
            state.busy = false;
            showButtons();
            if (failed) { return; }
            if (launched === 'exe') {
                say('インストーラーを開きました。After Effects と Maya を終了してから「インストール」を押し、終わったら起動し直してください。');
            } else if (launched === 'zip') {
                say('インストールを始めました。完了のメッセージが出たら、After Effects と Maya を再起動してください。');
            } else {
                say('更新を始められませんでした。', true);
            }
        });
        if (error) {
            state.busy = false;
            say(error, true);
            showButtons();
        }
    }

    return { open: load, render: render, confirmText: confirmText };
}());
