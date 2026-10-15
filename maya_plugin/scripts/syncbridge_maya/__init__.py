"""SyncBridge Maya plugin (Phase 0 prototype).

Usage in the Maya Script Editor (Python):

    import sys
    sys.path.insert(0, r"<repo>/maya_plugin/scripts")
    import syncbridge_maya.exchange as sbx
    sbx.export_timewarp()      # Scene Time Warp -> JSON for the CLI / AE
    sbx.apply_timewarp()       # JSON from the CLI -> Scene Time Warp

During development the repository `src` directory is added to sys.path so the
shared Time Mapping Core (`syncbridge.core`) is importable inside Maya.
"""
import os
import sys

_SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)
