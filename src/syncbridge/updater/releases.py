"""The SyncBridge releases on GitHub, for the About / update window of the Maya and AE panels (D-46).

TEMPORARY (the user, 2026-10-28): the update steps may change. The public GitHub Releases API is read
without credentials (no token anywhere, CLAUDE.md); 60 requests an hour per address is plenty.

    data = fetch()                                      # the API's JSON (network)
    items = parse_releases(data, current="0.1.15")      # pure: newest first, the file to use for each

Standard library only (Maya's Python 3.9, SyncServer.exe).
"""
from __future__ import annotations

import fnmatch
import json
import re
import urllib.request
from typing import List, Optional, Tuple

REPO = "ogshaw03/SyncBridge"
API_URL = "https://api.github.com/repos/%s/releases?per_page=50" % REPO
PAGE_URL = "https://github.com/%s/releases" % REPO
USER_AGENT = "SyncBridge-updater"
# the installer is used when a release has it (0.1.15 and later), else the zip (0.1.0 - 0.1.14)
ASSET_KINDS = (("exe", "SyncBridge-Setup-*.exe"), ("zip", "SyncBridge-*.zip"))
FIRST_WITH_UPDATER = (0, 1, 16)     # older versions have no About / update menu: going back is one way


def parse_version(text: Optional[str]) -> Optional[Tuple[int, ...]]:
    """"v0.1.15" / "0.1.15" -> (0, 1, 15); None when it is not a version."""
    match = re.match(r"^v?(\d+(?:\.\d+)*)$", (text or "").strip())
    return tuple(int(p) for p in match.group(1).split(".")) if match else None


def version_text(version: Tuple[int, ...]) -> str:
    return ".".join(str(p) for p in version)


def choose_asset(assets: List[dict]) -> Optional[dict]:
    """The file to install from a release's assets: {name, size, url, sha256, kind}, or None."""
    for kind, pattern in ASSET_KINDS:
        for asset in assets or []:
            name = asset.get("name") or ""
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                digest = asset.get("digest") or ""
                return {"name": name, "size": int(asset.get("size") or 0),
                        "url": asset.get("browser_download_url") or "",
                        "sha256": digest[7:].lower() if digest.lower().startswith("sha256:") else None,
                        "kind": kind}
    return None


def parse_releases(data, current: Optional[str] = None) -> List[dict]:
    """The releases of the API's JSON, newest version first (drafts and tags that are not versions
    left out): [{tag, version, name, date, prerelease, notes, page, asset, relation, has_updater}],
    relation = "current" / "newer" / "older" than `current` (None when unknown); has_updater: that
    version has this menu too."""
    now = parse_version(current)
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        version = parse_version(item.get("tag_name"))
        if version is None:
            continue
        relation = None
        if now is not None:
            relation = "current" if version == now else ("newer" if version > now else "older")
        out.append({"tag": item.get("tag_name"), "version": version_text(version),
                    "name": item.get("name") or item.get("tag_name"),
                    "date": (item.get("published_at") or "")[:10], "prerelease": bool(item.get("prerelease")),
                    "notes": item.get("body") or "", "page": item.get("html_url") or PAGE_URL,
                    "asset": choose_asset(item.get("assets")), "relation": relation,
                    "has_updater": version >= FIRST_WITH_UPDATER, "_key": version})
    out.sort(key=lambda r: r["_key"], reverse=True)
    for item in out:
        del item["_key"]
    return out


def fetch(timeout: float = 15.0, opener=None):
    """The API's JSON (a list). Raises RuntimeError with a Japanese message when it cannot be read."""
    request = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT,
                                                       "Accept": "application/vnd.github+json"})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(u"GitHub のリリースの一覧を取得できませんでした（ネットワークを確認してください）: %s" % exc)


def releases(current: Optional[str] = None, timeout: float = 15.0, opener=None) -> List[dict]:
    return parse_releases(fetch(timeout, opener), current)
