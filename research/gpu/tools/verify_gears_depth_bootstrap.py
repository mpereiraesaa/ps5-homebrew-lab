#!/usr/bin/env python3
"""Gate the topology-independent D32 bootstrap and its fail-closed edges."""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PAL = ROOT / "third_party/amd-pal/src/core/hw/gfxip/gfx9"
MESA = ROOT / "third_party/mesa-gfx1013/src/amd/addrlib/src"
CAPTURE = ROOT / "research/gpu/captures/san-andreas-attachment-control-paths.json"


def need(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, re.MULTILINE | re.DOTALL) is None:
        raise SystemExit(f"gears depth bootstrap failed: {label}")


def main() -> int:
    addrlib2 = (MESA / "core/addrlib2.cpp").read_text()
    gfx10 = (MESA / "gfx10/gfx10addrlib.cpp").read_text()
    depth_view = (PAL / "gfx9DepthStencilView.cpp").read_text()
    depth_state = (PAL / "gfx9DepthStencilState.cpp").read_text()
    shifts = (PAL / "chip/gfx9_plus_merged_shift.h").read_text()
    capture = json.loads(CAPTURE.read_text())

    need(addrlib2, r"log2NumEle\s*=\s*log2BlkSize\s*-\s*log2EleBytes\s*-\s*log2Samples",
         "missing thin-block element formula")
    need(gfx10, r"pOut->surfSize\s*=\s*pOut->sliceSize\s*\*\s*pOut->numSlices",
         "missing single-mip surface-size formula")
    need(depth_view,
         r"TILE_SURFACE_ENABLE\s*=\s*0;.*?TILE_STENCIL_DISABLE\s*=\s*1;.*?"
         r"DEPTH_COMPRESS_DISABLE\s*=\s*1;.*?STENCIL_COMPRESS_DISABLE\s*=\s*1;",
         "PAL no-HTILE state contract changed")
    need(depth_state,
         r"Z_ENABLE\s*=.*?Z_WRITE_ENABLE\s*=.*?ZFUNC\s*=\s*HwDepthCompare.*?"
         r"BACKFACE_ENABLE\s*=\s*1;",
         "PAL depth-test state construction changed")

    expected_shifts = {
        "DB_Z_INFO__FORMAT": 0,
        "DB_Z_INFO__SW_MODE": 4,
        "DB_Z_INFO__TILE_SURFACE_ENABLE": 29,
        "DB_STENCIL_INFO__SW_MODE": 4,
        "DB_STENCIL_INFO__TILE_STENCIL_DISABLE": 29,
        "DB_RENDER_CONTROL__STENCIL_COMPRESS_DISABLE": 5,
        "DB_RENDER_CONTROL__DEPTH_COMPRESS_DISABLE": 6,
        "DB_DEPTH_CONTROL__Z_ENABLE": 1,
        "DB_DEPTH_CONTROL__Z_WRITE_ENABLE": 2,
        "DB_DEPTH_CONTROL__ZFUNC": 4,
        "DB_DEPTH_CONTROL__BACKFACE_ENABLE": 7,
    }
    for name, expected in expected_shifts.items():
        match = re.search(rf"{name}__SHIFT\s*=\s*0x([0-9a-fA-F]+);", shifts)
        if match is None or int(match.group(1), 16) != expected:
            raise SystemExit(f"gears depth bootstrap failed: {name} shift drift")

    width, height, bpp, samples = 1920, 1080, 32, 1
    log2_elements = 16 - (bpp // 8).bit_length() + 1 - (samples.bit_length() - 1)
    log2_width = (log2_elements + 1) // 2
    block_width = 1 << log2_width
    block_height = 1 << (log2_elements - log2_width)
    pitch = (width + block_width - 1) // block_width * block_width
    padded_height = (height + block_height - 1) // block_height * block_height
    size = pitch * padded_height * (bpp // 8)
    if (block_width, block_height, pitch, padded_height, size) != (128, 128, 1920, 1152, 0x870000):
        raise SystemExit("gears depth bootstrap failed: D32 footprint mismatch")

    swizzle = 24  # public ADDR_SW_64KB_Z_X
    registers = {
        "DB_DEPTH_VIEW": 0,
        "DB_DEPTH_SIZE_XY": (width - 1) | ((height - 1) << 16),
        "DB_STENCIL_CLEAR": 0,
        "DB_DEPTH_CLEAR": struct.unpack("<I", struct.pack("<f", 1.0))[0],
        "DB_Z_INFO": 3 | (swizzle << 4),  # Z_32_FLOAT, 1xAA, no HTILE
        "DB_STENCIL_INFO": (swizzle << 4) | (1 << 29),
        "DB_RENDER_CONTROL": (1 << 5) | (1 << 6),
        "DB_DEPTH_CONTROL": (1 << 1) | (1 << 2) | (3 << 4) | (1 << 7),
    }
    expected_registers = {
        "DB_DEPTH_VIEW": 0x00000000,
        "DB_DEPTH_SIZE_XY": 0x0437077F,
        "DB_STENCIL_CLEAR": 0x00000000,
        "DB_DEPTH_CLEAR": 0x3F800000,
        "DB_Z_INFO": 0x00000183,
        "DB_STENCIL_INFO": 0x20000180,
        "DB_RENDER_CONTROL": 0x00000060,
        "DB_DEPTH_CONTROL": 0x000000B6,
    }
    if registers != expected_registers:
        raise SystemExit(f"gears depth bootstrap failed: register plan drift {registers!r}")

    # A permutation cannot alter a field whose every element has the same word.
    clear_words = [registers["DB_DEPTH_CLEAR"]] * (size // 4)
    for permutation in ((0, 1, 2, 3), (3, 1, 0, 2), (2, 0, 3, 1)):
        if [clear_words[i] for i in permutation] != [0x3F800000] * 4:
            raise SystemExit("gears depth bootstrap failed: uniform-fill invariant")

    path = capture["paths"]["color_depth_flags_0x3c00"]
    if path["derived_terminal_event_type"] != "0x14":
        raise SystemExit("gears depth bootstrap failed: terminal depth event drift")
    if "0x2c" not in path["public_amd_event_candidates"]:
        raise SystemExit("gears depth bootstrap failed: DB metadata event missing")
    protocol = capture["private_label_protocol"]
    if len(protocol) != 4 or "ACQUIRE_MEM covers the same 32-byte label allocation" not in protocol:
        raise SystemExit("gears depth bootstrap failed: completion-label protocol drift")
    if capture["selected_acquire_mem_call"]["range_bytes"] != 32:
        raise SystemExit("gears depth bootstrap failed: observed ACQUIRE range drift")

    print("gears depth bootstrap passed: D32 0x870000-byte uniform main plane, "
          "public no-HTILE/depth-test register plan, and observed post-draw "
          "DB completion chain; pre-draw clear visibility remains a separate gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
