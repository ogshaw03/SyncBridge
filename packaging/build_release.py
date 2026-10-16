"""Build the SyncBridge release (folder + zip) for users without Python or a terminal.

    .venv\\Scripts\\python packaging\\build_release.py [--skip-tests] [--no-timestamp]

Needs: requirements-server.txt + requirements-monitor.txt + requirements-build.txt in .venv, and
packaging/tools/ZXPSignCmd.exe (Adobe CEP-Resources, ZXPSignCMD 4.1.3 x64).

Output (dist/ is not in git):
    dist/SyncBridge-<version>/
        Install.bat, README_SyncBridge.txt
        payload/install.ps1, uninstall.ps1, Uninstall.bat, version.json, README_SyncBridge.txt
        payload/server/SyncServer.exe (+ _internal)        PyInstaller onedir
        payload/app/SyncBridge.exe (+ _internal)           the monitor (PySide6), PyInstaller onedir, windowed
        payload/maya/drag_to_maya_SyncBridge.py/.mel, icons/, scripts/{syncbridge, syncbridge_maya}
        payload/ae/com.syncbridge.panel.zxp                 signed with a self-signed certificate
    dist/SyncBridge-<version>.zip

The self-signed certificate and its password are created once in packaging/local/
(not in git; keep them to sign later versions with the same certificate).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGING = os.path.join(ROOT, "packaging")
LOCAL = os.path.join(PACKAGING, "local")
ZXPSIGN = os.path.join(PACKAGING, "tools", "ZXPSignCmd.exe")
CERT = os.path.join(LOCAL, "syncbridge_selfsigned.p12")
CERT_PASSWORD = os.path.join(LOCAL, "cert_password.txt")
TSA = "http://timestamp.digicert.com"
EXTENSION_ID = "com.syncbridge.panel"
AE_JSX = ("syncbridge_cep_host.jsx", "syncbridge_ae_lib.jsxinc", "syncbridge_json.jsxinc")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def log(text):
    print("[build] " + text, flush=True)


def run(argv, secret=None, **kw):
    shown = ["***" if secret is not None and a == secret else str(a) for a in argv]
    log(" ".join(shown))
    return subprocess.run(argv, check=True, **kw)


def version() -> str:
    with open(os.path.join(ROOT, "version.json"), encoding="utf-8") as f:
        return json.load(f)["version"]


def run_tests():
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=ROOT)


def build_server(payload, work):
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
         "--name", "SyncServer", "--distpath", os.path.join(work, "dist"),
         "--workpath", os.path.join(work, "work"), "--specpath", work,
         "--paths", os.path.join(ROOT, "src"),
         "--collect-submodules", "uvicorn", "--collect-submodules", "websockets",
         os.path.join(PACKAGING, "server_entry.py")], cwd=ROOT, stdout=subprocess.DEVNULL)
    shutil.copytree(os.path.join(work, "dist", "SyncServer"), os.path.join(payload, "server"))


# Not used by the monitor; keeps PyInstaller from pulling them in through optional imports.
MONITOR_EXCLUDES = ("fastapi", "uvicorn", "starlette", "pydantic", "websockets", "httpx", "tkinter",
                    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtSql",
                    "PySide6.QtOpenGL", "PySide6.QtPdf", "PySide6.QtSvg")


def build_monitor(payload, work):
    argv = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
            "--name", "SyncBridge", "--distpath", os.path.join(work, "dist"),
            "--workpath", os.path.join(work, "work"), "--specpath", work,
            "--paths", os.path.join(ROOT, "src")]
    for name in MONITOR_EXCLUDES:
        argv += ["--exclude-module", name]
    run(argv + [os.path.join(PACKAGING, "monitor_entry.py")], cwd=ROOT, stdout=subprocess.DEVNULL)
    shutil.copytree(os.path.join(work, "dist", "SyncBridge"), os.path.join(payload, "app"))


def build_maya(payload):
    maya = os.path.join(payload, "maya")
    scripts = os.path.join(maya, "scripts")
    os.makedirs(scripts)
    for name in ("drag_to_maya_SyncBridge.py", "drag_to_maya_SyncBridge.mel"):
        shutil.copy2(os.path.join(ROOT, "maya_plugin", name), maya)
    shutil.copytree(os.path.join(ROOT, "maya_plugin", "icons"), os.path.join(maya, "icons"), ignore=IGNORE)
    shutil.copytree(os.path.join(ROOT, "maya_plugin", "scripts", "syncbridge_maya"),
                    os.path.join(scripts, "syncbridge_maya"), ignore=IGNORE)
    shutil.copytree(os.path.join(ROOT, "src", "syncbridge"), os.path.join(scripts, "syncbridge"), ignore=IGNORE)


def ensure_certificate():
    if os.path.isfile(CERT) and os.path.isfile(CERT_PASSWORD):
        with open(CERT_PASSWORD, encoding="utf-8") as f:
            return f.read().strip()
    os.makedirs(LOCAL, exist_ok=True)
    password = secrets.token_urlsafe(24)
    run([ZXPSIGN, "-selfSignedCert", "JP", "Tokyo", "SyncBridge", "SyncBridge", password, CERT,
         "-validityDays", "3650"], secret=password, stdout=subprocess.DEVNULL)
    with open(CERT_PASSWORD, "w", encoding="utf-8") as f:
        f.write(password)
    log("created a self-signed certificate in %s (keep it, it is not in git)" % LOCAL)
    return password


def build_ae(payload, work, timestamp):
    if not os.path.isfile(ZXPSIGN):
        raise SystemExit("ZXPSignCmd not found: %s (see the docstring)" % ZXPSIGN)
    stage = os.path.join(work, "ae_stage", EXTENSION_ID)
    ae = os.path.join(ROOT, "after_effects")
    shutil.copytree(os.path.join(ae, "CSXS"), os.path.join(stage, "CSXS"), ignore=IGNORE)
    shutil.copytree(os.path.join(ae, "panel"), os.path.join(stage, "panel"), ignore=IGNORE)
    os.makedirs(os.path.join(stage, "jsx"))
    for name in AE_JSX:
        shutil.copy2(os.path.join(ae, "jsx", name), os.path.join(stage, "jsx", name))
    for dirpath, dirnames, filenames in os.walk(stage):   # signature check fails on links (KnownIssue2024)
        for name in dirnames + filenames:
            if os.path.islink(os.path.join(dirpath, name)):
                raise SystemExit("symbolic link in the extension: %s" % os.path.join(dirpath, name))
    password = ensure_certificate()
    out_dir = os.path.join(payload, "ae")
    os.makedirs(out_dir)
    zxp = os.path.join(out_dir, EXTENSION_ID + ".zxp")
    argv = [ZXPSIGN, "-sign", stage, zxp, CERT, password]
    try:
        run(argv + (["-tsa", TSA] if timestamp else []), secret=password, stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        if not timestamp:
            raise
        log("timestamping failed (offline?); signing without a timestamp")
        if os.path.exists(zxp):
            os.remove(zxp)
        run(argv, secret=password, stdout=subprocess.DEVNULL)
    run([ZXPSIGN, "-verify", zxp], stdout=subprocess.DEVNULL)


def write_text(path, text, bom=False, crlf=False):
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_installer(release, payload, ver):
    src = os.path.join(PACKAGING, "installer")
    for name in ("install.ps1", "uninstall.ps1"):   # PowerShell 5.1 needs the BOM for Japanese text
        write_text(os.path.join(payload, name), read(os.path.join(src, name)), bom=True, crlf=True)
    write_text(os.path.join(release, "Install.bat"), read(os.path.join(src, "Install.bat")), crlf=True)
    write_text(os.path.join(payload, "Uninstall.bat"), read(os.path.join(src, "Uninstall.bat")), crlf=True)
    readme = read(os.path.join(src, "README_SyncBridge.txt")).replace("{version}", ver)
    for folder in (release, payload):
        write_text(os.path.join(folder, "README_SyncBridge.txt"), readme, bom=True, crlf=True)
    shutil.copy2(os.path.join(ROOT, "version.json"), os.path.join(payload, "version.json"))


def make_zip(release):
    archive = release + ".zip"
    base = os.path.dirname(release)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, filenames in os.walk(release):
            for name in filenames:
                full = os.path.join(dirpath, name)
                z.write(full, os.path.relpath(full, base))
    return archive


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--no-timestamp", action="store_true", help="do not timestamp the ZXP signature")
    args = parser.parse_args(argv)

    ver = version()
    dist = os.path.join(ROOT, "dist")
    release = os.path.join(dist, "SyncBridge-%s" % ver)
    work = os.path.join(ROOT, "build", "release")
    for path in (release, release + ".zip", work):
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
    payload = os.path.join(release, "payload")
    os.makedirs(payload)

    if not args.skip_tests:
        run_tests()
    build_server(payload, work)
    build_monitor(payload, work)
    build_maya(payload)
    build_ae(payload, work, timestamp=not args.no_timestamp)
    build_installer(release, payload, ver)
    archive = make_zip(release)
    size = os.path.getsize(archive) / 1e6
    log("done: %s (%.1f MB)" % (archive, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
