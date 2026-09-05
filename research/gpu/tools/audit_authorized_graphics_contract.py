#!/usr/bin/env python3
"""Compare Stage E with authorized graphics headers without emitting private values."""
from __future__ import annotations

import argparse
import json
import re
import struct
from collections import Counter
from pathlib import Path


# Public PAL register names. AGC stores context-register offsets relative to
# the 0xA000 context base; no proprietary register value is read or emitted.
PUBLIC_CX_NAMES = {
    0x08F: "CB_SHADER_MASK",
    0x191: "SPI_PS_INPUT_CNTL_0",
    0x1B1: "SPI_VS_OUT_CONFIG",
    0x1B3: "SPI_PS_INPUT_ENA",
    0x1B4: "SPI_PS_INPUT_ADDR",
    0x1B6: "SPI_PS_IN_CONTROL",
    0x1B8: "SPI_BARYC_CNTL",
    0x1C3: "SPI_SHADER_POS_FORMAT",
    0x1C5: "SPI_SHADER_COL_FORMAT",
    0x203: "DB_SHADER_CONTROL",
    0x207: "PA_CL_VS_OUT_CNTL",
    0x2A1: "VGT_PRIMITIVEID_EN",
    0x310: "PA_SC_SHADER_CONTROL",
}

PUBLIC_SH_NAMES = {
    0x006: "SPI_SHADER_PGM_CHKSUM_PS",
    0x008: "SPI_SHADER_PGM_LO_PS",
    0x009: "SPI_SHADER_PGM_HI_PS",
    0x00A: "SPI_SHADER_PGM_RSRC1_PS",
    0x00B: "SPI_SHADER_PGM_RSRC2_PS",
    0x080: "SPI_SHADER_PGM_CHKSUM_GS",
    0x08A: "SPI_SHADER_PGM_RSRC1_GS",
    0x08B: "SPI_SHADER_PGM_RSRC2_GS",
    0x0C8: "SPI_SHADER_PGM_LO_ES",
    0x0C9: "SPI_SHADER_PGM_HI_ES",
}


def load_public_pal_cx_names() -> dict[int, str]:
    root = Path(__file__).resolve().parents[3]
    offsets = root / (
        "third_party/amd-pal/src/core/hw/gfxip/gfx9/chip/"
        "gfx9_plus_merged_offset.h")
    names: dict[int, str] = {}
    pattern = re.compile(
        r"constexpr unsigned int mm([A-Z0-9_]+)\s*=\s*0x(A[0-9A-Fa-f]{3});")
    for name, absolute in pattern.findall(offsets.read_text()):
        relative = int(absolute, 16) - 0xA000
        # Multiple ASIC aliases may exist. Keep a stable public spelling.
        names.setdefault(relative, name)
    return names


def u16(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<H", blob, offset)[0]


def u32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


def u64(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", blob, offset)[0]


def relative_offset(blob: bytes, field: int) -> int | None:
    raw = u64(blob, field)
    if raw == 0:
        return None
    signed = struct.unpack("<q", struct.pack("<Q", raw))[0]
    result = field + signed
    if result < 0 or result >= len(blob):
        raise ValueError(f"self-relative field {field:#x} leaves header")
    return result


def classify(blob: bytes) -> dict[str, object]:
    stage = blob[0x5A]
    user = relative_offset(blob, 0x08)
    specials = relative_offset(blob, 0x28)
    user_counts = (0, 0, 0, 0, 0)
    if user is not None:
        if user + 0x38 > len(blob):
            raise ValueError("user-data prefix leaves header")
        user_counts = (u16(blob, user + 0x2C),) + tuple(
            u16(blob, user + 0x2E + index * 2) for index in range(4))
    special_bytes = u16(blob, 0x58)
    if specials is None or specials + special_bytes > len(blob):
        raise ValueError("specials range leaves header")
    has_common_specials = special_bytes >= 0x30
    cx_count = blob[0x5B]
    cx = relative_offset(blob, 0x18)
    if cx_count and (cx is None or cx + cx_count * 8 > len(blob)):
        raise ValueError("CX range leaves header")
    cx_names = []
    for index in range(cx_count):
        offset = u32(blob, cx + index * 8)
        name = PUBLIC_CX_NAMES.get(offset)
        if name is None:
            raise ValueError("CX offset has no public PAL name")
        cx_names.append(name)
    sh_count = blob[0x5C]
    sh = relative_offset(blob, 0x20)
    if sh_count and (sh is None or sh + sh_count * 8 > len(blob)):
        raise ValueError("SH range leaves header")
    sh_names = []
    for index in range(sh_count):
        name = PUBLIC_SH_NAMES.get(u32(blob, sh + index * 8))
        if name is None:
            raise ValueError("SH offset has no public PAL name")
        sh_names.append(name)
    return {
        "stage": stage,
        "cx_count": cx_count,
        "cx_names": tuple(sorted(cx_names)),
        "sh_count": sh_count,
        "sh_names": tuple(sorted(sh_names)),
        "input_semantics": u32(blob, 0x50),
        "output_semantics": u16(blob, 0x56),
        "has_resources": any(user_counts),
        "resource_class_count": sum(1 for count in user_counts if count),
        "special_bytes": special_bytes,
        "common_specials_shape": has_common_specials,
        "dispatch_modifier_nonzero": has_common_specials and u32(blob, specials + 0x10) != 0,
        "user_data_range_nonempty": has_common_specials and
            u16(blob, specials + 0x14) != u16(blob, specials + 0x16),
        "draw_modifier_nonzero": has_common_specials and u64(blob, specials + 0x18) != 0,
    }


def histogram(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    return {str(k): v for k, v in sorted(Counter(row[key] for row in rows).items(),
                                          key=lambda item: str(item[0]))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path,
                        default=Path("research/gpu/captures/agc-authorized-shader-pairs.json"))
    parser.add_argument("--shaders", type=Path,
                        default=Path("research/gpu/shaders/san-andreas-authorized"))
    parser.add_argument("--output", type=Path,
                        default=Path("research/gpu/captures/agc-authorized-graphics-contract.json"))
    args = parser.parse_args()
    PUBLIC_CX_NAMES.update(load_public_pal_cx_names())
    manifest = json.loads(args.manifest.read_text())
    rows = []
    for entry in manifest["entries"]:
        if entry["type_raw"] not in (1, 2):
            continue
        rows.append(classify((args.shaders / entry["header_file"]).read_bytes()))
    if Counter(row["stage"] for row in rows) != Counter({1: 15, 2: 1}):
        raise SystemExit("authorized graphics inventory changed")
    keys = ("cx_count", "sh_count", "input_semantics", "output_semantics",
            "has_resources", "resource_class_count", "special_bytes",
            "common_specials_shape", "dispatch_modifier_nonzero",
            "user_data_range_nonempty", "draw_modifier_nonzero")
    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "authorized_graphics_headers": len(rows),
        "stage_counts": histogram(rows, "stage"),
        "aggregate_histograms": {key: histogram(rows, key) for key in keys},
        "aggregate_cx_name_sets_by_stage": {
            str(stage): histogram([row for row in rows if row["stage"] == stage],
                                  "cx_names")
            for stage in sorted({row["stage"] for row in rows})
        },
        "aggregate_sh_name_sets_by_stage": {
            str(stage): histogram([row for row in rows if row["stage"] == stage],
                                  "sh_names")
            for stage in sorted({row["stage"] for row in rows})
        },
        "stage_e_own_contract": {
            "cx_count": 0,
            "sh_count": 6,
            "input_semantics": 0,
            "output_semantics": 0,
            "has_resources": False,
            "resource_class_count": 0,
            "special_bytes": 48,
            "common_specials_shape": True,
            "dispatch_modifier_nonzero": False,
            "user_data_range_nonempty": False,
            "draw_modifier_nonzero": False,
        },
        "raw_bytes_emitted": False,
        "register_values_emitted": False,
        "per_shader_records_emitted": False,
        "console_contacted": False,
        "submitted_or_executed": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
