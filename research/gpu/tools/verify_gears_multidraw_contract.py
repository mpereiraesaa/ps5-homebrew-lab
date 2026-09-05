#!/usr/bin/env python3
"""Gate the direct-user-data layout and bounded three-gear command budget."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LLPC = ROOT / "third_party/amd-llpc/build-gfx1030/llpc/amdllpc"
READELF = ROOT / "third_party/amd-llpc/build-gfx1030/llvm/bin/llvm-readelf"
FIXTURE = ROOT / "research/gpu/experiments/gears-contracts/gears_lit.pipe"
OFFSETS = ROOT / "third_party/amd-pal/src/core/hw/gfxip/gfx9/chip/gfx9_plus_merged_offset.h"
ENUMS = ROOT / "third_party/amd-pal/src/core/hw/gfxip/gfx9/chip/gfx9_plus_merged_enum.h"
MODULE = ROOT / "research/gpu/dumps/system-libSceAgc.sprx"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit(f"gears multidraw contract failed: {message}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ps5-gears-multidraw-") as directory:
        elf = Path(directory) / "gears.elf"
        subprocess.run([str(LLPC), "-gfxip=10.1.3", f"-o={elf}", str(FIXTURE)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        notes = subprocess.check_output([str(READELF), "--notes", str(elf)], text=True)

    gs = re.search(r"^      \.gs:\n(?P<body>.*?)(?=^      \.ps:)", notes, re.M | re.S)
    require(gs is not None, "missing GS metadata")
    values = [int(item) for item in re.findall(r"^          - (\d+)$", gs.group("body"), re.M)]
    require(values[1:25] == list(range(24)), "24 direct parameters no longer contiguous")
    require(values[25] == 0x1000000F, "vertex-buffer-table mapping changed")

    offsets = OFFSETS.read_text()
    enums = ENUMS.read_text()
    gs0 = int(re.search(r"mmSPI_SHADER_USER_DATA_GS_0\s*=\s*0x([0-9A-Fa-f]+)", offsets).group(1), 16)
    persistent = int(re.search(r"PERSISTENT_SPACE_START\s*=\s*0x([0-9A-Fa-f]+)", enums).group(1), 16)
    compact_gs0 = gs0 - persistent
    require(compact_gs0 == 0x8C, "public compact GS user-data base changed")

    # Firmware builder: SysV (writer, offset, values, count), count+2 DWORDs,
    # SET_SH_REG header, compact offset, and inline memcpy payload.
    data = MODULE.read_bytes()
    code = data[0x28D0 + 0x4000:0x28D0 + 0x4000 + 237]
    for pattern, label in (
        (bytes.fromhex("89 cb 83 c3 02"), "count+2 reservation"),
        (bytes.fromhex("49 8d 04 9e"), "inline packet cursor advance"),
        (bytes.fromhex("0f b7 c6"), "compact 16-bit SH offset"),
        (bytes.fromhex("48 83 c7 08"), "payload starts after two DWORDs"),
        (bytes.fromhex("e8 b9 43 01 00"), "inline value copy"),
    ):
        require(pattern in code, f"firmware {label} changed")

    # Slot zero is the compiler internal-table pointer. Slots 1..24 hold MVP,
    # quaternion and material; slot 25 holds the 32-bit VB-table pointer.
    range_offset = compact_gs0 + 1
    range_values = 25
    range_dwords = range_values + 2
    # FW 12.02 DrawIndexAuto at libSceAgc+0x5240 advances the writer by
    # 0x0c bytes and emits header/count/modifier: exactly three DWORDs.
    draw_code = data[0x5240 + 0x4000:0x5240 + 0x4000 + 195]
    require(bytes.fromhex("48 8d 41 0c") in draw_code,
            "DrawIndexAuto 12-byte cursor advance changed")
    require(bytes.fromhex("c7 01 00 2d 01 c0") in draw_code,
            "DrawIndexAuto packet header changed")
    draw_dwords = 3
    three_draws = 3 * (range_dwords + draw_dwords)
    require((range_offset, range_values, three_draws) == (0x8D, 25, 90),
            "multidraw plan changed")
    require(three_draws <= 128, "three dynamic draws exceed bounded budget")

    print("gears multidraw contract passed: SH offset 0x8d, 25 inline values "
          "(MVP/quaternion/material/VB pointer), 27 DWORD update + 3 DWORD draw, "
          "90 DWORDs for three gears; no mutable indirect snapshot hazard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
