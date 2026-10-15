import unittest

from syncbridge import protocol
from syncbridge.core import jobs


class ProtocolTest(unittest.TestCase):
    def test_roundtrip(self):
        msg = protocol.message("hello", {"token": "t", "app": "maya", "pid": 1}, "maya")
        back = protocol.decode(protocol.encode(msg))
        self.assertEqual(back["kind"], "hello")
        self.assertEqual(back["data"]["app"], "maya")

    def test_reply_links_request(self):
        req = protocol.message("export.request", {})
        rep = protocol.reply(req, {"export": {}}, "ae")
        self.assertEqual(rep["kind"], "export.result")
        self.assertEqual(rep["reply_to"], req["event_id"])
        with self.assertRaises(protocol.ProtocolError):
            protocol.reply(rep)

    def test_rejects_bad_messages(self):
        bad = [
            "not json",
            "[1, 2]",
            '{"schema": "other"}',
            protocol.encode(protocol.message("hello", {"app": "maya"})),            # no token
            protocol.encode(protocol.message("hello", {"token": "t", "app": "nuke"})),
            protocol.encode(protocol.message("transfer.request", {"direction": "sideways"})),
            protocol.encode(protocol.message("apply.result", {"status": "maybe"})),
        ]
        for text in bad:
            with self.assertRaises(protocol.ProtocolError, msg=text[:60]) as ctx:
                protocol.decode(text)
            self.assertEqual(ctx.exception.code, protocol.E_BAD_MESSAGE)

    def test_error_message(self):
        err = protocol.decode(protocol.encode(protocol.error(protocol.E_NO_PEER, "no AE", reply_to="x")))
        self.assertEqual(err["data"]["code"], "no_peer")
        self.assertEqual(err["reply_to"], "x")


class TransferOptionsTest(unittest.TestCase):
    def test_json_roundtrip(self):
        opts = jobs.TransferOptions(mode="precision", origin=1001, range_frames=(1001, 1100))
        back = jobs.TransferOptions.from_json(opts.to_json())
        self.assertEqual(back, opts)

    def test_rejects_unknown_and_bad_mode(self):
        with self.assertRaises(ValueError):
            jobs.TransferOptions.from_json({"bogus": 1})
        with self.assertRaises(ValueError):
            jobs.TransferOptions.from_json({"mode": "fast"})
        self.assertEqual(jobs.TransferOptions.from_json(None).mode, "editable")


if __name__ == "__main__":
    unittest.main()
