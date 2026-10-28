"""Download a release's file and start its installer (D-46, TEMPORARY: the update steps may change).

    path = download(asset, progress=lambda done, total: ...)     # checked against GitHub's SHA-256
    what = launch(path)                                           # the setup's wizard, or the zip's Install.bat

The installer itself does the update, as when the user starts it: it stops the SyncBridge server and
monitor, replaces the files and says to restart Maya and After Effects. Nothing is replaced from here
(Maya and AE keep running the files they loaded). Files go to %LOCALAPPDATA%\\SyncBridge\\updates.
Standard library only.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import urllib.request
import zipfile
from typing import Callable, Optional

from .releases import USER_AGENT

CHUNK = 256 * 1024
# Variables of the host's Python (Maya) that must not reach the installer's PowerShell / Python children
STRIP_ENV = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONNOUSERSITE",
             "PYTHONEXECUTABLE", "__PYVENV_LAUNCHER__")


def updates_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "SyncBridge", "updates")


def download(asset: dict, dest_dir: Optional[str] = None, progress: Optional[Callable[[int, int], None]] = None,
             opener=None, timeout: float = 30.0) -> str:
    """The file of `asset` (releases.choose_asset) in dest_dir; its SHA-256 (or size) is checked.
    Raises RuntimeError with a Japanese message."""
    name = os.path.basename(asset.get("name") or "")
    if not name or not asset.get("url"):
        raise RuntimeError(u"このリリースには、SyncBridge のインストーラーも zip もありません。")
    dest_dir = dest_dir or updates_dir()
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, name)
    part = path + ".part"
    total = int(asset.get("size") or 0)
    digest = hashlib.sha256()
    done = 0
    request = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response, open(part, "wb") as out:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except Exception as exc:
        _remove(part)
        raise RuntimeError(u"%s をダウンロードできませんでした: %s" % (name, exc))
    expected = asset.get("sha256")
    if expected and digest.hexdigest().lower() != expected.lower():
        _remove(part)
        raise RuntimeError(u"%s の中身が GitHub の記録（SHA-256）と合いません。もう一度試してください。" % name)
    if not expected and total and done != total:
        _remove(part)
        raise RuntimeError(u"%s のダウンロードが途中で切れました（%d / %d バイト）。" % (name, done, total))
    _remove(path)
    os.replace(part, path)
    return path


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def extract_release(zip_path: str, dest: Optional[str] = None) -> str:
    """Unpack a release zip (folder SyncBridge-<version>/ with Install.bat); returns the folder that has
    Install.bat. Names that would leave `dest` are refused."""
    dest = os.path.abspath(dest or os.path.splitext(zip_path)[0])
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            target = os.path.abspath(os.path.join(dest, member))
            if os.path.commonpath([dest, target]) != dest:
                raise RuntimeError(u"zip の中に、展開先の外を指すファイルがあります: %s" % member)
        archive.extractall(dest)
    for dirpath, _dirs, files in os.walk(dest):
        if "Install.bat" in files:
            return dirpath
    raise RuntimeError(u"zip の中に Install.bat がありません: %s" % os.path.basename(zip_path))


def launch_command(path: str):
    """(argv, working folder) that starts the installer of a downloaded file: the setup EXE's wizard,
    or the zip's Install.bat (unpacked next to the zip)."""
    if path.lower().endswith(".exe"):
        return [path], os.path.dirname(path)
    if path.lower().endswith(".zip"):
        folder = extract_release(path)
        return ["cmd.exe", "/c", os.path.join(folder, "Install.bat")], folder
    raise RuntimeError(u"インストーラーではないファイルです: %s" % os.path.basename(path))


def launch(path: str) -> str:
    """Start the installer, detached (it stops the SyncBridge server, so it must not be our child);
    returns "exe" or "zip"."""
    argv, cwd = launch_command(path)
    env = dict(os.environ)
    for name in STRIP_ENV:
        env.pop(name, None)
    flags, extras = 0, (0,)
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        extras = (0x01000000, 0)           # CREATE_BREAKAWAY_FROM_JOB: AE's panel may run us in a job
    for extra in extras:
        try:
            subprocess.Popen(argv, cwd=cwd, env=env, creationflags=flags | extra, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            break
        except OSError:
            if not extra:
                raise
    return "exe" if path.lower().endswith(".exe") else "zip"
