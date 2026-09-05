#!/usr/bin/env python3
"""Verify sanitized AGC defaults evidence against the local analysis ELF."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CAPTURE = ROOT / "research/gpu/captures/agc-native-sce-phase2-defaults.json"
ANALYSIS = ROOT / "research/gpu/ghidra/game-libSceAgc.analysis.elf"

FILE_OFFSETS = {
    "root": 0x2C180,
    "table_cx": 0x3B450,
    "table_sh": 0x3B6F0,
    "table_uc": 0x3B7F0,
    "type_index_pairs": 0x20EC0,
}


def main() -> int:
    evidence = json.loads(CAPTURE.read_text(encoding="utf-8"))
    expected = evidence["static_correlation"]["sha256_by_block"]
    blob = ANALYSIS.read_bytes()
    actual = {
        name: hashlib.sha256(blob[offset:offset + 64]).hexdigest()
        for name, offset in FILE_OFFSETS.items()
    }
    if actual != expected:
        raise SystemExit(f"AGC defaults correlation mismatch: {actual}")
    if evidence["layout"]["size"] != 0x40 or evidence["layout"]["count"] != 0x89:
        raise SystemExit("unexpected AGC defaults layout/count")
    if not evidence["repeatability"]["all_five_hashes_equal"]:
        raise SystemExit("cross-process repeatability is not proven")
    print(json.dumps({"verified": True, "blocks": actual}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
