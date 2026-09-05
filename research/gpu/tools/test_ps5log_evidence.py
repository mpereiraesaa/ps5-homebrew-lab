#!/usr/bin/env python3
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ps5log_evidence import EvidenceError, validate_manifest


class Ps5logEvidenceTests(unittest.TestCase):
    def make_run(self, directory: Path) -> Path:
        data = (
            b"HELLO ps5log/1 title=PPSA99998 app=agc-native-sce boot=0x42\n"
            b"1\t100\tINFO\tLOG_SCHEMA=3\n"
            b"2\t101\tMARK\tLOG_BOOT_MONOTONIC_NS=0x0000000000000042\n"
            b"BYE seq=2 reason=cleanup-complete\n"
        )
        log = directory / "run.log"
        log.write_bytes(data)
        manifest = {
            "protocol": "ps5log/1", "transport": "tcp", "hello": True,
            "clean": True, "bye": True, "gaps": [], "oversized_lines": 0,
            "records": 2, "raw_lines": 0, "last_seq": 2,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "log_path": log.name,
            "identity": {"title": "PPSA99998", "app": "agc-native-sce",
                         "boot": "0x42"},
            "bye_fields": {"seq": "2", "reason": "cleanup-complete"},
        }
        path = directory / "run.json"
        path.write_text(json.dumps(manifest))
        return path

    def test_complete_structured_run_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = validate_manifest(self.make_run(Path(tmp)),
                                         expected_boot="0x00042")
            self.assertEqual(evidence["boot"], "0x42")

    def test_transcript_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(Path(tmp))
            (Path(tmp) / "run.log").write_bytes(b"tampered\n")
            with self.assertRaisesRegex(EvidenceError, "size/hash"):
                validate_manifest(path)

    def test_gap_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(Path(tmp))
            value = json.loads(path.read_text())
            value["gaps"] = [{"expected": 2, "got": 3}]
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(EvidenceError, "gaps"):
                validate_manifest(path)

    def test_hello_and_logged_boot_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(Path(tmp))
            value = json.loads(path.read_text())
            value["identity"]["boot"] = "0x43"
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(EvidenceError, "differ"):
                validate_manifest(path)


if __name__ == "__main__":
    unittest.main()
