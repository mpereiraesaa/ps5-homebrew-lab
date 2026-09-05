#!/usr/bin/env python3
"""Verify the extracted, authorized AGC shader corpus without touching the PS5."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path("research/gpu")
MANIFEST = ROOT / "captures/agc-authorized-shader-pairs.json"
SHADERS = ROOT / "shaders/san-andreas-authorized"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


manifest = json.loads(MANIFEST.read_text())
entries = manifest["entries"]
assert manifest["pairs_extracted"] == 47 == len(entries)
assert manifest["submitted_or_executed"] is False
assert manifest["all_self_relative_relocations_cross_checked"] is True
assert manifest["all_code_cross_checked_between_captures"] is True
assert Counter(entry["type_raw"] for entry in entries) == Counter({0: 31, 1: 15, 2: 1})

expected: set[str] = set()
for index, entry in enumerate(entries):
    assert entry["index"] == index
    for kind in ("header", "code"):
        name = entry[f"{kind}_file"]
        path = SHADERS / name
        expected.add(name)
        assert path.stat().st_size == entry[f"{kind}_bytes"]
        assert sha256(path) == entry[f"{kind}_sha256"]
    assert entry["header_code_field_initially_null"] is True
    assert entry["footer_barefoot"] is True

actual = {path.name for path in SHADERS.iterdir() if path.is_file()}
assert actual == expected
print(json.dumps({
    "manifest": str(MANIFEST),
    "pairs_verified": len(entries),
    "files_verified": len(actual),
    "type_raw_counts": manifest["type_raw_counts"],
    "graphics_pair_selected": manifest["graphics_pair_selected"],
    "console_contacted": False,
}, indent=2, sort_keys=True))
