#!/usr/bin/env python3
"""Compose the bounded DMA_DATA + ownership-fence stream entirely on the host.

The addresses are deliberately synthetic.  The result is a packet-composition
proof, not a submit-ready command buffer and never contacts the console.
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


DMA_OFFSET = 0x47D0
DMA_SIZE = 0x1DD
RELEASE_OFFSET = 0x2700
RELEASE_SIZE = 0x1D0
DEFAULT_TARGET = 0x1122334455667000
DEFAULT_FENCE = 0x1122334455667800


class Dcb(ctypes.Structure):
    _fields_ = [
        ("pad0", ctypes.c_uint8 * 0x10),
        ("cursor", ctypes.POINTER(ctypes.c_uint32)),
        ("end", ctypes.POINTER(ctypes.c_uint32)),
        ("grow", ctypes.c_void_p),
        ("grow_arg", ctypes.c_void_p),
        ("reserved", ctypes.c_uint32),
    ]


def map_function(code: bytes) -> tuple[mmap.mmap, object]:
    mapping = mmap.mmap(
        -1, len(code), prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC
    )
    mapping.write(code)
    address = ctypes.addressof(ctypes.c_char.from_buffer(mapping))
    function = ctypes.CFUNCTYPE(ctypes.c_void_p, *([ctypes.c_uint64] * 12))(
        address
    )
    return mapping, function


def expected_dma(target: int) -> list[int]:
    return [
        0xC0055000, 0xC0300000, 0, 0,
        target & 0xFFFFFFFF, (target >> 32) & 0xFFFFFFFF, 4,
    ]


def expected_fence(fence: int) -> list[int]:
    return [
        0xC0064900, 0x06000528, 0x42010000,
        fence & 0xFFFFFFFF, (fence >> 32) & 0xFFFFFFFF, 0, 0, 0,
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime_agc", type=Path)
    parser.add_argument("--target-address", type=lambda x: int(x, 0), default=DEFAULT_TARGET)
    parser.add_argument("--fence-address", type=lambda x: int(x, 0), default=DEFAULT_FENCE)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-bin", type=Path)
    args = parser.parse_args()

    if platform.machine() not in ("x86_64", "AMD64"):
        raise SystemExit("isolated builder execution requires an x86-64 host")
    if args.target_address == 0 or args.target_address & 3:
        raise SystemExit("synthetic target address must be nonzero and 4-byte aligned")
    if args.fence_address == 0 or args.fence_address & 7:
        raise SystemExit("synthetic fence address must be nonzero and 8-byte aligned")
    if not (args.target_address + 4 <= args.fence_address
            or args.fence_address + 8 <= args.target_address):
        raise SystemExit("target and fence ranges overlap")

    agc = args.runtime_agc.read_bytes()
    if len(agc) < DMA_OFFSET + DMA_SIZE:
        raise SystemExit("runtime AGC dump is too short")

    dma_map, dma = map_function(agc[DMA_OFFSET:DMA_OFFSET + DMA_SIZE])
    release_map, release = map_function(
        agc[RELEASE_OFFSET:RELEASE_OFFSET + RELEASE_SIZE]
    )
    try:
        output = (ctypes.c_uint32 * 32)()
        output_address = ctypes.addressof(output)
        writer = Dcb()
        writer.cursor = ctypes.cast(output, ctypes.POINTER(ctypes.c_uint32))
        writer.end = ctypes.cast(
            output_address + ctypes.sizeof(output), ctypes.POINTER(ctypes.c_uint32)
        )

        dma_return = dma(
            ctypes.addressof(writer), 0, 3, 0, args.target_address,
            2, 0, 0, 4, 0, 0, 1,
        )
        after_dma = ctypes.addressof(writer.cursor.contents) - output_address
        if dma_return != output_address or after_dma != 28:
            raise SystemExit("DMA builder did not emit exactly seven DWORDs")

        release_return = release(
            ctypes.addressof(writer), 0x28, 0, 1, 3, args.fence_address,
            2, 0, 0, 1, 2, 0,
        )
        after_release = ctypes.addressof(writer.cursor.contents) - output_address
        if release_return != output_address + 28 or after_release != 60:
            raise SystemExit("RELEASE_MEM builder did not append exactly eight DWORDs")

        words = list(output[:15])
        expected = expected_dma(args.target_address) + expected_fence(args.fence_address)
        if words != expected:
            raise SystemExit(f"composed stream mismatch: expected {expected}, got {words}")
        binary = struct.pack("<15I", *words)
    finally:
        release_map.close()
        dma_map.close()

    proof = {
        "schema": 1,
        "firmware_scope": "12.02",
        "console_contacted": False,
        "synthetic_addresses_only": True,
        "submit_ready": False,
        "submitted_or_executed_by_gpu": False,
        "purpose": "four-byte private-memory DMA write followed by independent ownership fence",
        "cpu_preconditions_for_future_probe": {
            "target_u32": "nonzero canary",
            "fence_u64": 1,
        },
        "expected_gpu_postconditions_for_future_probe": {
            "target_u32": 0,
            "fence_u64": 0,
        },
        "synthetic_target_address": hex(args.target_address),
        "synthetic_fence_address": hex(args.fence_address),
        "stream_bytes": len(binary),
        "stream_dwords": len(words),
        "packet_boundaries_dwords": [0, 7, 15],
        "packets": {
            "dma_data": [f"0x{x:08x}" for x in words[:7]],
            "ownership_release_mem": [f"0x{x:08x}" for x in words[7:]],
        },
        "stream_sha256": hashlib.sha256(binary).hexdigest(),
        "gates_still_required": [
            "homebrew-owned AGC graphics queue",
            "effective GPU mapping for command, target and fence memory",
            "verified coherency and CPU acquire-read contract",
            "bounded submit and timeout-safe cleanup",
        ],
    }
    rendered = json.dumps(proof, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered)
    if args.output_bin:
        args.output_bin.parent.mkdir(parents=True, exist_ok=True)
        args.output_bin.write_bytes(binary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
