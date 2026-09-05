#!/usr/bin/env python3
"""Compile clean-room Plasma/Cube fixtures and verify public gfx1013 ABI facts."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AMDLLPC = ROOT / "third_party/amd-llpc/build-gfx1030/llpc/amdllpc"
READELF = ROOT / "third_party/amd-llpc/build-gfx1030/llvm/bin/llvm-readelf"
FIXTURES = ROOT / "research/gpu/experiments/gears-contracts"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"gears shader contract failed: {message}")


def compile_and_read(name: str, source: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="ps5-agc-gears-") as directory:
        elf = Path(directory) / f"{name}.pal.elf"
        subprocess.run(
            [str(AMDLLPC), "-gfxip=10.1.3", f"-o={elf}", str(source)],
            cwd=ROOT, check=True)
        header = subprocess.check_output(
            [str(READELF), "--file-header", str(elf)], text=True)
        require("Flags:                             0x42" in header,
                f"{name}: ELF is not gfx1013")
        relocations = subprocess.check_output(
            [str(READELF), "--relocations", str(elf)], text=True)
        require("There are no relocations" in relocations,
                f"{name}: unexpected relocation")
        return subprocess.check_output(
            [str(READELF), "--symbols", "--notes", str(elf)], text=True)


def stage_map(text: str, stage: str) -> tuple[list[int], int]:
    match = re.search(
        rf"^      \.{stage}:\n(?P<body>.*?)(?=^      \.[a-z]+:|^    \.)",
        text, re.M | re.S)
    require(match is not None, f"missing {stage} metadata")
    body = match.group("body")
    values_match = re.search(
        r"\.user_data_reg_map:\n(?P<values>(?:\s+- \d+\n)+)", body)
    count_match = re.search(r"\.user_sgprs:\s+(\d+)", body)
    require(values_match is not None and count_match is not None,
            f"missing {stage} user-data contract")
    values = [int(item) for item in re.findall(r"- (\d+)",
                                               values_match.group("values"))]
    return values, int(count_match.group(1))


def require_shader_symbols(text: str, name: str) -> None:
    for symbol in ("_amdgpu_gs_main", "_amdgpu_ps_main"):
        match = re.search(
            rf"^\s*\d+:\s+[0-9a-f]+\s+(\d+)\s+FUNC.*\s{symbol}$",
            text, re.M)
        require(match is not None and int(match.group(1)) > 0,
                f"{name}: missing non-empty {symbol}")


def main() -> int:
    require(AMDLLPC.is_file() and READELF.is_file(), "LLPC toolchain missing")
    plasma = compile_and_read("plasma", FIXTURES / "plasma_push_constant.pipe")
    cube = compile_and_read("cube", FIXTURES / "cube_vertex_input.pipe")
    gears = compile_and_read("gears", FIXTURES / "gears_lit.pipe")
    require_shader_symbols(plasma, "plasma")
    require_shader_symbols(cube, "cube")
    require_shader_symbols(gears, "gears")

    plasma_ps, plasma_ps_count = stage_map(plasma, "ps")
    require(plasma_ps_count == 5, "Plasma PS must use internal table + 4 constants")
    require(plasma_ps[:5] == [0x10000000, 0, 1, 2, 3],
            "Plasma push constants are not direct PS user data")

    cube_gs, cube_gs_count = stage_map(cube, "gs")
    require(cube_gs_count == 20, "Cube GS user-data count changed")
    require(cube_gs[1:17] == list(range(16)),
            "Cube matrix is not mapped as 16 direct user SGPRs")
    require(cube_gs[17] == 0x1000000F,
            "Cube vertex-input indirect pointer is absent")

    gears_gs, gears_gs_count = stage_map(gears, "gs")
    require(gears_gs_count == 28, "Gears GS user-data count changed")
    require(gears_gs[1:25] == list(range(24)),
            "Gears MVP/quaternion/material are not direct user data")
    require(gears_gs[25] == 0x1000000F,
            "Gears vertex-input indirect pointer is absent")

    print("gears shader contract passed: gfx1013 Plasma direct constants; "
          "Cube matrix; Gears MVP + quaternion + material + two vertex inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
