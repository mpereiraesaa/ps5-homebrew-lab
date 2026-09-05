#!/usr/bin/env python3
"""Cross-check the local AGC depth-pair IDs against public GFX10 registers."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OFFSETS = ROOT / "third_party/amd-pal/src/core/hw/gfxip/gfx9/chip/gfx9_plus_merged_offset.h"

# The authorized local descriptor contains these 16 IDs. Names below come only
# from public PAL's GFX10 register-offset table.
EXPECTED = {
    0x02: "DB_DEPTH_VIEW",
    0x05: "DB_HTILE_DATA_BASE",
    0x07: "DB_DEPTH_SIZE_XY",
    0x0A: "DB_STENCIL_CLEAR",
    0x0B: "DB_DEPTH_CLEAR",
    0x10: "DB_Z_INFO",
    0x11: "DB_STENCIL_INFO",
    0x12: "DB_Z_READ_BASE",
    0x13: "DB_STENCIL_READ_BASE",
    0x14: "DB_Z_WRITE_BASE",
    0x15: "DB_STENCIL_WRITE_BASE",
    0x1A: "DB_Z_READ_BASE_HI",
    0x1B: "DB_STENCIL_READ_BASE_HI",
    0x1C: "DB_Z_WRITE_BASE_HI",
    0x1D: "DB_STENCIL_WRITE_BASE_HI",
    0x1E: "DB_HTILE_DATA_BASE_HI",
}


def main() -> int:
    text = OFFSETS.read_text()
    for register_id, name in EXPECTED.items():
        match = re.search(rf"mm{name}\s*=\s*0x([0-9A-Fa-f]+);", text)
        if match is None:
            raise SystemExit(f"depth register gate failed: missing public {name}")
        absolute = int(match.group(1), 16)
        if absolute != 0xA000 + register_id:
            raise SystemExit(
                f"depth register gate failed: {name}=0x{absolute:x}, "
                f"expected context ID 0x{register_id:x}")
    print("depth register gate passed: all 16 AGC pair IDs map exactly to "
          "public GFX10 DB context registers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
