#!/usr/bin/env python3
"""Pin authorized game callsites to the FW 12.02 CreateShader export."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


EBOOT_BASE = 0x400000
GOT_SLOT = 0x67F8DE0
PLT_THUNK = 0x5A7D460
INITIALIZER_START = 0x59CB1F0
INITIALIZER_END = 0x59CBC6D
GENERIC_CALL = 0x5A483C4
LIB_BASE = 0x80058C000
CREATE_SHADER_OFFSET = 0xEF70


def rip_target(blob: bytes, instruction: int, opcode: bytes) -> int:
    if blob[instruction:instruction + 3] != opcode:
        raise SystemExit(f"unexpected LEA at {instruction:#x}")
    return instruction + 7 + struct.unpack_from("<i", blob, instruction + 3)[0]


def direct_calls(blob: bytes, target: int) -> list[int]:
    result = []
    for offset in range(len(blob) - 5):
        if blob[offset] == 0xE8 and offset + 5 + struct.unpack_from(
                "<i", blob, offset + 1)[0] == target:
            result.append(offset)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eboot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    blob = args.eboot.read_bytes()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    resolved = struct.unpack_from("<Q", blob, GOT_SLOT)[0]
    if resolved != LIB_BASE + CREATE_SHADER_OFFSET:
        raise SystemExit("CreateShader GOT slot does not resolve to pinned FW export")
    expected_thunk = bytes.fromhex("ff257ab9d70068ce020000e900d3ffff")
    if blob[PLT_THUNK:PLT_THUNK + len(expected_thunk)] != expected_thunk:
        raise SystemExit("CreateShader PLT thunk changed")

    calls = direct_calls(blob, PLT_THUNK)
    initializer_calls = [c for c in calls if INITIALIZER_START <= c < INITIALIZER_END]
    if len(initializer_calls) != 47 or calls != initializer_calls + [GENERIC_CALL]:
        raise SystemExit(f"unexpected CreateShader callsite inventory: {len(calls)}")

    observed = []
    for call, entry in zip(initializer_calls, manifest["entries"]):
        destination = rip_target(blob, call - 21, bytes.fromhex("488d3d"))
        header = rip_target(blob, call - 14, bytes.fromhex("488d35"))
        code = rip_target(blob, call - 7, bytes.fromhex("488d15"))
        expected_header = 0x67FC000 + (int(entry["source_header_offset"], 16) - 0x62DC000)
        if header != expected_header:
            raise SystemExit("callsite header does not match authorized relocated arena")
        bound_code = struct.unpack_from("<Q", blob, header + 0x10)[0] - EBOOT_BASE
        if code != bound_code:
            raise SystemExit("callsite code does not match header's bound runtime outcome")
        if destination % 8 or code % 0x100:
            raise SystemExit("callsite destination/code alignment mismatch")
        return_check = blob[call + 5:call + 12]
        if return_check not in (bytes.fromhex("bb02006c8a85c0"),
                                bytes.fromhex("89c385c0741d49")):
            raise SystemExit("callsite no longer checks constructor return")
        observed.append((call, destination, header, code))

    digest = hashlib.sha256(json.dumps(observed, separators=(",", ":")).encode()).hexdigest()
    init_hash = hashlib.sha256(blob[INITIALIZER_START:INITIALIZER_END]).hexdigest()
    result = {
        "schema": 1,
        "firmware": "12.02",
        "title_capture": "authorized owned-game runtime",
        "got_resolves_pinned_create_shader": True,
        "plt_thunk_verified": True,
        "direct_initializer_calls": 47,
        "generic_wrapper_calls": 1,
        "all_three_arguments_correlated": True,
        "all_return_values_checked": True,
        "all_headers_match_cross_capture_relocated_outcomes": True,
        "initializer_sha256": init_hash,
        "sanitized_callsite_digest": digest,
        "raw_bytes_emitted": False,
        "shader_bytes_emitted": False,
        "console_contacted": False,
        "create_shader_called": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
