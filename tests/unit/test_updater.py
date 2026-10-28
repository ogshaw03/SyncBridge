"""The updater (D-46): the GitHub release list, the download check, the zip and the command line.
No network: the API's JSON and the downloads are fakes."""
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from unittest import mock

from syncbridge.updater import __main__ as cli
from syncbridge.updater import install, releases


def _asset(name, data=b"x", digest=True):
    return {"name": name, "size": len(data), "browser_download_url": "https://example.invalid/" + name,
            "digest": ("sha256:" + hashlib.sha256(data).hexdigest()) if digest else None}


API = [
    {"tag_name": "v0.1.9", "name": "SyncBridge 0.1.9", "prerelease": True, "draft": False,
     "published_at": "2026-10-26T01:01:18Z", "html_url": "https://github.com/x/releases/tag/v0.1.9",
     "body": "notes", "assets": [_asset("SyncBridge-0.1.9.zip")]},
    {"tag_name": "v0.1.15", "name": "SyncBridge 0.1.15", "prerelease": False, "draft": False,
     "published_at": "2026-10-28T09:00:00Z", "assets": [_asset("SyncBridge-0.1.15.zip"),
                                                        _asset("SyncBridge-Setup-0.1.15.exe")]},
    {"tag_name": "v0.1.10", "draft": False, "published_at": "2026-10-27T00:00:00Z", "assets": []},
    {"tag_name": "v0.2.0", "draft": True, "assets": [_asset("SyncBridge-Setup-0.2.0.exe")]},
    {"tag_name": "nightly", "draft": False, "assets": []},
]


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(data):
    return lambda request, timeout=None: _Response(data)


class ReleasesTest(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(releases.parse_version("v0.1.15"), (0, 1, 15))
        self.assertEqual(releases.parse_version("0.1.9"), (0, 1, 9))
        self.assertIsNone(releases.parse_version("nightly"))
        self.assertGreater(releases.parse_version("v0.1.10"), releases.parse_version("v0.1.9"))   # not text order

    def test_newest_first_without_drafts_with_the_relation(self):
        items = releases.parse_releases(API, current="0.1.10")
        self.assertEqual([r["tag"] for r in items], ["v0.1.15", "v0.1.10", "v0.1.9"])
        self.assertEqual([r["relation"] for r in items], ["newer", "current", "older"])
        self.assertEqual(items[2]["date"], "2026-10-26")
        self.assertIsNone(items[1]["asset"])                                   # no file to install
        self.assertEqual([r["has_updater"] for r in items], [False, False, False])   # before 0.1.16
        self.assertTrue(releases.parse_releases([{"tag_name": "v0.1.16", "assets": []}])[0]["has_updater"])

    def test_the_setup_exe_is_preferred_over_the_zip(self):
        items = releases.parse_releases(API, current="0.1.15")
        self.assertEqual(items[0]["asset"]["kind"], "exe")
        self.assertEqual(items[0]["asset"]["name"], "SyncBridge-Setup-0.1.15.exe")
        self.assertEqual(items[2]["asset"]["kind"], "zip")
        self.assertEqual(len(items[2]["asset"]["sha256"]), 64)

    def test_fetch(self):
        self.assertEqual(releases.fetch(opener=_opener(json.dumps(API).encode("utf-8"))), API)

        def broken(request, timeout=None):
            raise OSError("offline")
        with self.assertRaises(RuntimeError):
            releases.fetch(opener=broken)


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sbupdater_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def asset(self, name, data, digest=True):
        return releases.choose_asset([_asset(name, data, digest)])

    def test_download_checks_the_sha256(self):
        data = b"setup" * 1000
        seen = []
        path = install.download(self.asset("SyncBridge-Setup-0.1.15.exe", data), self.tmp,
                                progress=lambda done, total: seen.append((done, total)), opener=_opener(data))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), data)
        self.assertEqual(seen[-1], (len(data), len(data)))
        with self.assertRaises(RuntimeError):                                  # a different file
            install.download(self.asset("SyncBridge-Setup-0.1.15.exe", data), self.tmp, opener=_opener(b"evil"))
        self.assertEqual(os.listdir(self.tmp), ["SyncBridge-Setup-0.1.15.exe"])   # no .part left
        with self.assertRaises(RuntimeError):                                  # cut short, no digest
            install.download(self.asset("SyncBridge-0.1.9.zip", data, digest=False), self.tmp,
                             opener=_opener(data[:10]))

    def make_zip(self, names):
        path = os.path.join(self.tmp, "SyncBridge-0.1.9.zip")
        with zipfile.ZipFile(path, "w") as z:
            for name in names:
                z.writestr(name, "x")
        return path

    def test_zip_unpacks_to_the_folder_with_install_bat(self):
        path = self.make_zip(["SyncBridge-0.1.9/Install.bat", "SyncBridge-0.1.9/payload/install.ps1"])
        argv, cwd = install.launch_command(path)
        self.assertEqual(os.path.basename(cwd), "SyncBridge-0.1.9")
        self.assertEqual(argv[:2], ["cmd.exe", "/c"])
        self.assertTrue(os.path.isfile(argv[2]))
        self.assertTrue(argv[2].endswith(os.path.join("SyncBridge-0.1.9", "Install.bat")))

    def test_zip_with_a_name_outside_is_refused(self):
        with self.assertRaises(RuntimeError):
            install.extract_release(self.make_zip(["../evil.bat", "SyncBridge-0.1.9/Install.bat"]))
        with self.assertRaises(RuntimeError):
            install.extract_release(self.make_zip(["SyncBridge-0.1.9/readme.txt"]))   # no Install.bat

    def test_exe_starts_itself(self):
        exe = os.path.join(self.tmp, "SyncBridge-Setup-0.1.15.exe")
        self.assertEqual(install.launch_command(exe), ([exe], self.tmp))
        with self.assertRaises(RuntimeError):
            install.launch_command(os.path.join(self.tmp, "notes.txt"))


class CommandLineTest(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(releases, "fetch", return_value=API):
            code = cli.main(list(args))
        return code, [json.loads(line) for line in out.getvalue().splitlines()]

    def test_list(self):
        code, lines = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["releases"][0]["tag"], "v0.1.15")
        self.assertIn("current", lines[0])

    def test_install_reports_progress_then_launches(self):
        with mock.patch.object(install, "download", return_value="C:/x/SyncBridge-Setup-0.1.15.exe") as download, \
                mock.patch.object(install, "launch") as launch:
            code, lines = self.run_cli("install", "v0.1.15")
        self.assertEqual(code, 0)
        self.assertEqual(download.call_args[0][0]["kind"], "exe")
        launch.assert_called_once_with("C:/x/SyncBridge-Setup-0.1.15.exe")
        self.assertEqual([list(line)[0] for line in lines], ["launching", "done"])

    def test_errors_are_json(self):
        code, lines = self.run_cli("install", "v9.9.9")
        self.assertEqual(code, 1)
        self.assertIn("v9.9.9", lines[0]["error"])
        code, lines = self.run_cli("install", "v0.1.10")                       # no file in that release
        self.assertEqual(code, 1)
        code, lines = self.run_cli("frobnicate")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
