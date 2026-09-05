#!/usr/bin/env python3
"""Gate the public-evidence pre-draw D32 clear candidate, offline only."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAL_H = ROOT / "third_party/amd-pal/src/core/hw/gfxip/gfx9/gfx9CmdUtil.h"
PAL_CPP = ROOT / "third_party/amd-pal/src/core/hw/gfxip/gfx9/gfx9CmdUtil.cpp"
RADV = ROOT / "third_party/mesa-gfx1013/src/amd/vulkan/radv_cp_dma.c"
SOLID = ROOT / "research/gpu/captures/agc-solid-fill-plan-4k.json"
STAGE_D = ROOT / "research/gpu/captures/agc-stage-d-runtime.json"


def need(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, re.MULTILINE | re.DOTALL) is None:
        raise SystemExit(f"pre-draw clear contract failed: {label}")


def main() -> int:
    pal_h = PAL_H.read_text()
    pal_cpp = PAL_CPP.read_text()
    radv = RADV.read_text()
    solid = json.loads(SOLID.read_text())
    stage_d = json.loads(STAGE_D.read_text())

    need(pal_h, r'"sync" flag should be set in almost all cases.*?if true.*?is halted until this packet is finished',
         "PAL sync semantics changed")
    need(pal_h, r"disWc.*disable write-confirm", "PAL write-confirm semantics changed")
    need(pal_cpp, r"numBytes must be less than 64MB", "PAL DMA byte limit changed")
    need(pal_cpp, r"ordinal2\.bitfields\.cp_sync\s*=\s*\(dmaDataInfo\.sync \? 1 : 0\)",
         "PAL cp_sync encoding changed")
    need(radv, r"3D engine to wait until CP DMA is done.*?last CP DMA packet",
         "RADV CP_DMA_SYNC contract changed")
    need(radv, r"DMA operations via L2 are coherent and faster", "RADV L2 coherency evidence changed")

    packet = [int(word, 16) for word in solid["dma_data"]["packet_dwords"]]
    if len(packet) != 7 or packet[0] != 0xC0055000:
        raise SystemExit("pre-draw clear contract failed: DMA packet shape drift")
    if not solid["dma_data"]["cp_sync"] or solid["dma_data"]["raw_wait"]:
        raise SystemExit("pre-draw clear contract failed: final DMA sync policy drift")
    if not solid["dma_data"]["write_confirm_enabled"]:
        raise SystemExit("pre-draw clear contract failed: write-confirm disabled")
    if not stage_d["fill"]["target_matches"] or not stage_d["gpu_fence_zero"]:
        raise SystemExit("pre-draw clear contract failed: prior hardware DMA evidence drift")

    depth_bytes = 0x870000
    if depth_bytes >= (1 << 26) or depth_bytes % 4:
        raise SystemExit("pre-draw clear contract failed: D32 plane does not fit one DMA")

    print("pre-draw clear contract passed: one immediate 0x3f800000 DMA_DATA, "
          "0x870000 bytes via L2, write-confirm enabled and cp_sync set; "
          "public evidence makes an extra pre-draw ACQUIRE unnecessary for a "
          "fresh target, but depth consumption remains a hardware gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
