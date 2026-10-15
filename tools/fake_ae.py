"""Stand-in for After Effects on the Local Sync Server (development / Phase 1-B testing).

Lets you test the Maya side before the AE CEP panel exists (Phase 1-C):

    py -3 tools\\fake_ae.py --export probe_results\\v2_ae_before.json

  * export.request -> answers with the given ae.timeremap.export file (a real AE export)
  * apply.request  -> prints the keys, saves the apply envelope to
                      probe_results\\fake_ae_last_apply.json and answers "applied" with a
                      SIMULATED readback (the keys evaluated by SyncBridge's own AE model)
  * type  m + Enter  to request AE -> Maya (as if the AE panel's button was pressed)
  * type  q + Enter  (or Ctrl+C) to quit

Nothing here touches After Effects. Standard library only.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from syncbridge import protocol  # noqa: E402
from syncbridge.client.sync_client import ConnectError, SyncClient  # noqa: E402
from syncbridge.core import ae_codec, envelope  # noqa: E402


def simulated_after(export_env: dict, keys: list) -> dict:
    """An export as AE would send it after applying `keys` (evaluated by SyncBridge's AE model)."""
    data = dict(export_env["data"])
    curve = ae_codec.decode(keys)
    t0, t1 = keys[0]["time"], keys[-1]["time"]
    step = float(data["comp"].get("frameDuration") or 1 / 24.0) / 8
    n = int(round((t1 - t0) / step))
    times = [t0 + i * step for i in range(n + 1)]
    data["keys"] = keys
    data["samples"] = {"times": times, "values": [curve.evaluate(t) for t in times]}
    return envelope.make("ae.timeremap.export", data, "fake-ae")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--export", required=True, help="ae.timeremap.export file to answer with")
    parser.add_argument("--origin", type=float, default=1.0, help="origin frame for the m command")
    parser.add_argument("--mode", default="editable")
    args = parser.parse_args(argv)

    export_env = envelope.load(args.export, "ae.timeremap.export")
    last_apply = os.path.join(ROOT, "probe_results", "fake_ae_last_apply.json")
    layer = export_env["data"]["layer"].get("name", "?")

    def on_export(msg):
        print("<- export.request: answering with %s (layer %s)" % (os.path.basename(args.export), layer))
        return {"export": export_env}

    def on_apply(msg):
        apply_env = msg["data"]["apply"]
        keys = apply_env["data"]["keys"]
        os.makedirs(os.path.dirname(last_apply), exist_ok=True)
        envelope.save(last_apply, apply_env)
        print("<- apply.request: %d keys (%s mode), saved to %s"
              % (len(keys), apply_env["data"].get("mode"), last_apply))
        for k in keys:
            print("     comp %.4f s -> source %.4f s  %s/%s" % (k["time"], k["value"], k["inInterp"], k["outInterp"]))
        print("   answering 'applied' with a SIMULATED readback (no real After Effects)")
        return {"status": "applied", "after": simulated_after(export_env, keys), "backup": "(fake)"}

    def on_event(name, payload):
        if name == "peers":
            print("   peers: %s" % ", ".join("%s(%s)" % (p["client_id"], p.get("document") or "-") for p in payload))
        elif name in ("disconnected", "error"):
            print("   %s: %s" % (name, payload))

    client = SyncClient("ae", {"export.request": on_export, "apply.request": on_apply},
                        on_event=on_event, version="fake-ae",
                        document=lambda: "fake AE: %s" % os.path.basename(args.export))
    try:
        welcome = client.connect()
    except ConnectError as exc:
        print("error: %s" % exc)
        print("Start the server first (Connect in the Maya panel, or syncbridge-server.cmd).")
        return 1
    print("connected as %s. Commands: m = request AE -> Maya, q = quit" % welcome["client_id"])

    def on_result(reply):
        if reply["kind"] == "error":
            print("-> AE -> Maya failed: %s" % reply["data"].get("message"))
        else:
            print("-> %s" % protocol.describe_result(reply["data"]))
            if reply["data"].get("message"):
                print("   %s" % reply["data"]["message"])

    try:
        while client.connected:
            line = sys.stdin.readline()
            if not line or line.strip().lower() == "q":
                break
            if line.strip().lower() == "m":
                client.request_transfer("ae2maya", {"origin": args.origin, "mode": args.mode}, on_result)
                print("   requested AE -> Maya; confirm in Maya")
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
