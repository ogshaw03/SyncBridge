"""Check in After Effects: switch the panel to a newly installed version without restarting AE (D-56;
H-UPD-1 for AE, H-AE-36, H-AE-37).

    py -3 tools\\ae_hot_reload_check.py [--ae "C:\\Program Files\\Adobe\\Adobe After Effects 2027\\Support Files\\AfterFX.exe"]

Needs the development setup (tools/dev_env_on.ps1: PlayerDebugMode, the panel folder is a link into this
repository) and After Effects not running. For the check the link is replaced by a real folder (as an
installed panel is); the link is put back at the end, also when the check fails.

1. Version A = this repository's after_effects with a .debug file (remote debugging on port 8099).
2. AE starts with SYNCBRIDGE_INSTALL_ROOT pointing at a temporary install.json (0.1.20 -> nothing to do).
3. While the panel is open, the panel folder is replaced as install.ps1 does (Remove-Item, Expand-Archive)
   with version B (0.1.99, probes in the host script, a panel script and index.html); install.json says 0.1.99.
4. Through the debug port: the bar shows, its button is pressed, the page loads B and the host script of
   B answers. Pictures: probe_results/ae_hot_reload/.
5. AE (started here, untitled project) is closed; the link is put back.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXT = os.path.join(os.environ["APPDATA"], "Adobe", "CEP", "extensions", "com.syncbridge.panel")
PORT = 8099
NEW_VERSION = "0.1.99"
OUT = os.path.join(REPO, "probe_results", "ae_hot_reload")
DEBUG_FILE = ('<?xml version="1.0" encoding="UTF-8"?>\n<ExtensionList><Extension Id="com.syncbridge.panel">'
              '<HostList><Host Name="AEFT" Port="%d"/></HostList></Extension></ExtensionList>\n' % PORT)

# Chrome DevTools Protocol from Node (its global WebSocket): evaluate one expression in the panel's page,
# or capture the page. argv: port, "eval" <expression> | "shot" <png path>
CDP_JS = r"""
const [port, mode, arg] = process.argv.slice(2);
(async () => {
  const targets = await (await fetch(`http://localhost:${port}/json`)).json();
  const page = targets.find(t => t.type === 'page') || targets[0];
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((ok, bad) => { ws.onopen = ok; ws.onerror = bad; });
  let id = 0;
  const call = (method, params) => new Promise(ok => {
    const my = ++id;
    ws.addEventListener('message', function on(ev) {
      const m = JSON.parse(ev.data);
      if (m.id === my) { ws.removeEventListener('message', on); ok(m); }
    });
    ws.send(JSON.stringify({id: my, method, params}));
  });
  let out;
  if (mode === 'eval') {
    const r = await call('Runtime.evaluate', {expression: arg, awaitPromise: true, returnByValue: true});
    out = r.result && r.result.result ? r.result.result.value : r;
  } else {
    const r = await call('Page.captureScreenshot', {format: 'png'});
    require('fs').writeFileSync(arg, Buffer.from(r.result.data, 'base64'));
    out = arg;
  }
  process.stdout.write(JSON.stringify(out === undefined ? null : out));
  ws.close();
})().catch(e => { process.stdout.write(JSON.stringify({cdp_error: String(e)})); });
"""

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%s  %s  %s" % ("OK" if ok else "NG", name, detail))
    sys.stdout.flush()


def cdp(js_file, mode, arg):
    out = subprocess.run(["node", js_file, str(PORT), mode, arg], capture_output=True, encoding="utf-8", timeout=60)
    try:
        return json.loads(out.stdout)
    except ValueError:
        return {"cdp_error": out.stdout + out.stderr}


def wait_for_page(timeout):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen("http://localhost:%d/json" % PORT, timeout=2) as r:
                if any(t.get("type") == "page" for t in json.load(r)):
                    return True
        except OSError:
            pass
        time.sleep(2)
    return False


def make_version_b(src, dst):
    shutil.copytree(src, dst)
    manifest = os.path.join(dst, "CSXS", "manifest.xml")
    with open(manifest, encoding="utf-8") as f:
        text = f.read()
    version = re.search(r'ExtensionBundleVersion="([^"]+)"', text).group(1)
    with open(manifest, "w", encoding="utf-8") as f:
        f.write(text.replace('"%s"' % version, '"%s"' % NEW_VERSION))
    with open(os.path.join(dst, "jsx", "syncbridge_cep_host.jsx"), "a", encoding="ascii") as f:
        f.write("\nvar SB_HOTRELOAD_PROBE = '%s';\n" % NEW_VERSION)
    with open(os.path.join(dst, "panel", "js", "hotreload.js"), "a", encoding="utf-8") as f:
        f.write("\nwindow.SB_HOTRELOAD_PROBE_JS = '%s';\n" % NEW_VERSION)
    index = os.path.join(dst, "panel", "index.html")
    with open(index, encoding="utf-8") as f:
        text = f.read()
    with open(index, "w", encoding="utf-8") as f:
        f.write(text.replace("<title>", '<meta name="sb-probe" content="%s">\n  <title>' % NEW_VERSION, 1))
    return version


def write_record(root, version):
    with open(os.path.join(root, "install.json"), "w", encoding="utf-8-sig") as f:
        json.dump({"version": version}, f)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--ae", default=r"C:\Program Files\Adobe\Adobe After Effects 2027\Support Files\AfterFX.exe")
    args = parser.parse_args(argv)
    if subprocess.run(["tasklist", "/FI", "IMAGENAME eq AfterFX.exe"], capture_output=True,
                      encoding="mbcs").stdout.count("AfterFX.exe"):
        print("After Effects is running: close it first.")
        return 2
    link_target = os.path.realpath(EXT)
    if not os.path.isdir(EXT) or os.path.normcase(link_target) == os.path.normcase(EXT):
        print("The panel folder is not the development link (tools/dev_env_on.ps1): nothing changed.")
        return 2
    shutil.rmtree(OUT, True)
    os.makedirs(OUT)
    work = tempfile.mkdtemp(prefix="sb_ae_hot_reload_")
    ae = None
    js_file = os.path.join(work, "cdp.js")
    with open(js_file, "w", encoding="utf-8") as f:
        f.write(CDP_JS)
    try:
        version_a = os.path.join(work, "a")
        shutil.copytree(link_target, version_a, ignore=shutil.ignore_patterns(".debug"))
        with open(os.path.join(version_a, ".debug"), "w", encoding="utf-8") as f:
            f.write(DEBUG_FILE)
        old = make_version_b(version_a, os.path.join(work, "b"))
        zip_b = shutil.make_archive(os.path.join(work, "b"), "zip", os.path.join(work, "b"))
        root = os.path.join(work, "root")
        os.makedirs(root)
        write_record(root, old)

        os.rmdir(EXT)                               # the junction only; its target is untouched
        shutil.copytree(version_a, EXT)
        env = dict(os.environ, SYNCBRIDGE_INSTALL_ROOT=root)
        ae = subprocess.Popen([args.ae], env=env)
        up = wait_for_page(240)
        if not up:
            diag = subprocess.run(["powershell", "-NoProfile", "-Command",
                                   "Get-CimInstance Win32_Process -Filter \"Name='CEPHtmlEngine.exe'\" | "
                                   "ForEach-Object { $_.ProcessId.ToString() + ' ' + $_.CommandLine.Substring(0, "
                                   "[Math]::Min(220, $_.CommandLine.Length)) }; netstat -ano | Select-String LISTENING | "
                                   "Select-String ':80[0-9][0-9] '"], capture_output=True, timeout=60)
            print("NOTE " + diag.stdout.decode("mbcs", "replace").replace("\r\n", " | ")[:1500])
        check("the panel is up (debug port)", up)
        time.sleep(5)
        state = cdp(js_file, "eval", "JSON.stringify({bar: !!document.querySelector('.update-bar') && "
                    "document.querySelector('.update-bar').style.display !== 'none', reload: typeof SBHotReload})")
        check("version A runs, no bar", state == json.dumps({"bar": False, "reload": "object"}), str(state))

        # what install.ps1 does with the AE panel, while the panel is open (H-UPD-1)
        ps = ("$ErrorActionPreference = 'Stop'; $e = '%s'; Remove-Item -Recurse -Force $e; "
              "Expand-Archive -Path '%s' -DestinationPath $e" % (EXT, zip_b))
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=120)
        check("the panel folder is replaced while AE runs (H-UPD-1)", r.returncode == 0,
              (r.stdout + r.stderr).decode("mbcs", "replace").strip()[:300])
        write_record(root, NEW_VERSION)
        time.sleep(6)
        text = cdp(js_file, "eval", "(document.querySelector('.update-bar') || {}).textContent || ''")
        check("the bar shows %s" % NEW_VERSION, isinstance(text, str) and NEW_VERSION in text and u"切り替える" in text,
              str(text))
        cdp(js_file, "shot", os.path.join(OUT, "ae_bar.png"))
        cdp(js_file, "eval", "document.querySelector('.update-bar button').click(); 'clicked'")
        time.sleep(8)
        wait_for_page(30)
        after = cdp(js_file, "eval",
                    "new Promise(ok => window.__adobe_cep__.evalScript('typeof SB_HOTRELOAD_PROBE === \"undefined\" ? "
                    "\"none\" : SB_HOTRELOAD_PROBE', r => ok(JSON.stringify({js: window.SB_HOTRELOAD_PROBE_JS || null, "
                    "html: (document.querySelector('meta[name=sb-probe]') || {}).content || null, host: r, "
                    "bar: !!document.querySelector('.update-bar') && "
                    "document.querySelector('.update-bar').style.display !== 'none'}))))")
        print("NOTE after the switch: %s" % after)
        try:
            got = json.loads(after)
        except (TypeError, ValueError):
            got = {}
        check("the page loaded B's index.html and scripts (H-AE-37)",
              got.get("html") == NEW_VERSION and got.get("js") == NEW_VERSION)
        check("the host script of B runs ($.evalFile, H-AE-36)", got.get("host") == NEW_VERSION)
        check("no bar after the switch", got.get("bar") is False)
        cdp(js_file, "shot", os.path.join(OUT, "ae_after.png"))
    finally:
        if ae is not None:
            ae.kill()
            ae.wait(60)
            time.sleep(5)
        if os.path.isdir(EXT) and not os.path.islink(EXT) and os.path.normcase(os.path.realpath(EXT)) == os.path.normcase(EXT):
            shutil.rmtree(EXT, True)
        if not os.path.exists(EXT):
            subprocess.run(["cmd", "/c", "mklink", "/J", EXT, link_target], capture_output=True)
        restored = os.path.normcase(os.path.realpath(EXT)) == os.path.normcase(link_target)
        print("%s  the development link is back  %s" % ("OK" if restored else "NG", link_target))
        results.append(restored)
        shutil.rmtree(work, True)
    print("RESULT %s" % ("PASS" if all(results) else "FAIL"))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
