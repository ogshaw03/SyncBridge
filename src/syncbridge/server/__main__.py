"""Run the Local Sync Server.

    .venv\\Scripts\\python -m syncbridge.server [--port 8765] [--idle-timeout 600]

Exits with 0 without starting when a SyncBridge server already answers on
the port (single instance), with 3 when another program uses the port.
"""
from __future__ import annotations

import argparse
import logging
import sys

from .. import __version__, protocol
from . import session


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="syncbridge.server")
    parser.add_argument("--port", type=int, default=protocol.DEFAULT_PORT)
    parser.add_argument("--idle-timeout", type=float, default=600.0,
                        help="stop when no client has been connected for this many seconds (0 = never)")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(name)s %(levelname)s %(message)s")

    running = session.probe_server(args.port)
    if running:
        print("SyncBridge server %s is already running on port %d" % (running.get("version"), args.port))
        return 0
    if session.port_in_use(args.port):
        print("error: port %d is used by another program" % args.port, file=sys.stderr)
        return 3

    import uvicorn
    from .app import create_app

    token = session.new_token()
    holder = {}

    def stop():
        holder["server"].should_exit = True

    app = create_app(token, idle_timeout=args.idle_timeout or None, on_idle=stop)
    # Loopback only (SPEC 8). Never bind 0.0.0.0.
    config = uvicorn.Config(app, host=protocol.HOST, port=args.port, log_level=args.log_level,
                            ws="websockets-sansio")
    server = uvicorn.Server(config)
    holder["server"] = server
    path = session.write_session(args.port, token, __version__)
    print("SyncBridge server %s on ws://%s:%d%s (session: %s)"
          % (__version__, protocol.HOST, args.port, protocol.WS_PATH, path))
    try:
        server.run()
    finally:
        session.remove_session()
    return 0


if __name__ == "__main__":
    sys.exit(main())
