"""Minimal WebSocket client (RFC 6455), standard library only (D-12).

Supports what SyncBridge needs: text messages (fragmented or not), ping/pong
and close, over plain ws:// to the loopback server. No extensions, no TLS.

    conn = WebSocket.connect("127.0.0.1", 8765, "/ws")
    conn.send_text("...")
    text = conn.recv()        # str, or None once the connection is closed
    conn.close()

send_text / close may be called from another thread than recv (sends are
serialized with a lock).
"""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct
import threading
from typing import Optional, Tuple

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
MAX_MESSAGE = 64 * 1024 * 1024


class WebSocketError(Exception):
    pass


class WebSocketClosed(WebSocketError):
    def __init__(self, code: Optional[int] = None, reason: str = ""):
        super().__init__("connection closed (%s) %s" % (code, reason))
        self.code = code
        self.reason = reason


def accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")


def encode_frame(opcode: int, payload: bytes, fin: bool = True, mask_key: Optional[bytes] = None) -> bytes:
    """One frame. Clients must mask (mask_key defaults to 4 random bytes)."""
    if mask_key is None:
        mask_key = os.urandom(4)
    head = bytearray([(0x80 if fin else 0) | opcode])
    n = len(payload)
    if n < 126:
        head.append(0x80 | n)
    elif n < 1 << 16:
        head.append(0x80 | 126)
        head += struct.pack("!H", n)
    else:
        head.append(0x80 | 127)
        head += struct.pack("!Q", n)
    head += mask_key
    return bytes(head) + _mask(payload, mask_key)


def _mask(data: bytes, key: bytes) -> bytes:
    if not data:
        return b""
    # XOR with the repeated 4-byte key, done on integers for speed.
    repeated = (key * (len(data) // 4 + 1))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(repeated, "big")).to_bytes(len(data), "big")


class _Reader:
    """Exact-size reads from a socket with a leftover buffer (bytes after the HTTP headers)."""

    def __init__(self, sock: socket.socket, leftover: bytes = b""):
        self.sock = sock
        self.buf = bytearray(leftover)

    def read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise WebSocketClosed(1006, "socket closed")
            self.buf += chunk
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out


def decode_frame(read) -> Tuple[bool, int, bytes]:
    """Read one frame with `read(n)`; returns (fin, opcode, payload). Unmasks if masked."""
    b0, b1 = read(2)
    fin, opcode = bool(b0 & 0x80), b0 & 0x0F
    if b0 & 0x70:
        raise WebSocketError("reserved bits set (extensions are not supported)")
    masked, n = bool(b1 & 0x80), b1 & 0x7F
    if n == 126:
        n = struct.unpack("!H", read(2))[0]
    elif n == 127:
        n = struct.unpack("!Q", read(8))[0]
    if n > MAX_MESSAGE:
        raise WebSocketError("frame too large (%d bytes)" % n)
    key = read(4) if masked else None
    payload = read(n) if n else b""
    if key:
        payload = _mask(payload, key)
    return fin, opcode, payload


class WebSocket:
    def __init__(self, sock: socket.socket, leftover: bytes = b""):
        self.sock = sock
        self._reader = _Reader(sock, leftover)
        self._send_lock = threading.Lock()
        self.closed = False
        self.close_code: Optional[int] = None

    @classmethod
    def connect(cls, host: str, port: int, path: str = "/", timeout: float = 5.0) -> "WebSocket":
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            request = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                       "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, host, port, key))
            sock.sendall(request.encode("ascii"))
            raw = b""
            while b"\r\n\r\n" not in raw:
                chunk = sock.recv(4096)
                if not chunk:
                    raise WebSocketError("server closed during the handshake")
                raw += chunk
                if len(raw) > 65536:
                    raise WebSocketError("handshake response too large")
            head, leftover = raw.split(b"\r\n\r\n", 1)
            lines = head.decode("latin-1").split("\r\n")
            if " 101 " not in lines[0] + " ":
                raise WebSocketError("handshake refused: %s" % lines[0])
            headers = {}
            for line in lines[1:]:
                name, _, value = line.partition(":")
                headers[name.strip().lower()] = value.strip()
            if headers.get("sec-websocket-accept") != accept_key(key):
                raise WebSocketError("bad Sec-WebSocket-Accept")
            sock.settimeout(None)   # recv() blocks; close() from another thread unblocks it
            return cls(sock, leftover)
        except Exception:
            sock.close()
            raise

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        with self._send_lock:
            if self.closed:
                raise WebSocketClosed(self.close_code, "already closed")
            self.sock.sendall(encode_frame(opcode, payload))

    def send_text(self, text: str) -> None:
        self._send_frame(OP_TEXT, text.encode("utf-8"))

    def recv(self) -> Optional[str]:
        """Next text message, or None when the connection has been closed."""
        parts = []
        size = 0
        try:
            while True:
                fin, opcode, payload = decode_frame(self._reader.read)
                if opcode == OP_PING:
                    self._send_frame(OP_PONG, payload)
                    continue
                if opcode == OP_PONG:
                    continue
                if opcode == OP_CLOSE:
                    self.close_code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1005
                    self._shutdown(reply_close=True)
                    return None
                if opcode not in (OP_TEXT, OP_CONT, OP_BINARY):
                    raise WebSocketError("unknown opcode %d" % opcode)
                parts.append(payload)
                size += len(payload)
                if size > MAX_MESSAGE:
                    raise WebSocketError("message too large")
                if fin:
                    return b"".join(parts).decode("utf-8")
        except (OSError, WebSocketClosed):
            self._shutdown(reply_close=False)
            return None

    def close(self, code: int = 1000) -> None:
        try:
            self._send_frame(OP_CLOSE, struct.pack("!H", code))
        except (OSError, WebSocketClosed):
            pass
        self._shutdown(reply_close=False)

    def _shutdown(self, reply_close: bool) -> None:
        with self._send_lock:
            if self.closed:
                return
            if reply_close:
                try:
                    self.sock.sendall(encode_frame(OP_CLOSE, b""))
                except OSError:
                    pass
            self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
