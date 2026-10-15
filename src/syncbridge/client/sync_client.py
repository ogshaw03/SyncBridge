"""Connection from an application (Maya, later others) to the Local Sync Server.

Threading model (H-MY-14):
  * a background thread blocks in WebSocket.recv()
  * everything that touches the application or its UI is handed to
    `dispatch(fn)`, which must run fn on the application's main thread
    (Maya: maya.utils.executeDeferred). Without a dispatch function, fn runs
    on the receiving thread (tests, command line use).
  * sending is thread-safe (the WebSocket serializes sends).

Requests from the server (export.request, apply.request) are answered by the
`handlers` given to the constructor: handler(message) -> reply data dict.
An exception becomes an `error` reply (app_error) with its message.

    client = SyncClient("maya", handlers, dispatch=maya.utils.executeDeferred,
                        on_event=ui.on_event)
    client.connect()                      # reads the session file
    client.request_transfer("maya2ae", {"origin": 1}, callback)
"""
from __future__ import annotations

import os
import threading
import traceback
from typing import Callable, Dict, List, Optional

from .. import __version__, protocol
from ..server import session
from .ws import WebSocket, WebSocketError

Handler = Callable[[dict], dict]
Dispatch = Callable[[Callable[[], None]], None]
EventCallback = Callable[[str, object], None]

# on_event names
EV_CONNECTED = "connected"          # payload: welcome data
EV_DISCONNECTED = "disconnected"    # payload: reason (str)
EV_PEERS = "peers"                  # payload: list of client summaries
EV_ERROR = "error"                  # payload: error data {code, message}
EV_REQUEST = "request"              # payload: kind of a server request being handled


class ConnectError(Exception):
    pass


class SyncClient:
    def __init__(self, app: str, handlers: Optional[Dict[str, Handler]] = None,
                 dispatch: Optional[Dispatch] = None, on_event: Optional[EventCallback] = None,
                 version: str = __version__, document: Callable[[], str] = lambda: ""):
        if app not in protocol.APPS:
            raise ValueError("app must be one of %s" % (protocol.APPS,))
        self.app = app
        self.handlers = dict(handlers or {})
        self.dispatch = dispatch or (lambda fn: fn())
        self.on_event = on_event
        self.version = version
        self.document = document
        self.ws: Optional[WebSocket] = None
        self.client_id: Optional[str] = None
        self.peers: List[dict] = []
        self._pending: Dict[str, Callable[[dict], None]] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._closing = False

    # -- connection ---------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self.ws is not None and not self.ws.closed

    def connect(self, port: Optional[int] = None, token: Optional[str] = None,
                host: str = protocol.HOST, timeout: float = 5.0) -> dict:
        """Connect and say hello. Port and token default to the session file. Returns welcome data."""
        if self.connected:
            raise ConnectError("already connected")
        if port is None or token is None:
            info = session.read_session()
            if info is None:
                raise ConnectError("no SyncBridge server session (%s); start the server first"
                                   % session.session_path())
            port = info["port"] if port is None else port
            token = info["token"] if token is None else token
        try:
            conn = WebSocket.connect(host, port, protocol.WS_PATH, timeout=timeout)
        except (OSError, WebSocketError) as exc:
            raise ConnectError("cannot connect to %s:%s: %s" % (host, port, exc))
        try:
            conn.send_text(protocol.encode(protocol.message("hello", {
                "token": token, "app": self.app, "version": self.version, "pid": os.getpid(),
                "document": self._document(), "protocol": protocol.PROTOCOL_VERSION}, self.app)))
            text = conn.recv()
            if text is None:
                raise ConnectError("the server closed the connection")
            welcome = protocol.decode(text)
        except (OSError, WebSocketError, protocol.ProtocolError) as exc:
            conn.close()
            raise ConnectError("handshake failed: %s" % exc)
        if welcome["kind"] != "welcome":
            conn.close()
            raise ConnectError("refused by the server: %s" % welcome["data"].get("message", welcome["kind"]))
        self.ws = conn
        self._closing = False
        self.client_id = welcome["data"]["client_id"]
        self._thread = threading.Thread(target=self._read_loop, name="syncbridge-client", daemon=True)
        self._thread.start()
        self._emit(EV_CONNECTED, welcome["data"])
        return welcome["data"]

    def disconnect(self) -> None:
        self._closing = True
        if self.ws is not None:
            self.ws.close()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(5)

    # -- requests to the server ------------------------------------------------------
    def request_transfer(self, direction: str, options: Optional[dict],
                         callback: Callable[[dict], None], target: Optional[str] = None) -> str:
        """Ask the server for a transfer. `callback(reply)` runs via dispatch with
        a transfer.result or error message. Returns the request's event_id."""
        data = {"direction": direction, "options": options or {}}
        if target:
            data["target"] = target
        return self._request("transfer.request", data, callback)

    def _request(self, kind: str, data: dict, callback: Callable[[dict], None]) -> str:
        if not self.connected:
            raise ConnectError("not connected")
        msg = protocol.message(kind, data, self.app)
        with self._lock:
            self._pending[msg["event_id"]] = callback
        try:
            self.ws.send_text(protocol.encode(msg))
        except (OSError, WebSocketError) as exc:
            with self._lock:
                self._pending.pop(msg["event_id"], None)
            raise ConnectError("send failed: %s" % exc)
        return msg["event_id"]

    # -- receiving -------------------------------------------------------------------
    def _read_loop(self) -> None:
        reason = "closed"
        try:
            while True:
                text = self.ws.recv()
                if text is None:
                    if self._closing:
                        reason = "disconnected by this client"
                    else:
                        reason = "the server closed the connection (code %s)" % self.ws.close_code
                    break
                try:
                    msg = protocol.decode(text)
                except protocol.ProtocolError as exc:
                    self._emit(EV_ERROR, {"code": exc.code, "message": exc.message})
                    continue
                self._on_message(msg)
        except Exception as exc:  # never die silently
            reason = "receive error: %s" % exc
        finally:
            self._finish(reason)

    def _on_message(self, msg: dict) -> None:
        kind = msg["kind"]
        reply_to = msg.get("reply_to")
        if reply_to:
            with self._lock:
                callback = self._pending.pop(reply_to, None)
            if callback is not None:
                self._call(callback, msg)
                return
        if kind == "peers":
            self.peers = msg["data"]["clients"]
            self._emit(EV_PEERS, self.peers)
        elif kind in self.handlers:
            self.dispatch(lambda: self._handle_request(msg))
        elif kind == "error":
            self._emit(EV_ERROR, msg["data"])
        else:
            self._send_quietly(protocol.error(protocol.E_BAD_MESSAGE, "%s cannot handle %s" % (self.app, kind),
                                              self.app, msg["event_id"]))

    def _handle_request(self, msg: dict) -> None:
        """Runs on the main thread (via dispatch)."""
        if self.on_event:
            self._safe(lambda: self.on_event(EV_REQUEST, msg["kind"]))
        try:
            data = self.handlers[msg["kind"]](msg)
            reply = protocol.reply(msg, data, self.app)
        except Exception as exc:
            traceback.print_exc()
            reply = protocol.error(protocol.E_APP, "%s: %s" % (type(exc).__name__, exc), self.app, msg["event_id"])
        self._send_quietly(reply)

    def _finish(self, reason: str) -> None:
        with self._lock:
            pending = list(self._pending.items())
            self._pending.clear()
        for event_id, callback in pending:
            self._call(callback, protocol.error(protocol.E_DISCONNECTED, reason, "client", event_id))
        self.peers = []
        self._emit(EV_DISCONNECTED, reason)

    # -- helpers ----------------------------------------------------------------------
    def _send_quietly(self, msg: dict) -> None:
        try:
            if self.connected:
                self.ws.send_text(protocol.encode(msg))
        except (OSError, WebSocketError):
            pass

    def _call(self, callback, msg) -> None:
        self.dispatch(lambda: self._safe(lambda: callback(msg)))

    def _emit(self, name: str, payload) -> None:
        if self.on_event:
            self.dispatch(lambda: self._safe(lambda: self.on_event(name, payload)))

    @staticmethod
    def _safe(fn) -> None:
        try:
            fn()
        except Exception:
            traceback.print_exc()

    def _document(self) -> str:
        try:
            return str(self.document() or "")
        except Exception:
            return ""
