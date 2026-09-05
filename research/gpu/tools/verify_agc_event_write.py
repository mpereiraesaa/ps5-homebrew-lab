#!/usr/bin/env python3
"""Byte-verify the FW 12.02 AGC EVENT_WRITE builder cases used by the game."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


BUILDER = 0x5CE0
SYSTEM_TEXT_FILE_OFFSET = 0x4000
FUNCTION_BYTES = 0x180


def require(blob: bytes, offset: int, expected: bytes, label: str) -> None:
    actual = blob[offset : offset + len(expected)]
    if actual != expected:
        raise SystemExit(
            f"{label}: expected {expected.hex()} at 0x{offset:x}, got {actual.hex()}"
        )


def packet(selector: int) -> list[str]:
    if selector not in (7, 0x10):
        raise ValueError("this verifier covers only the two observed partial-flush cases")
    return ["0xc0004600", f"0x{selector | 0x400:08x}"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("system_agc", type=Path)
    parser.add_argument("runtime_agc", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    system = args.system_agc.read_bytes()
    runtime = args.runtime_agc.read_bytes()
    system_fn = SYSTEM_TEXT_FILE_OFFSET + BUILDER
    if system[system_fn : system_fn + FUNCTION_BYTES] != runtime[BUILDER : BUILDER + FUNCTION_BYTES]:
        raise SystemExit("system/runtime EVENT_WRITE builder mismatch")

    # Normal cases allocate two DWORD and construct header 0xc0004600.
    require(runtime, BUILDER + 0x45,
            bytes.fromhex("81c10000fe3f81c9004600c0894dc8"),
            "EVENT_WRITE header construction")
    # Bitset 0x18080 selects API values 7, 15, and 16 and ORs payload bit 0x400.
    require(runtime, BUILDER + 0x5F,
            bytes.fromhex("41b880800100490fa3c8730e400fb6c60d000400008945cc"),
            "partial-flush event-index encoding")
    # The generic fallback masks the event selector to six bits.
    require(runtime, BUILDER + 0x14D,
            bytes.fromhex("4080e63f400fb6ce894dcc"),
            "generic event selector mask")

    result = {
        "schema": 1,
        "firmware": "12.02",
        "builder": "libSceAgc+0x5ce0",
        "system_runtime_equal": True,
        "packet_opcode": "EVENT_WRITE (0x46)",
        "observed_cases": {
            "api_selector_7": {
                "dwords": packet(7),
                "public_amd_candidate": "CS_PARTIAL_FLUSH",
            },
            "api_selector_0x10": {
                "dwords": packet(0x10),
                "public_amd_candidate": "PS_PARTIAL_FLUSH",
            },
        },
        "event_index_bits": "0x400",
        "ps5_semantic_names_proven": False,
        "corroboration_level": "strong architectural match, not PS5 ABI proof",
        "submitted_or_executed": False,
        "target_writes": 0,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
