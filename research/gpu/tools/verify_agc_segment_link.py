#!/usr/bin/env python3
"""Pin the native AGC segment-link builder without contacting the console."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


EBOOT_BASE = 0x400000
AGC_BASE = 0x80058C000
THUNK = 0x4DC0C30
BUILDER_OFFSET = 0x21C0
CALL_START = 0x1F22410
CALL_END = 0x1F22446


def resolve_thunk(blob: bytes, address: int) -> int:
    offset = address - EBOOT_BASE
    if blob[offset:offset + 2] != b"\xff\x25":
        raise SystemExit(f"{address:#x} is not a RIP-indirect thunk")
    displacement = struct.unpack_from("<i", blob, offset + 2)[0]
    got = address + 6 + displacement
    return struct.unpack_from("<Q", blob, got - EBOOT_BASE)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("eboot", type=Path)
    parser.add_argument("runtime_agc", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    eboot = args.eboot.read_bytes()
    agc = args.runtime_agc.read_bytes()
    call = eboot[CALL_START - EBOOT_BASE:CALL_END - EBOOT_BASE]
    call_hash = hashlib.sha256(call).hexdigest()
    if call_hash != "5dafbe80137984025ba48f91714cdd75049fe8ae03092cd3c90aa8920dce43fd":
        raise SystemExit("native segment-link callsite changed")
    if call[-5] != 0xE8:
        raise SystemExit("segment-link window does not end in rel32 CALL")
    displacement = struct.unpack_from("<i", call, len(call) - 4)[0]
    if CALL_END + displacement != THUNK:
        raise SystemExit("segment-link call no longer targets the expected thunk")

    target = resolve_thunk(eboot, THUNK)
    if target != AGC_BASE + BUILDER_OFFSET:
        raise SystemExit(f"unexpected segment-link builder target {target:#x}")

    builder = agc[BUILDER_OFFSET:0x2368]
    builder_hash = hashlib.sha256(builder).hexdigest()
    if builder_hash != "e92b821d24d2ff9850344bf33acf4fef850381b71b5bb55bcb7c5186a58f9745":
        raise SystemExit("AGC segment-link builder changed")
    header_store = bytes.fromhex("c702003f0cc0")
    if builder.find(header_store) < 0:
        raise SystemExit("14-DWORD packet header store is missing")

    proof = {
        "schema": 1,
        "firmware_scope": "12.02",
        "source": "authorized local San Andreas and runtime libSceAgc dumps",
        "console_contacted": False,
        "callsite": {
            "address": hex(CALL_END - 5),
            "window": [hex(CALL_START), hex(CALL_END)],
            "sha256": call_hash,
            "thunk": hex(THUNK),
            "resolved_target": hex(target),
        },
        "builder": {
            "runtime_offset": hex(BUILDER_OFFSET),
            "sha256": builder_hash,
            "packet_header": "0xc00c3f00",
            "packet_dwords": 14,
        },
        "interpretation": {
            "role": "link/indirect-buffer packet used when the native writer rotates between command segments",
            "required_for_single_segment_stream": False,
            "root_cause_of_phase0r_timeout": False,
            "note": "The verifier proves callsite, target, header and size; it does not assign undocumented PS5 field names.",
        },
    }
    text = json.dumps(proof, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
