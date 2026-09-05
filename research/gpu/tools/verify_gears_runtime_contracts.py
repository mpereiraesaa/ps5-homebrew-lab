#!/usr/bin/env python3
"""Verify the public, offline runtime contracts needed by Cube/Gears."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AMDLLPC = ROOT / "third_party/amd-llpc/build-gfx1030/llpc/amdllpc"
OBJDUMP = ROOT / "third_party/amd-llpc/build-gfx1030/llvm/bin/llvm-objdump"
NID = ROOT / "third_party/ps5-native-app-boilerplate/.deps/native/ps5-payload-sdk/bin/prospero-nid"
CUBE = ROOT / "research/gpu/experiments/gears-contracts/cube_vertex_input.pipe"
GEARS = ROOT / "research/gpu/experiments/gears-contracts/gears_lit.pipe"
PAL_DEVICE = ROOT / "third_party/amd-pal/src/core/hw/gfxip/gfx9/gfx9Device.cpp"
PAL_SRD = ROOT / "third_party/amd-pal/src/core/hw/gfxip/gfx9/chip/gfx10_sq_ko_reg.h"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"gears runtime contract failed: {message}")


def nid(name: str) -> str:
    return subprocess.check_output([str(NID), name], text=True).strip()


def make_untyped_vertex_srd(gpu_address: int, byte_range: int,
                            stride: int) -> tuple[int, int, int, int]:
    """Mirror the public PAL GFX10 untyped-buffer SRD construction."""
    require(0 <= gpu_address < (1 << 48), "GPU address exceeds 48-bit SRD field")
    require(1 < stride < (1 << 14), "structured vertex stride is invalid")
    require(byte_range % stride == 0, "vertex byte range is not stride-aligned")
    selectors_xyzw = 4 | (5 << 3) | (6 << 6) | (7 << 9)
    word3 = selectors_xyzw | (0x14 << 12) | (1 << 24) | (1 << 28)
    return (
        gpu_address & 0xFFFFFFFF,
        ((gpu_address >> 32) & 0xFFFF) | (stride << 16),
        byte_range // stride,
        word3,
    )


def main() -> int:
    for path in (AMDLLPC, OBJDUMP, NID, CUBE, GEARS, PAL_DEVICE, PAL_SRD):
        require(path.is_file(), f"missing input: {path}")

    pal_device = PAL_DEVICE.read_text()
    pal_srd = PAL_SRD.read_text()
    require("Device::CreateUntypedBufferViewSrds" in pal_device,
            "public PAL untyped SRD constructor missing")
    require("SqBufRsrcTWord1StrideShift" in pal_srd and
            "uint64_t base_address" in pal_srd and
            "uint64_t stride" in pal_srd,
            "public GFX10 SRD layout missing")

    # Stable sentinel: address 0x123456789000, 24-byte vertices, 36 vertices.
    srd = make_untyped_vertex_srd(0x123456789000, 24 * 36, 24)
    require(srd == (0x56789000, 0x00181234, 36, 0x11014FAC),
            f"unexpected public-PAL SRD encoding: {srd!r}")

    with tempfile.TemporaryDirectory(prefix="ps5-agc-gears-runtime-") as directory:
        elf = Path(directory) / "cube.elf"
        subprocess.run([str(AMDLLPC), "-gfxip=10.1.3", f"-o={elf}", str(CUBE)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        cube_isa = subprocess.check_output(
            [str(OBJDUMP), "-d", "--mcpu=gfx1013", str(elf)], text=True)
        gears_elf = Path(directory) / "gears.elf"
        subprocess.run([str(AMDLLPC), "-gfxip=10.1.3", f"-o={gears_elf}", str(GEARS)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        gears_isa = subprocess.check_output(
            [str(OBJDUMP), "-d", "--mcpu=gfx1013", str(gears_elf)], text=True)

    # The two GLSL attributes share binding zero. The compiler loads one 16-byte
    # SRD and combines position+normal into typed fetches at offsets 0 and 16.
    require(len(re.findall(r"s_load_dwordx4 .*s\[0:1\]", cube_isa)) == 1,
            "Cube no longer loads exactly one vertex-buffer SRD")
    require("BUF_FMT_32_32_32_32_FLOAT" in cube_isa and
            "BUF_FMT_32_32_FLOAT" in cube_isa and "offset:16" in cube_isa,
            "Cube position/normal fetch shape changed")
    require(len(re.findall(r"s_load_dwordx4 .*null", gears_isa)) == 1,
            "Gears no longer loads exactly one vertex-buffer SRD")
    require("BUF_FMT_32_32_32_32_FLOAT" in gears_isa and
            "BUF_FMT_32_32_FLOAT" in gears_isa and "offset:16" in gears_isa,
            "Gears position/normal fetch shape changed")

    expected_nids = {
        "sceAgcCbSetShRegisterRangeDirect": "n2fD4A+pb+g",
        "sceAgcDcbDrawIndex": "q88lQ+GP5Yk",
        "sceAgcDcbSetIndexBuffer": "l4fM9K-Lyks",
        "sceAgcDcbSetIndexCount": "8N2tmT3jmC8",
        "sceAgcDcbDrawIndexOffset": "B+aG9DUnTKA",
        "sceAgcSuspendPoint": "h9z6+0hEydk",
        "sceVideoOutGetFlipStatus": "SbU3dwp80lQ",
        "sceVideoOutWaitVblank": "j6RaAUlaLv0",
    }
    for name, expected in expected_nids.items():
        require(nid(name) == expected, f"NID drift for {name}")

    print("gears runtime contract passed: Cube and lit Gears each use one GFX10 "
          "vertex SRD; public optional draw/pacing NIDs; gfx1013 ISA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
