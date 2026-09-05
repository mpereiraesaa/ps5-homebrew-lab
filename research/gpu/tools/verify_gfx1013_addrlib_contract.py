#!/usr/bin/env python3
"""Verify the public Mesa/AddrLib boundary relevant to PS5 depth layouts.

This gate deliberately does not guess a console GB_ADDR_CONFIG value. It
proves which public path GFX1013 takes and that a real topology register is a
mandatory input before a depth allocation can be computed.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MESA = ROOT / "third_party/mesa-gfx1013"
ASIC = MESA / "src/amd/addrlib/src/amdgpu_asic_addr.h"
GFX10 = MESA / "src/amd/addrlib/src/gfx10/gfx10addrlib.cpp"
GB = MESA / "src/amd/addrlib/src/chip/gfx10/gfx10_gb_reg.h"
GPU_INFO = MESA / "src/amd/common/ac_gpu_info.c"
SURFACE = MESA / "src/amd/common/ac_surface.c"
ADDR_TYPES = MESA / "src/amd/addrlib/inc/addrtypes.h"
ADDRLIB2 = MESA / "src/amd/addrlib/src/core/addrlib2.cpp"


def require(text: str, pattern: str, label: str) -> re.Match[str]:
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise SystemExit(f"gfx1013 AddrLib gate failed: {label}")
    return match


def main() -> int:
    asic = ASIC.read_text()
    gfx10 = GFX10.read_text()
    gb = GB.read_text()
    gpu_info = GPU_INFO.read_text()
    surface = SURFACE.read_text()
    addr_types = ADDR_TYPES.read_text()
    addrlib2 = ADDRLIB2.read_text()

    require(asic, r"AMDGPU_GFX1013_RANGE\s+0x82,\s*0x86",
            "GFX1013 external-revision range is not 0x82..0x85")
    require(gpu_info, r"case\s+FAMILY_NV:.*?identify_chip\(GFX1013\);",
            "GFX1013 is not identified inside FAMILY_NV")
    require(gpu_info, r"GFX1013 is GFX10 plus ray tracing instructions",
            "public GFX1013 generation classification changed")

    # ac_surface passes the actual kernel-reported topology value into
    # AddrCreate. A chip name/revision is not a substitute for this input.
    require(surface,
            r"regValue\.gbAddrConfig\s*=\s*info->gb_addr_config;.*?"
            r"addrCreateInput\.chipFamily\s*=\s*info->family_id;.*?"
            r"addrCreateInput\.chipRevision\s*=\s*info->chip_external_rev;",
            "Mesa no longer passes topology and chip identity separately")
    require(gb,
            r"NUM_PIPES\s*:\s*3;.*?PIPE_INTERLEAVE_SIZE\s*:\s*3;.*?"
            r"MAX_COMPRESSED_FRAGS\s*:\s*2;.*?NUM_PKRS\s*:\s*3;",
            "GFX10 GB_ADDR_CONFIG field contract changed")
    for field in ("NUM_PIPES", "PIPE_INTERLEAVE_SIZE", "MAX_COMPRESSED_FRAGS"):
        require(gfx10, rf"switch\s*\(gbAddrConfig\.bits\.{field}\)",
                f"AddrLib does not consume GB_ADDR_CONFIG.{field}")

    # GFX1013 is accepted by FAMILY_NV but matches none of the explicit Navi10
    # or RDNA2 ASIC branches here. In particular, the generic GFX10 path does
    # not enable RB+ and therefore has no variable-block depth mode.
    family_nv = require(gfx10, r"case\s+FAMILY_NV:(.*?)break;",
                        "missing FAMILY_NV conversion branch").group(1)
    if "GFX1013" in family_nv:
        raise SystemExit("gfx1013 AddrLib gate failed: GFX1013 gained an "
                         "explicit ASIC branch; review required")
    require(gfx10,
            r"if\s*\(m_settings\.supportRbPlus\).*?"
            r"m_blockVarSizeLog2\s*=\s*m_pipesLog2\s*\+\s*14;",
            "variable block size is no longer RB+-gated")
    require(gfx10,
            r"forbidVarBlockType\s*=\s*\(\(m_blockVarSizeLog2\s*==\s*0\)",
            "depth VAR_Z_X availability is no longer blockVarSize-gated")
    require(gfx10, r"pOut->swizzleMode\s*=\s*ADDR_SW_64KB_Z_X;",
            "64KB_Z_X fallback disappeared")

    # For a single-mip, single-sample, 2D D32 main plane the footprint is
    # topology-independent.  The pipe-dependent equation only permutes bytes
    # inside each 64 KiB block.  Reproduce the public generic formulas rather
    # than constructing AddrLib with a guessed GB_ADDR_CONFIG.
    require(addr_types, r"ADDR_SW_64KB_Z_X\s*=\s*24",
            "64KB_Z_X public swizzle value changed")
    require(addrlib2,
            r"log2NumEle\s*=\s*log2BlkSize\s*-\s*log2EleBytes\s*-\s*log2Samples;.*?"
            r"log2Width\s*=\s*\(log2NumEle\s*\+\s*\(widthPrecedent\s*\?\s*1\s*:\s*0\)\)\s*/\s*2;",
            "thin-block dimension formula changed")
    require(gfx10,
            r"pOut->pitch\s*=\s*PowTwoAlign\(pIn->width,\s*pOut->blockWidth\);.*?"
            r"pOut->height\s*=\s*PowTwoAlign\(pIn->height,\s*heightAlign\);.*?"
            r"pOut->baseAlign\s*=\s*blockSize;",
            "macro-tiled footprint formula changed")
    log2_elements = 16 - 2  # 64 KiB / 4-byte D32 / one sample
    block_width = 1 << ((log2_elements + 1) // 2)
    block_height = 1 << (log2_elements - ((log2_elements + 1) // 2))
    if (block_width, block_height) != (128, 128):
        raise SystemExit("gfx1013 AddrLib gate failed: unexpected D32 block")
    pitch = (1920 + block_width - 1) // block_width * block_width
    height = (1080 + block_height - 1) // block_height * block_height
    footprint = pitch * height * 4
    if (pitch, height, footprint) != (1920, 1152, 0x870000):
        raise SystemExit("gfx1013 AddrLib gate failed: D32 footprint drift")

    print("gfx1013 AddrLib gate passed: revs 0x82..0x85 use generic GFX10; "
          "depth falls back to 64KB_Z_X; 1920x1080 D32 main plane is "
          "128x128-blocked, 64KiB-aligned, 0x870000 bytes. Per-coordinate "
          "addressing and HTILE still require real topology")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
