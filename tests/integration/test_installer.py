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


def _build_release_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sb_build_release", os.path.join(REPO, "packaging", "build_release.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = _build_release_module() if sys.platform == "win32" else None
ISCC = BUILD.find_iscc() if BUILD else None
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{37BA4B31-BD87-4A70-AE30-F53FA9756084}_is1"


@unittest.skipUnless(sys.platform == "win32" and POWERSHELL and ISCC, "Windows PowerShell and Inno Setup 6")
class SetupExeTest(unittest.TestCase):
    """SyncBridge-Setup.exe (SyncBridge.iss) on the same fake payload, silently, into temporary folders:
    /SBTest=1 makes no "Apps" entry, so nothing outside the temporary folders is written."""
    setUp = InstallerTest.setUp
    shelf = InstallerTest.shelf

    def make_setup(self):
        return BUILD.make_setup(ISCC, self.payload, os.path.join(self.tmp, "iss"), os.path.join(self.tmp, "out"),
                                "0.0.1", "SyncBridge-Setup-test")

    def test_setup_installs_and_its_uninstaller_removes(self):
        import winreg
        setup = self.make_setup()
        root = os.path.join(self.tmp, "Programs", "SyncBridge")
        cep = os.path.join(self.tmp, "cep")
        result = subprocess.run([setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SBTest=1",
                                 "/DIR=%s" % root, "/CepRoot=%s" % cep,
                                 "/ProgramsDir=%s" % os.path.join(self.tmp, "StartMenu"),
                                 "/MayaAppDir=%s" % self.maya_dir], timeout=300)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(root, "install.json")))
        self.assertTrue(os.path.isfile(os.path.join(root, "uninstall.ps1")))
        self.assertFalse(os.path.exists(os.path.join(root, "Uninstall.bat")))      # the setup's uninstaller instead
        uninstaller = os.path.join(root, "uninstall", "unins000.exe")
        self.assertTrue(os.path.isfile(uninstaller))
        self.assertTrue(os.path.isfile(self.shelf("2023")))
        self.assertTrue(os.path.isfile(os.path.join(cep, "com.syncbridge.panel", "CSXS", "manifest.xml")))
        with self.assertRaises(OSError):                                             # no "Apps" entry in the test
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)

        # The uninstaller runs a copy of itself from the temporary folder and returns at once.
        subprocess.run([uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=120)
        import time
        for _ in range(120):
            if not os.path.exists(root):
                break
            time.sleep(0.5)
        self.assertFalse(os.path.exists(root), os.listdir(root) if os.path.exists(root) else "")
        self.assertFalse(os.path.exists(self.shelf("2023")))
        self.assertFalse(os.path.exists(os.path.join(cep, "com.syncbridge.panel")))
        self.assertTrue(os.path.isfile(os.path.join(self.maya_dir, "2023", "prefs", "shelves", "shelf_Custom.mel")))


if __name__ == "__main__":
    unittest.main()
