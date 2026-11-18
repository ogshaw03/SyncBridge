/*
 * Switch to a newly installed version without restarting After Effects (D-56).
 *
 * The installer replaces the extension's files while AE runs (H-UPD-1) and writes install.json last.
 * The panel reads install.json through CEP's Node every few seconds. When its version is not the running
 * one and this extension's manifest on disk has that version, a bar with "切り替える" appears:
 *   1. the panel disconnects (opts.beforeSwitch)
 *   2. the host script is evaluated again from the new files ($.evalFile, H-AE-36)
 *   3. the page is loaded again (location.reload, H-AE-37); the new panel connects as it starts
 * CEP reads the manifest only when AE starts: when it changed in more than its version numbers (Node,
 * sizes, a new host), the bar asks to restart AE instead.
 *
 *   SBHotReload.start({log: fn, beforeSwitch: fn, container: element, before: element})
 *   SBHotReload.show({version: '0.1.21', restart: false})   show the bar (mocks, tests)
 */
var SBHotReload = (function () {
    'use strict';

    var CHECK_MS = 3000;
    var HOST_SCRIPT = 'jsx/syncbridge_cep_host.jsx';
    var running = null;               // {version, manifest} of the files this panel was loaded from
    var opts = {};
    var bar = null;
    var shown = null;

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

    function readText(req, file) {
        try {
            return String(req('fs').readFileSync(file, 'utf8')).replace(/^﻿/, '');
        } catch (e) {
            return null;                                         // not there, or being written
        }
    }

    function bundleVersion(manifest) {
        var m = /ExtensionBundleVersion="([^"]+)"/.exec(manifest || '');
        return m ? m[1] : null;
    }

    /* The manifest without its version numbers: what else changed needs AE to start again. */
    function withoutVersion(manifest, version) {
        return String(manifest || '').split('"' + version + '"').join('""');
    }

    /* <install root>/install.json; SYNCBRIDGE_INSTALL_ROOT points elsewhere (the check in docs/VERIFICATION.md) */
    function installRecord(req) {
        var proc = (window.cep_node && window.cep_node.process) || req('process');
        var pathMod = req('path');
        var root = proc.env.SYNCBRIDGE_INSTALL_ROOT ||
                   (proc.env.LOCALAPPDATA ? pathMod.join(proc.env.LOCALAPPDATA, 'Programs', 'SyncBridge') : null);
        if (!root) { return null; }
        var text = readText(req, pathMod.join(root, 'install.json'));
        try {
            return text ? JSON.parse(text) : null;
        } catch (e) {
            return null;
        }
    }

    /* {version, restart} when another version is installed into this extension's folder, else null. */
    function check() {
        var req = nodeRequire();
        var ext = extensionPath();
        if (!req || !ext || !running) { return null; }
        var record = installRecord(req);
        if (!record || !record.version || record.version === running.version) { return null; }
        var manifest = readText(req, req('path').join(ext, 'CSXS', 'manifest.xml'));
        // still being installed, or this panel is not the installed one (the development link)
        if (bundleVersion(manifest) !== record.version) { return null; }
        return {
            version: record.version,
            restart: withoutVersion(manifest, record.version) !== withoutVersion(running.manifest, running.version)
        };
    }

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) { node.className = cls; }
        if (text) { node.textContent = text; }
        return node;
    }

    function show(info) {
        if (!bar) {
            bar = el('div', 'update-bar');
            bar.style.display = 'none';
            var container = opts.container || document.body;
            container.insertBefore(bar, opts.before || container.firstChild);
        }
        var key = info ? info.version + (info.restart ? ' restart' : '') : null;
        if (key === shown) { return; }
        shown = key;
        bar.textContent = '';
        bar.style.display = info ? '' : 'none';
        if (!info) { return; }
        var current = running ? running.version : '?';
        if (info.restart) {
            bar.appendChild(el('div', 'grow', 'SyncBridge ' + info.version + ' がインストールされました（使用中は ' +
                current + '）。この版は After Effects を開き直すと使えます（パネルの設定が変わったため）。'));
            return;
        }
        bar.appendChild(el('div', 'grow', 'SyncBridge ' + info.version + ' がインストールされました（使用中は ' +
            current + '）。'));
        var button = el('button', 'primary', '切り替える');
        button.title = 'After Effects を開き直さずに、インストールした版に切り替えます（パネルを読み込み直して、つなぎ直します）';
        button.onclick = function () {
            button.disabled = true;
            switchNow();
        };
        bar.appendChild(button);
    }

    function log(text) {
        if (opts.log) { opts.log(text); }
    }

    function switchNow() {
        log('新しい版に切り替えています…');
        try {
            if (opts.beforeSwitch) { opts.beforeSwitch(); }
        } catch (e) { /* the page is loaded again anyway */ }
        var cep = window.__adobe_cep__;
        var ext = extensionPath();
        if (!cep || !ext) {
            window.location.reload();
            return;
        }
        var host = (ext + '/' + HOST_SCRIPT).replace(/\\/g, '/');
        var script = 'try { $.evalFile(new File(' + JSON.stringify(host) + ')); "ok"; } ' +
                     'catch (e) { "error: " + e.toString(); }';
        cep.evalScript(script, function (result) {
            if (String(result).indexOf('error') === 0) {
                // reloaded anyway: the new page shows what fails; AE has to be restarted then
                log('AE 側のスクリプトを読み込めませんでした: ' + result);
            }
            window.location.reload();
        });
    }

    function start(options) {
        opts = options || {};
        var req = nodeRequire();
        var ext = extensionPath();
        if (!req || !ext) { return false; }                      // a browser (the mock): no Node
        var manifest = readText(req, req('path').join(ext, 'CSXS', 'manifest.xml'));
        if (!manifest) { return false; }
        running = { version: bundleVersion(manifest), manifest: manifest };
        function tick() {
            try {
                show(check());
            } catch (e) { /* try again on the next tick */ }
        }
        tick();
        setInterval(tick, CHECK_MS);
        return true;
    }

    return { start: start, show: show, check: check, bundleVersion: bundleVersion, withoutVersion: withoutVersion,
             setRunning: function (r) { running = r; } };
}());
