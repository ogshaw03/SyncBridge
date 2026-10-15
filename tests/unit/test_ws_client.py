"""stdlib WebSocket client against a tiny stdlib WebSocket server (no packages needed)."""
import base64
import hashlib
import socket
import struct
import threading
import unittest

from syncbridge.client import ws
from syncbridge.client.ws import OP_CLOSE, OP_CONT, OP_PING, OP_PONG, OP_TEXT


def server_frame(opcode, payload, fin=True):
    """Unmasked server -> client frame."""
    head = bytearray([(0x80 if fin else 0) | opcode])
    n = len(payload)
    if n < 126:
        head.append(n)
    elif n < 1 << 16:
        head.append(126)
        head += struct.pack("!H", n)
    else:
        head.append(127)
        head += struct.pack("!Q", n)
    return bytes(head) + payload


class TinyServer:
    """Accepts one client; `script(conn, read_frame)` drives the conversation."""

    def __init__(self, script, refuse=False, bad_accept=False):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.script, self.refuse, self.bad_accept = script, refuse, bad_accept
        self.received = []
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            conn, _ = self.sock.accept()
            with conn:
                raw = b""
                while b"\r\n\r\n" not in raw:
                    raw += conn.recv(4096)
                headers = dict(l.split(": ", 1) for l in raw.decode().split("\r\n")[1:] if ": " in l)
                if self.refuse:
                    conn.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                    return
                accept = base64.b64encode(hashlib.sha1(
                    (headers["Sec-WebSocket-Key"] + ws.GUID).encode()).digest()).decode()
                if self.bad_accept:
                    accept = "x" + accept
                conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                              "Connection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
                reader = ws._Reader(conn)
                self.script(conn, lambda: self._read(reader))
        except Exception as exc:  # surfaced by the test
            self.error = exc
        finally:
            self.sock.close()

    def _read(self, reader):
        fin, op, payload = ws.decode_frame(reader.read)
        self.received.append((op, payload))
        return op, payload


class FrameTest(unittest.TestCase):
    def test_rfc_accept_key(self):
        self.assertEqual(ws.accept_key("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def test_roundtrip_all_length_encodings(self):
        for n in (0, 1, 125, 126, 65535, 65536, 200000):
            payload = bytes(i % 251 for i in range(n))
            frame = ws.encode_frame(OP_TEXT, payload, mask_key=b"\x01\x02\x03\x04")
            buf = bytearray(frame)

            def read(k):
                out = bytes(buf[:k])
                del buf[:k]
                return out
            fin, op, back = ws.decode_frame(read)
            self.assertEqual((fin, op, back), (True, OP_TEXT, payload), n)
            self.assertEqual(len(buf), 0)

    def test_client_frames_are_masked(self):
        frame = ws.encode_frame(OP_TEXT, b"hello")
        self.assertTrue(frame[1] & 0x80)
        self.assertNotIn(b"hello", frame)


class ClientTest(unittest.TestCase):
    def test_echo_ping_fragments_and_close(self):
        def script(conn, read_frame):
            op, payload = read_frame()                       # "hello"
            conn.sendall(server_frame(OP_PING, b"p1"))       # client must pong
            conn.sendall(server_frame(OP_TEXT, "日本".encode(), fin=False))   # fragmented message
            conn.sendall(server_frame(OP_CONT, "語!".encode(), fin=True))
            conn.sendall(server_frame(OP_TEXT, b"x" * 70000))
            op, _ = read_frame()                             # pong
            conn.sendall(server_frame(OP_CLOSE, struct.pack("!H", 1000)))
            read_frame()                                     # close reply

        srv = TinyServer(script)
        c = ws.WebSocket.connect("127.0.0.1", srv.port, "/ws")
        c.send_text("hello")
        self.assertEqual(c.recv(), "日本語!")
        self.assertEqual(c.recv(), "x" * 70000)
        self.assertIsNone(c.recv())
        self.assertEqual(c.close_code, 1000)
        self.assertTrue(c.closed)
        srv.thread.join(5)
        self.assertIsNone(srv.error)
        ops = [op for op, _ in srv.received]
        self.assertEqual(ops, [OP_TEXT, OP_PONG, OP_CLOSE])
        self.assertEqual(srv.received[0][1], b"hello")
        self.assertEqual(srv.received[1][1], b"p1")
        with self.assertRaises(ws.WebSocketClosed):
            c.send_text("after close")

    def test_close_from_another_thread_unblocks_recv(self):
        done = threading.Event()

        def script(conn, read_frame):
            read_frame()          # wait for the client's close frame
            done.set()

        srv = TinyServer(script)
        c = ws.WebSocket.connect("127.0.0.1", srv.port, "/ws")
        result = {}
        t = threading.Thread(target=lambda: result.update(r=c.recv()))
        t.start()
        c.close()
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertIsNone(result["r"])
        self.assertTrue(done.wait(5))

    def test_server_disappears(self):
        srv = TinyServer(lambda conn, read_frame: None)    # closes right after the handshake
        c = ws.WebSocket.connect("127.0.0.1", srv.port, "/ws")
        self.assertIsNone(c.recv())

    def test_handshake_refused(self):
        srv = TinyServer(None, refuse=True)
        with self.assertRaises(ws.WebSocketError):
            ws.WebSocket.connect("127.0.0.1", srv.port, "/ws")

    def test_bad_accept(self):
        srv = TinyServer(None, bad_accept=True)
        with self.assertRaises(ws.WebSocketError):
            ws.WebSocket.connect("127.0.0.1", srv.port, "/ws")

    def test_nothing_listening(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with self.assertRaises(OSError):
            ws.WebSocket.connect("127.0.0.1", port, "/ws", timeout=1)


if __name__ == "__main__":
    unittest.main()
