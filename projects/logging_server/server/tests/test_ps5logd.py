#!/usr/bin/env python3
"""Unit and loopback tests for ps5logd. Run: python3 -m unittest discover -s server/tests"""

from __future__ import annotations

import io
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ps5logd  # noqa: E402


def wait_for(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class ParsingTests(unittest.TestCase):
    def test_parse_hello(self) -> None:
        hello = ps5logd.parse_hello("HELLO ps5log/1 title=PPSA99998 app=agc-gears boot=0x1a2b tag=")
        assert hello is not None
        self.assertEqual(hello.protocol, "ps5log/1")
        self.assertEqual(hello.fields, {"title": "PPSA99998", "app": "agc-gears",
                                        "boot": "0x1a2b", "tag": ""})

    def test_parse_hello_rejects_other_lines(self) -> None:
        self.assertIsNone(ps5logd.parse_hello("HELLOWORLD"))
        self.assertIsNone(ps5logd.parse_hello("1\t2\tINFO\tHELLO ps5log/1"))

    def test_parse_bye(self) -> None:
        self.assertEqual(ps5logd.parse_bye("BYE seq=9 reason=complete"),
                         {"seq": "9", "reason": "complete"})
        self.assertEqual(ps5logd.parse_bye("BYE"), {})
        self.assertIsNone(ps5logd.parse_bye("BYEBYE"))
        self.assertIsNone(ps5logd.parse_bye("3\t4\tINFO\tBYE"))

    def test_parse_record_structured(self) -> None:
        record = ps5logd.parse_record("7\t123456789\tMARK\tSTAGE_E_GPU_FENCE_ZERO\tdetail=1")
        self.assertTrue(record.structured)
        self.assertEqual((record.seq, record.mono_ns, record.level), (7, 123456789, "MARK"))
        self.assertEqual(record.text, "STAGE_E_GPU_FENCE_ZERO\tdetail=1")

    def test_parse_record_empty_level_defaults_to_info(self) -> None:
        self.assertEqual(ps5logd.parse_record("1\t2\t\tx").level, "INFO")

    def test_parse_record_raw_fallbacks(self) -> None:
        for line in ("plain text", "a\tb\tc\td", "1\t2\tINFO", ""):
            record = ps5logd.parse_record(line)
            self.assertFalse(record.structured, line)
            self.assertEqual(record.level, "RAW")
            self.assertEqual(record.text, line)

    def test_safe_name(self) -> None:
        self.assertEqual(ps5logd.safe_name("PPSA99998", "x"), "PPSA99998")
        self.assertEqual(ps5logd.safe_name("../../etc/passwd", "x"), "etc-passwd")
        self.assertEqual(ps5logd.safe_name("", "fallback"), "fallback")
        self.assertEqual(len(ps5logd.safe_name("a" * 100, "x")), 48)


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="ps5logd-test-")
        self.root = Path(self.tmp.name)
        self.store = ps5logd.RunStore(self.root, keep=10)
        self.out = io.StringIO()
        self.printer = ps5logd.Printer(stream=self.out, color=False)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def session(self) -> ps5logd.Session:
        return ps5logd.Session(self.store, self.printer, "10.0.0.5:4000", "tcp")

    def test_full_run_with_gap_and_bye(self) -> None:
        session = self.session()
        session.feed(b"HELLO ps5log/1 title=PPSA99998 app=agc-gears boot=0x1\n")
        session.feed(b"1\t1000\tINFO\tfirst\n3\t3000\tWARN\tthird\nBYE seq=3 reason=complete\n")
        manifest = session.close("eof")
        assert manifest is not None
        self.assertEqual(manifest["title"], "PPSA99998")
        self.assertEqual(manifest["app"], "agc-gears")
        self.assertEqual(manifest["records"], 2)
        self.assertEqual(manifest["raw_lines"], 0)
        self.assertEqual(manifest["gaps"], [{"expected": 2, "got": 3}])
        self.assertTrue(manifest["clean"])
        self.assertTrue(manifest["hello"])
        self.assertEqual(manifest["bye_fields"], {"seq": "3", "reason": "complete"})
        self.assertEqual(manifest["first_seq"], 1)
        self.assertEqual(manifest["last_seq"], 3)
        self.assertAlmostEqual(manifest["device_span_s"], 2e-6)
        log_path = self.root / manifest["log_path"]
        self.assertEqual(
            log_path.read_bytes(),
            b"HELLO ps5log/1 title=PPSA99998 app=agc-gears boot=0x1\n"
            b"1\t1000\tINFO\tfirst\n3\t3000\tWARN\tthird\nBYE seq=3 reason=complete\n")
        self.assertIn("PPSA99998_agc-gears_0x1", log_path.name)
        stored = json.loads(log_path.with_suffix(".json").read_text())
        self.assertEqual(stored["sha256"], manifest["sha256"])
        latest = self.root / "latest_PPSA99998.log"
        self.assertTrue(latest.is_symlink())
        self.assertEqual(latest.resolve(), log_path.resolve())
        self.assertIn("sequence gap: expected 2, got 3", self.out.getvalue())

    def test_partial_lines_and_crlf(self) -> None:
        session = self.session()
        for chunk in (b"HELLO ps5log/1 ti", b"tle=T app=A\r\n1\t5\tINFO\tsp", b"lit\r\n2\t6\tINFO\twhole\n"):
            session.feed(chunk)
        manifest = session.close("eof")
        assert manifest is not None
        self.assertEqual(manifest["records"], 2)
        self.assertEqual(manifest["gaps"], [])
        self.assertFalse(manifest["clean"])
        text = (self.root / manifest["log_path"]).read_text()
        self.assertIn("1\t5\tINFO\tsplit\n", text)
        self.assertNotIn("\r", text)

    def test_raw_stream_without_hello(self) -> None:
        session = self.session()
        session.feed(b"just some text\nmore text")
        manifest = session.close("eof")
        assert manifest is not None
        self.assertFalse(manifest["hello"])
        self.assertEqual(manifest["title"], "unknown")
        self.assertEqual(manifest["raw_lines"], 2)
        self.assertEqual(manifest["records"], 0)
        self.assertEqual((self.root / manifest["log_path"]).read_text(),
                         "just some text\nmore text\n")

    def test_oversized_line_is_split_and_counted(self) -> None:
        session = self.session()
        session.feed(b"HELLO ps5log/1 title=T app=A\n")
        session.feed(b"x" * (ps5logd.MAX_LINE_BYTES + 10))
        session.feed(b"\n")
        manifest = session.close("eof")
        assert manifest is not None
        self.assertEqual(manifest["oversized_lines"], 1)
        self.assertEqual(manifest["raw_lines"], 2)

    def test_close_is_idempotent_and_empty_session_has_no_run(self) -> None:
        session = self.session()
        self.assertIsNone(session.close("eof"))
        self.assertIsNone(session.close("eof"))
        self.assertEqual(list(self.root.glob("*.log")), [])

    def test_retention_prunes_oldest(self) -> None:
        store = ps5logd.RunStore(self.root / "bounded", keep=1)
        for token in ("0x1", "0x2"):
            session = ps5logd.Session(store, self.printer, "p", "tcp")
            session.feed(f"HELLO ps5log/1 title=T app=A boot={token}\n".encode())
            session.close("eof")
            time.sleep(0.01)
        logs = [p for p in store.root.glob("*.log") if not p.is_symlink()]
        self.assertEqual(len(logs), 1)
        self.assertIn("0x2", logs[0].name)
        self.assertEqual(len(list(store.root.glob("*.json"))), 1)


class LoopbackServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="ps5logd-live-")
        self.root = Path(self.tmp.name)
        self.out = io.StringIO()
        self.printer = ps5logd.Printer(stream=self.out, color=False)
        self.server = ps5logd.Server(ps5logd.RunStore(self.root), self.printer,
                                     bind="127.0.0.1", port=0, udp=True,
                                     udp_idle_seconds=0.3, poll_interval=0.05)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def manifests(self) -> list[dict]:
        return [json.loads(p.read_text()) for p in sorted(self.root.glob("*.json"))]

    def test_tcp_roundtrip(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.port), timeout=5) as sock:
            sock.sendall(b"HELLO ps5log/1 title=PPSA99998 app=live boot=0x77\n")
            for seq in range(1, 4):
                sock.sendall(f"{seq}\t{seq * 1000}\tINFO\tline {seq}\n".encode())
            sock.sendall(b"BYE seq=3 reason=done\n")
        self.assertTrue(wait_for(lambda: len(self.manifests()) == 1))
        manifest = self.manifests()[0]
        self.assertEqual(manifest["transport"], "tcp")
        self.assertEqual(manifest["records"], 3)
        self.assertTrue(manifest["clean"])
        self.assertEqual(manifest["close_reason"], "eof")
        self.assertEqual(manifest["gaps"], [])

    def test_two_concurrent_tcp_clients_get_separate_runs(self) -> None:
        a = socket.create_connection(("127.0.0.1", self.server.port), timeout=5)
        b = socket.create_connection(("127.0.0.1", self.server.port), timeout=5)
        a.sendall(b"HELLO ps5log/1 title=A app=x\n1\t1\tINFO\ta\n")
        b.sendall(b"HELLO ps5log/1 title=B app=y\n1\t1\tINFO\tb\n")
        a.close()
        b.close()
        self.assertTrue(wait_for(lambda: len(self.manifests()) == 2))
        self.assertEqual(sorted(m["title"] for m in self.manifests()), ["A", "B"])

    def test_udp_datagrams_finalize_on_idle(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(b"HELLO ps5log/1 title=U app=udp boot=0x9", ("127.0.0.1", self.server.port))
            sock.sendto(b"1\t10\tINFO\tone\n2\t20\tINFO\ttwo\n", ("127.0.0.1", self.server.port))
        self.assertTrue(wait_for(lambda: len(self.manifests()) == 1, timeout=5))
        manifest = self.manifests()[0]
        self.assertEqual(manifest["transport"], "udp")
        self.assertEqual(manifest["records"], 2)
        self.assertEqual(manifest["close_reason"], "udp_idle")

    def test_shutdown_finalizes_open_sessions(self) -> None:
        sock = socket.create_connection(("127.0.0.1", self.server.port), timeout=5)
        sock.sendall(b"HELLO ps5log/1 title=S app=open\n1\t1\tINFO\tstill open\n")
        self.assertTrue(wait_for(lambda: "HELLO from" in self.out.getvalue()))
        self.server.shutdown()
        sock.close()
        manifests = self.manifests()
        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0]["close_reason"], "server_shutdown")
        self.assertFalse(manifests[0]["clean"])


if __name__ == "__main__":
    unittest.main()
