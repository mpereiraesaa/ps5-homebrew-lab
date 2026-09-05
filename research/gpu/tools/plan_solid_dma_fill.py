#!/usr/bin/env python3
"""Compute bounded PS5 tiled-buffer sizes for a proposed solid DMA fill.

This is a planning tool only.  It never connects to a console or emits a
command buffer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TILE_WIDTH = 512
TILE_HEIGHT = 128
TILE_PIXELS = TILE_WIDTH * TILE_HEIGHT
BYTES_PER_PIXEL = 4
DMA_MAX_BYTES = 0x03FFFFFF
DMA_HEADER = 0xC0055000
DMA_IMMEDIATE_SYNC_CONTROL = 0xC0300000
PAL_COMMIT = "c5e800072a32f68b6ccc4422936d96167c6e0728"


def tiled_size(width: int, height: int) -> int:
    if width <= 0 or height <= 0:
        raise ValueError("dimensions must be positive")
    last_band = ((height - 1) // TILE_HEIGHT) * (TILE_HEIGHT * width)
    last_tile = ((width - 1) // TILE_WIDTH) * TILE_PIXELS
    return (last_band + last_tile + TILE_PIXELS) * BYTES_PER_PIXEL


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("width", type=int)
    parser.add_argument("height", type=int)
    parser.add_argument("--bgra", type=lambda value: int(value, 0),
                        default=0xFFFF0000,
                        help="repeated little-endian BGRA DWORD")
    parser.add_argument("--destination", type=lambda value: int(value, 0),
                        default=0x1122334450000000,
                        help="synthetic or future GPU destination address")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    size = tiled_size(args.width, args.height)
    if not 0 <= args.bgra <= 0xFFFFFFFF:
        raise SystemExit("BGRA value must fit in one DWORD")
    if not 0 <= args.destination <= 0xFFFFFFFFFFFFFFFF:
        raise SystemExit("destination must fit in one QWORD")
    if args.destination & 3:
        raise SystemExit("destination must be DWORD aligned")
    packet = [
        DMA_HEADER,
        DMA_IMMEDIATE_SYNC_CONTROL,
        args.bgra,
        0,
        args.destination & 0xFFFFFFFF,
        args.destination >> 32,
        size,
    ]
    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "dimensions": [args.width, args.height],
        "tile": [TILE_WIDTH, TILE_HEIGHT],
        "bytes_per_pixel": BYTES_PER_PIXEL,
        "tiled_bytes": size,
        "tiled_bytes_hex": f"0x{size:08x}",
        "dma_26bit_max": DMA_MAX_BYTES,
        "fits_one_dma_packet": size <= DMA_MAX_BYTES,
        "solid_bgra_dword": f"0x{args.bgra:08x}",
        "swizzle_invariant_for_solid_color": True,
        "dma_data": {
            "packet_dwords": [f"0x{word:08x}" for word in packet],
            "packet_size_dwords": 7,
            "source_select": "immediate_data",
            "immediate_dword_repeated_for_byte_count": True,
            "destination": f"0x{args.destination:016x}",
            "destination_is_synthetic": True,
            "cp_sync": True,
            "raw_wait": False,
            "write_confirm_enabled": True,
        },
        "primary_source_evidence": {
            "repository": "https://github.com/GPUOpen-Drivers/pal",
            "commit": PAL_COMMIT,
            "builder": "src/core/hw/gfxip/gfx9/gfx9CmdUtil.cpp::BuildDmaData",
            "fill_usage": "src/core/hw/gfxip/gfx9/gfx9OcclusionQueryPool.cpp",
            "immediate_range_fill_semantics_proven": True,
        },
        "gpu_visibility_proven": False,
        "cache_transition_proven": False,
        "display_coherency_proven": False,
        "flip_after_gpu_fence_proven": False,
        "submitted": False,
    }
    if not result["fits_one_dma_packet"]:
        raise SystemExit("surface does not fit in one DMA_DATA packet")
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
