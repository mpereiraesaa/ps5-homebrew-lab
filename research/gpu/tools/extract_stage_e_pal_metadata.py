#!/usr/bin/env python3
"""Extract reproducible, non-proprietary facts from our own gfx1013 PAL ELF."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import argparse
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "third_party/amd-llpc/build-gfx1030"  # Historical cache name.
READELF = BUILD / "llvm/bin/llvm-readelf"
ELF = ROOT / "research/gpu/build/stage-e-shaders/fullscreen_triangle.pal.elf"
OUTPUT = ROOT / "research/gpu/captures/stage-e-gfx1013-pal-metadata.json"


class PalMetadataLoader(yaml.SafeLoader):
    """Safe YAML loader with LLVM's scalar spelling tag."""


PalMetadataLoader.add_constructor(
    "!str", lambda loader, node: loader.construct_scalar(node))


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", type=Path, default=ELF)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    elf = args.elf if args.elf.is_absolute() else ROOT / args.elf
    output = args.output if args.output.is_absolute() else ROOT / args.output
    raw = elf.read_bytes()
    header = run(str(READELF), "--file-header", str(elf))
    relocations = run(str(READELF), "--relocations", str(elf))
    symbols = run(str(READELF), "--symbols", str(elf))
    notes = run(str(READELF), "--notes", "--elf-output-style=LLVM", str(elf))
    match = re.search(r"AMDGPU Metadata: ---\n(.*?)\n\.\.\.", notes, re.S)
    if match is None:
        raise SystemExit("PAL metadata YAML was not decoded")
    metadata = yaml.load(match.group(1), Loader=PalMetadataLoader)
    pipeline = metadata["amdpal.pipelines"][0]
    stages = pipeline[".hardware_stages"]
    graphics = pipeline[".graphics_registers"]

    def symbol_size(name: str) -> int:
        match = re.search(rf"^\s*\d+:\s+[0-9a-f]+\s+(\d+)\s+FUNC.*\s{name}$",
                          symbols, re.M)
        if match is None:
            raise SystemExit(f"missing function symbol: {name}")
        return int(match.group(1))

    def stage(name: str) -> dict[str, object]:
        item = stages[name]
        return {
            "entry_point_symbol": item[".entry_point_symbol"],
            "sgpr_count": item[".sgpr_count"],
            "user_sgprs": item[".user_sgprs"],
            "vgpr_count": item[".vgpr_count"],
            "wavefront_size": item[".wavefront_size"],
            "wgp_mode": item.get(".wgp_mode", False),
            "scratch_enabled": item[".scratch_en"],
            "user_data_reg_map": item[".user_data_reg_map"],
        }

    result = {
        "schema": 1,
        "source": str(elf.relative_to(ROOT)),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "target": "gfx1013",
        "elf_machine_flags": "0x42",
        "amd_pal_osabi": "AMDGPU - PAL" in header,
        "no_relocations": "no relocations" in relocations.lower(),
        "symbols": {
            "pre_raster_gs": "_amdgpu_gs_main" in symbols,
            "ps": "_amdgpu_ps_main" in symbols,
        },
        "code_bytes": {
            "pre_raster_gs": symbol_size("_amdgpu_gs_main"),
            "ps": symbol_size("_amdgpu_ps_main"),
        },
        "pipeline_type": pipeline[".type"],
        "stages": {"pre_raster_gs": stage(".gs"), "ps": stage(".ps")},
        "exports": {
            "color_formats": graphics[".spi_shader_col_format"],
            "position_formats": graphics[".spi_shader_pos_format"],
            "color_write_masks": graphics[".cb_shader_mask"],
        },
        "graphics_register_metadata": graphics,
        "public_inputs_only": True,
        "console_contacted": False,
        "submit_performed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
