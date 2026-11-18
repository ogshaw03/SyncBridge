"""Switching to a newly installed version without restarting Maya / AE (D-56).

Maya: syncbridge_maya.hot_reload with a fake maya package (what is installed, which plug-in changed).
AE: panel/js/hotreload.js in Node with a fake CEP (what install.json and the manifest on disk say).
The switch itself runs in Maya and AE only (tools/hot_reload_check.py, docs/VERIFICATION.md).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAYA_SCRIPTS = os.path.join(REPO, "maya_plugin", "scripts")
HOTRELOAD_JS = os.path.join(REPO, "after_effects", "panel", "js", "hotreload.js")
NODE = shutil.which("node")


def _maya_modules():
    return [k for k in sys.modules if k == "maya" or k.startswith(("maya.", "syncbridge_maya"))]


class MayaHotReloadTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: sys.modules.pop(k) for k in _maya_modules()}
        maya = types.ModuleType("maya")
        cmds = types.ModuleType("maya.cmds")
        maya.cmds = cmds
        sys.modules.update({"maya": maya, "maya.cmds": cmds})
        sys.path.insert(0, MAYA_SCRIPTS)
        from syncbridge_maya import hot_reload
        self.hot = hot_reload
        self.tmp = tempfile.mkdtemp(prefix="sbhotreload_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def tearDown(self):
        sys.path.remove(MAYA_SCRIPTS)
        for k in _maya_modules():
            del sys.modules[k]
        sys.modules.update(self.saved)
        import __main__
        if hasattr(__main__, self.hot.PLUGIN_DIGESTS_KEY):
            delattr(__main__, self.hot.PLUGIN_DIGESTS_KEY)

    def write_record(self, version, bom=True):
        # install.ps1 writes it with Set-Content -Encoding UTF8 (Windows PowerShell 5.1: with a BOM)
        with open(os.path.join(self.tmp, "install.json"), "w", encoding="utf-8-sig" if bom else "utf-8") as f:
            json.dump({"version": version, "installed": "2026-11-11T10:00:00"}, f)

    def test_repository_is_not_an_install(self):
        self.assertIsNone(self.hot.install_root())         # the repository has no install.json

    def test_installed_version(self):
        self.assertIsNone(self.hot.installed_version(self.tmp))
        self.write_record("0.1.21")
        self.assertEqual(self.hot.installed_version(self.tmp), "0.1.21")
        self.write_record("0.1.22", bom=False)
        self.assertEqual(self.hot.installed_version(self.tmp), "0.1.22")

    def test_half_written_record_is_not_a_version(self):
        with open(os.path.join(self.tmp, "install.json"), "w", encoding="utf-8") as f:
            f.write('{"version": "0.1')
        self.assertIsNone(self.hot.installed_version(self.tmp))

    def test_pending_only_for_another_version(self):
        from syncbridge import __version__
        self.hot.install_root = lambda: self.tmp
        self.write_record(__version__)
        self.assertIsNone(self.hot.pending())
        self.write_record("9.9.9")
        self.assertEqual(self.hot.pending(), "9.9.9")

    def test_plugin_changed(self):
        import __main__
        path = os.path.join(self.tmp, "syncbridge_guide.py")
        with open(path, "w") as f:
            f.write("# r1\n")
        # loaded by a version that did not remember its file (0.1.20 and older): changed
        self.assertTrue(self.hot._plugin_changed("syncbridge_guide", path))
        setattr(__main__, self.hot.PLUGIN_DIGESTS_KEY, {"syncbridge_guide": self.hot.file_digest(path)})
        self.assertFalse(self.hot._plugin_changed("syncbridge_guide", path))
        with open(path, "w") as f:
            f.write("# r2\n")
        self.assertTrue(self.hot._plugin_changed("syncbridge_guide", path))

    def test_guide_plugin_remembers_the_same_digest(self):
        """The plug-in's own digest (it cannot import syncbridge_maya) must match hot_reload's."""
        with open(os.path.join(REPO, "maya_plugin", "plug-ins", "syncbridge_guide.py"), encoding="utf-8") as f:
            source = f.read()
        self.assertIn('digests["syncbridge_guide"] = digest', source)
        self.assertIn('"_syncbridge_plugin_digests"', source)
        self.assertEqual(self.hot.PLUGIN_DIGESTS_KEY, "_syncbridge_plugin_digests")
        self.assertEqual(self.hot.GUIDE_PLUGIN, "syncbridge_guide")
        self.assertIn("_remember_digest(plugin.loadPath())", source)


MANIFEST = ('<ExtensionManifest ExtensionBundleId="com.syncbridge" ExtensionBundleVersion="{v}">'
            '<Extension Id="com.syncbridge.panel" Version="{v}"/>{extra}</ExtensionManifest>')


@unittest.skipUnless(NODE, "Node.js")
class PanelHotReloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sbhotreload_js_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ext = os.path.join(self.tmp, "CEP", "com.syncbridge.panel")
        os.makedirs(os.path.join(self.ext, "CSXS"))
        os.makedirs(os.path.join(self.tmp, "Programs", "SyncBridge"))

    def files(self, manifest_version, record_version, extra=""):
        with open(os.path.join(self.ext, "CSXS", "manifest.xml"), "w", encoding="utf-8") as f:
            f.write(MANIFEST.format(v=manifest_version, extra=extra))
        if record_version is not None:
            with open(os.path.join(self.tmp, "Programs", "SyncBridge", "install.json"), "w",
                      encoding="utf-8-sig") as f:
                json.dump({"version": record_version}, f)

    def check(self, running_manifest):
        body = (
            "const vm = require('vm'), fs = require('fs');"
            "const page = {document: {}, navigator: {platform: 'Win32'},"
            "  cep_node: {require: require, process: {env: {LOCALAPPDATA: %s}}},"
            "  __adobe_cep__: {getSystemPath: () => 'file:///' + %s}};"
            "page.window = page; vm.createContext(page);"
            "vm.runInContext(fs.readFileSync(%s, 'utf8'), page);"
            "page.SBHotReload.setRunning({version: page.SBHotReload.bundleVersion(%s), manifest: %s});"
            "process.stdout.write(JSON.stringify(page.SBHotReload.check()));"
            % (json.dumps(self.tmp), json.dumps(self.ext.replace("\\", "/")), json.dumps(HOTRELOAD_JS),
               json.dumps(running_manifest), json.dumps(running_manifest)))
        out = subprocess.run([NODE, "-e", body], capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_same_version_is_nothing(self):
        self.files("0.1.21", "0.1.21")
        self.assertIsNone(self.check(MANIFEST.format(v="0.1.21", extra="")))

    def test_new_version_can_switch(self):
        self.files("0.1.22", "0.1.22")
        self.assertEqual(self.check(MANIFEST.format(v="0.1.21", extra="")), {"version": "0.1.22", "restart": False})

    def test_changed_manifest_needs_restart(self):
        self.files("0.1.22", "0.1.22", extra="<Parameter>--new-flag</Parameter>")
        self.assertEqual(self.check(MANIFEST.format(v="0.1.21", extra="")), {"version": "0.1.22", "restart": True})

    def test_not_while_installing_or_for_another_folder(self):
        # install.json says 0.1.22 but this extension's files are not (yet): the development link, or mid-install
        self.files("0.1.21", "0.1.22")
        self.assertIsNone(self.check(MANIFEST.format(v="0.1.21", extra="")))
        self.files("0.1.22", None)
        os.remove(os.path.join(self.tmp, "Programs", "SyncBridge", "install.json"))
        self.assertIsNone(self.check(MANIFEST.format(v="0.1.21", extra="")))


if __name__ == "__main__":
    unittest.main()
