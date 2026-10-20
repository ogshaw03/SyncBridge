"""Installer and uninstaller (packaging/installer) in temporary folders: the Maya shelf tabs (D-17).

Runs install.ps1 / uninstall.ps1 with Windows PowerShell on a fake payload and a fake Maya
user folder; never touches the real Maya, AE or Start menu. LOCALAPPDATA is pointed at a
temporary folder so the default install location is temporary too.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INSTALLER = os.path.join(REPO, "packaging", "installer")
POWERSHELL = shutil.which("powershell")


def _write_ps1(src, dst):
    """As the release build does: UTF-8 with BOM (PowerShell 5.1 and Japanese text), CRLF."""
    with open(src, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n").replace("\n", "\r\n")
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)


@unittest.skipUnless(sys.platform == "win32" and POWERSHELL, "Windows PowerShell")
class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sbinstaller_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.payload = os.path.join(self.tmp, "release", "payload")
        maya = os.path.join(self.payload, "maya")
        os.makedirs(os.path.join(maya, "icons"))
        os.makedirs(os.path.join(maya, "scripts", "syncbridge_maya"))
        shutil.copy2(os.path.join(REPO, "maya_plugin", "icons", "syncbridge_shelf.png"), os.path.join(maya, "icons"))
        open(os.path.join(maya, "scripts", "syncbridge_maya", "ui.py"), "w").close()
        os.makedirs(os.path.join(self.payload, "ae"))
        with zipfile.ZipFile(os.path.join(self.payload, "ae", "com.syncbridge.panel.zxp"), "w") as z:
            z.writestr("CSXS/manifest.xml", '<ExtensionManifest ExtensionBundleId="com.syncbridge.panel"/>')
        shutil.copy2(os.path.join(REPO, "version.json"), self.payload)
        for name in ("install.ps1", "uninstall.ps1"):
            _write_ps1(os.path.join(INSTALLER, name), os.path.join(self.payload, name))
        # Fake Maya user folder.
        self.maya_dir = os.path.join(self.tmp, "Documents", "maya")
        for prefs in ("2022/prefs", "2023/prefs/shelves", "2024/ja_JP/prefs", "2025/scripts", "scripts"):
            os.makedirs(os.path.join(self.maya_dir, prefs))
        with open(os.path.join(self.maya_dir, "2023", "prefs", "shelves", "shelf_Custom.mel"), "w") as f:
            f.write("// the user's own shelf\n")
        self.local = os.path.join(self.tmp, "Local")
        os.makedirs(self.local)

    def run_ps(self, script, *args):
        env = dict(os.environ, LOCALAPPDATA=self.local)
        env.pop("MAYA_APP_DIR", None)
        result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                                 "-CepRoot", os.path.join(self.tmp, "cep"), "-Quiet"] + list(args),
                                capture_output=True, env=env, timeout=120)
        out = result.stdout.decode("mbcs", errors="replace") + result.stderr.decode("mbcs", errors="replace")
        self.assertEqual(result.returncode, 0, out)
        return out

    def install(self, *args):
        return self.run_ps(os.path.join(self.payload, "install.ps1"), "-ProgramsDir",
                           os.path.join(self.tmp, "StartMenu"), "-MayaAppDir", self.maya_dir, *args)

    def shelf(self, *parts):
        return os.path.join(self.maya_dir, *parts, "prefs", "shelves", "shelf_SyncBridge.mel")

    def test_shelf_tabs_for_started_maya_2023_and_later(self):
        self.install()
        self.assertTrue(os.path.isfile(self.shelf("2023")))
        self.assertTrue(os.path.isfile(self.shelf("2024", "ja_JP")))
        self.assertTrue(os.path.isfile(os.path.join(self.maya_dir, "2024", "ja_JP", "prefs", "icons",
                                                    "syncbridge_shelf.png")))
        self.assertFalse(os.path.exists(self.shelf("2022")))                        # older than 2023
        self.assertFalse(os.path.exists(os.path.join(self.maya_dir, "2025", "prefs")))   # never started
        root = os.path.join(self.local, "Programs", "SyncBridge")
        with open(os.path.join(root, "install.json"), encoding="utf-8-sig") as f:
            record = json.load(f)
        files = record["maya_files"] if isinstance(record["maya_files"], list) else [record["maya_files"]]
        self.assertEqual(len(files), 4)                                              # 2 shelves + 2 icons

    def test_shelf_file_is_ascii_and_its_command_is_python(self):
        self.install()
        with open(self.shelf("2023"), "rb") as f:
            raw = f.read()
        raw.decode("ascii")                                       # Maya reads it in the system code page
        text = raw.decode("ascii")
        self.assertIn('global proc shelf_SyncBridge ()', text)
        self.assertIn('-sourceType "python"', text)
        self.assertIn('-image "syncbridge_shelf.png"', text)
        command = re.search(r'-command "([^"]*)"', text).group(1)
        compile(command, "shelf", "exec")
        # Default install location: the scripts folder is found from LOCALAPPDATA when pressed.
        self.assertIn("os.environ['LOCALAPPDATA'], 'Programs', 'SyncBridge', 'maya', 'scripts'", command)

    def test_other_install_location_is_written_into_the_command(self):
        root = os.path.join(self.tmp, "Elsewhere", "SyncBridge")
        self.install("-InstallRoot", root)
        with open(self.shelf("2023"), encoding="ascii") as f:
            command = re.search(r'-command "([^"]*)"', f.read()).group(1)
        compile(command, "shelf", "exec")
        self.assertIn("r'%s/maya/scripts'" % root.replace("\\", "/"), command)

    def test_uninstall_removes_only_our_files(self):
        self.install()
        root = os.path.join(self.local, "Programs", "SyncBridge")
        self.run_ps(os.path.join(root, "uninstall.ps1"))
        self.assertFalse(os.path.exists(self.shelf("2023")))
        self.assertFalse(os.path.exists(self.shelf("2024", "ja_JP")))
        self.assertFalse(os.path.exists(os.path.join(self.maya_dir, "2023", "prefs", "icons", "syncbridge_shelf.png")))
        self.assertTrue(os.path.isfile(os.path.join(self.maya_dir, "2023", "prefs", "shelves", "shelf_Custom.mel")))
        self.assertFalse(os.path.exists(root))

    def test_start_menu_item_has_the_english_name(self):
        # 0.1.6: "SyncBridge Monitor"; the Japanese name of 0.1.3 - 0.1.5 is removed.
        app = os.path.join(self.payload, "app")
        os.makedirs(app)
        open(os.path.join(app, "SyncBridge.exe"), "wb").close()
        shutil.copy2(os.path.join(REPO, "packaging", "syncbridge.ico"), app)
        start = os.path.join(self.tmp, "StartMenu")
        os.makedirs(start)
        old = os.path.join(start, u"SyncBridge モニター.lnk")
        open(old, "wb").close()
        self.install()
        self.assertEqual(sorted(os.listdir(start)), ["SyncBridge Monitor.lnk"])
        # The item uses the icon file, not the EXE (Windows may have cached an old EXE icon).
        link = os.path.join(start, "SyncBridge Monitor.lnk")
        out = subprocess.run([POWERSHELL, "-NoProfile", "-Command",
                              "(New-Object -ComObject WScript.Shell).CreateShortcut('%s').IconLocation" % link],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        root = os.path.join(self.local, "Programs", "SyncBridge")
        self.assertEqual(os.path.normcase(out), os.path.normcase(os.path.join(root, "app", "syncbridge.ico") + ",0"))

    def test_no_maya_folder(self):
        shutil.rmtree(self.maya_dir)
        self.install()
        with open(os.path.join(self.local, "Programs", "SyncBridge", "install.json"), encoding="utf-8-sig") as f:
            record = json.load(f)
        self.assertIn(record["maya_files"], ([], None))


if __name__ == "__main__":
    unittest.main()
