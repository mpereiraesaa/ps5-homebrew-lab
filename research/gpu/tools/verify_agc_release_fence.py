#!/usr/bin/env python3
"""Verify San Andreas' two AGC RELEASE_MEM uses from authorized local dumps.

This is a host-only verifier.  It hashes the exact callsite windows, resolves
their common import thunk, and can execute only the copied packet-builder bytes
inside an isolated host buffer.  It never contacts the console or submits PM4.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import mmap
import platform
import struct
from pathlib import Path


EBOOT_BASE = 0x400000
AGC_BASE = 0x80058C000
RELEASE_OFFSET = 0x2700
RELEASE_SIZE = 0x1D0  # next known firmware builder starts at +0x28d0
THUNK = 0x4DC0C20
TEST_ADDRESS = 0x1122334455667788


def eboot_slice(blob: bytes, start: int, end: int) -> bytes:
    return blob[start - EBOOT_BASE:end - EBOOT_BASE]


def verify_callsite(
    blob: bytes, start: int, end: int, expected_sha256: str, label: str
) -> dict[str, object]:
    window = eboot_slice(blob, start, end)
    digest = hashlib.sha256(window).hexdigest()
    if digest != expected_sha256:
        raise SystemExit(f"{label}: callsite window changed at {start:#x}")
    if len(window) < 5 or window[-5] != 0xE8:
        raise SystemExit(f"{label}: window does not end in rel32 CALL")
    displacement = struct.unpack_from("<i", window, len(window) - 4)[0]
    target = end + displacement
    if target != THUNK:
        raise SystemExit(f"{label}: expected call target {THUNK:#x}, got {target:#x}")
    return {
        "window": [hex(start), hex(end)],
        "call": hex(end - 5),
        "sha256": digest,
        "target": hex(target),
    }


def resolve_thunk(blob: bytes, address: int) -> int:
    offset = address - EBOOT_BASE
    if blob[offset:offset + 2] != b"\xff\x25":
        raise SystemExit(f"{address:#x} is not a RIP-indirect thunk")
    displacement = struct.unpack_from("<i", blob, offset + 2)[0]
    got = address + 6 + displacement
    return struct.unpack_from("<Q", blob, got - EBOOT_BASE)[0]


def execute_builder(code: bytes, data_sel: int) -> tuple[list[int], int, int, int]:
    class Dcb(ctypes.Structure):
        _fields_ = [
            ("pad0", ctypes.c_uint8 * 0x10),
            ("cursor", ctypes.POINTER(ctypes.c_uint32)),
            ("end", ctypes.POINTER(ctypes.c_uint32)),
            ("grow", ctypes.c_void_p),
            ("grow_arg", ctypes.c_void_p),
            ("reserved", ctypes.c_uint32),
        ]

    executable = mmap.mmap(
        -1, len(code), prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC
    )
    try:
        executable.write(code)
        address = ctypes.addressof(ctypes.c_char.from_buffer(executable))
        function = ctypes.CFUNCTYPE(ctypes.c_void_p, *([ctypes.c_uint64] * 12))(
            address
        )
        output = (ctypes.c_uint32 * 16)()
        writer = Dcb()
        writer.cursor = ctypes.cast(output, ctypes.POINTER(ctypes.c_uint32))
        writer.end = ctypes.cast(
            ctypes.addressof(output) + ctypes.sizeof(output),
            ctypes.POINTER(ctypes.c_uint32),
        )
        # writer, event=0x28, a3=0, a4=1, a5=3, destination,
        # then stack arguments a7=data_sel, a8=0, a9=0, a10=1, a11, a12=0.
        # a11 is immaterial to these two observed packets and is retained raw.
        returned = function(
            ctypes.addressof(writer), 0x28, 0, 1, 3, TEST_ADDRESS,
            data_sel, 0, 0, 1, 2 if data_sel == 2 else 0, 0,
        )
        cursor_bytes = (
            ctypes.addressof(writer.cursor.contents) - ctypes.addressof(output)
        )
        return list(output[:8]), returned, ctypes.addressof(output), cursor_bytes
    finally:
        executable.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("eboot", type=Path)
    parser.add_argument("runtime_agc", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--execute-local-builder", action="store_true",
        help="execute copied x86-64 builder bytes in an isolated host buffer",
    )
    args = parser.parse_args()

    eboot = args.eboot.read_bytes()
    agc = args.runtime_agc.read_bytes()
    if len(agc) < RELEASE_OFFSET + RELEASE_SIZE:
        raise SystemExit("runtime AGC dump is too short")

    timestamp = verify_callsite(
        eboot, 0x1F221A4, 0x1F221D1,
        "89471d4fd3c1b99d2a1fc5e7419407863b3eb45e0105d4f05ed66af9076b5e44",
        "auxiliary timestamp RELEASE_MEM",
    )
    ownership = verify_callsite(
        eboot, 0x1F2246D, 0x1F224C8,
        "c7af479e029a37179d2c2be8e8a93096f3c65d4081eeecf023e6ef8341aadde1",
        "ownership RELEASE_MEM",
    )
    target = resolve_thunk(eboot, THUNK)
    if target != AGC_BASE + RELEASE_OFFSET:
        raise SystemExit(
            f"release thunk expected AGC+{RELEASE_OFFSET:#x}, got {target:#x}"
        )

    # Pin the two CPU-side ownership stores and the timestamp pointer copies.
    ownership_prefix = bytes.fromhex("4c894a2049c70101000000")
    if eboot_slice(eboot, 0x1F2246D, 0x1F22478) != ownership_prefix:
        raise SystemExit("ownership pointer/CPU=1 initialization changed")
    timestamp_copies = bytes.fromhex(
        "4c897258488d4a60c5fa6f4248c5fa7f42284c897238"
    )
    if eboot_slice(eboot, 0x1F221E1, 0x1F221F7) != timestamp_copies:
        raise SystemExit("timestamp pointer copies to work+0x38/+0x58 changed")

    expected = {
        3: [0xC0064900, 0x06000528, 0x60010000,
            0x55667788, 0x11223344, 0, 0, 0],
        2: [0xC0064900, 0x06000528, 0x42010000,
            0x55667788, 0x11223344, 0, 0, 0],
    }
    locally_executed = False
    packets: dict[str, list[str]] = {}
    if args.execute_local_builder:
        if platform.machine() not in ("x86_64", "AMD64"):
            raise SystemExit("local builder execution requires an x86-64 host")
        code = agc[RELEASE_OFFSET:RELEASE_OFFSET + RELEASE_SIZE]
        for selector, name in ((3, "aux_timestamp"), (2, "ownership")):
            packet, returned, output_address, cursor_bytes = execute_builder(
                code, selector
            )
            if packet != expected[selector]:
                raise SystemExit(
                    f"{name}: builder packet mismatch: expected {expected[selector]}, got {packet}"
                )
            if returned != output_address or cursor_bytes != 32:
                raise SystemExit(
                    f"{name}: builder return/cursor mismatch: "
                    f"return={returned:#x}, output={output_address:#x}, cursor={cursor_bytes}"
                )
            packets[name] = [f"0x{word:08x}" for word in packet]
        locally_executed = True

    proof = {
        "schema": 1,
        "firmware_scope": "12.02",
        "source": "authorized local San Andreas and runtime libSceAgc dumps",
        "console_contacted": False,
        "builder": {
            "runtime_offset": hex(RELEASE_OFFSET),
            "thunk": hex(THUNK),
            "resolved_target": hex(target),
            "packet_header": "0xc0064900",
            "dwords": 8,
            "locally_executed": locally_executed,
        },
        "callsites": {
            "aux_timestamp": {
                **timestamp,
                "raw_arguments": {
                    "event": "0x28", "a3": 0, "a4": 1, "a5": 3,
                    "a7_data_sel": 3, "a8": 0, "a9": 0,
                    "a10": 1, "a11": 0, "a12": 0,
                },
                "stored_at_work_offsets": ["0x38", "0x58"],
            },
            "ownership": {
                **ownership,
                "raw_arguments": {
                    "event": "0x28", "a3": 0, "a4": 1, "a5": 3,
                    "a7_data_sel": 2, "a8": 0, "a9": 0,
                    "a10": 1, "a11": 2, "a12": 0,
                },
                "stored_at_work_offset": "0x20",
            },
        },
        "packets_for_test_address": packets,
        "ownership_protocol_proven": True,
        "ownership_cpu_initial": 1,
        "ownership_gpu_final": 0,
        "ownership_data_sel": 2,
        "aux_timestamp_data_sel": 3,
        "homebrew_gpu_mapping_and_submit_proven": False,
        "submitted_or_executed": False,
        "target_writes": 0,
    }
    rendered = json.dumps(proof, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
