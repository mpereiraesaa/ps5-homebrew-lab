#!/usr/bin/env python3
"""Build the independently authored Stage E pipeline for PS5-class gfx1013."""
from __future__ import annotations

import re
import subprocess
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LLPC_BUILD = ROOT / "third_party/amd-llpc/build-gfx1030"  # Historical cache name.
AMDLLPC = LLPC_BUILD / "llpc/amdllpc"
OBJCOPY = Path("/usr/bin/llvm-objcopy")
PIPE = ROOT / "research/gpu/shaders/stage-e/fullscreen_triangle.pipe"
OUTPUT = ROOT / "research/gpu/build/stage-e-shaders/fullscreen_triangle.pal.elf"
TEXT = OUTPUT.with_suffix(".text.bin")
GS = OUTPUT.parent / "fullscreen_triangle.bin"
PS = OUTPUT.parent / "solid_green.bin"
READELF = LLPC_BUILD / "llvm/bin/llvm-readelf"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipe", type=Path, default=PIPE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--gs", type=Path, default=GS)
    parser.add_argument("--ps", type=Path, default=PS)
    args = parser.parse_args()
    if not AMDLLPC.is_file():
        raise SystemExit(f"missing amdllpc: {AMDLLPC}")
    def project_path(path: Path) -> Path:
        return path if path.is_absolute() else ROOT / path

    pipe = project_path(args.pipe)
    output = project_path(args.output)
    gs = project_path(args.gs)
    ps = project_path(args.ps)
    text_path = output.with_suffix(".text.bin")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(AMDLLPC), "-gfxip=10.1.3", f"-o={output}", str(pipe)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [str(OBJCOPY), f"--dump-section=.text={text_path}", str(output)],
        cwd=ROOT,
        check=True,
    )
    text = text_path.read_bytes()
    symbols = subprocess.run(
        [str(READELF), "--symbols", str(output)], check=True, text=True,
        capture_output=True).stdout

    def symbol_extent(name: str) -> tuple[int, int]:
        match = re.search(
            rf"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC.*\s{name}$",
            symbols, re.M)
        if match is None:
            raise SystemExit(f"missing PAL shader symbol: {name}")
        return int(match.group(1), 16), int(match.group(2))

    gs_offset, gs_size = symbol_extent("_amdgpu_gs_main")
    ps_offset, ps_size = symbol_extent("_amdgpu_ps_main")
    if (gs_offset + gs_size > len(text) or
            ps_offset + ps_size > len(text) or not gs_size or not ps_size):
        raise SystemExit("PAL shader symbol extent exceeds .text")
    gs.parent.mkdir(parents=True, exist_ok=True)
    ps.parent.mkdir(parents=True, exist_ok=True)
    gs.write_bytes(text[gs_offset:gs_offset + gs_size])
    ps.write_bytes(text[ps_offset:ps_offset + ps_size])
    print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
