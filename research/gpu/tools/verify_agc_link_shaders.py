#!/usr/bin/env python3
"""Pin the FW 12.02 sceAgcLinkShaders export without executing it."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


FILE_BIAS = 0x4000
START = 0x103F0
END = 0x1088C
PRIMITIVE_TABLE = 0x23F1C
EXPECTED_PRIMITIVE_MAP = [0, 1, 1, 2, 2, 2, 3, 2, 2, 1, 1, 2, 2, 2, 2, 2, 4, 1]


def dynamic_symbols(module: bytes) -> list[tuple[str, int, int, int, int]]:
    phoff = struct.unpack_from("<Q", module, 0x20)[0]
    phentsize = struct.unpack_from("<H", module, 0x36)[0]
    phnum = struct.unpack_from("<H", module, 0x38)[0]
    loads: list[tuple[int, int, int]] = []
    dynamic = None
    for index in range(phnum):
        entry = phoff + index * phentsize
        p_type, _, p_offset, p_vaddr, _, p_filesz, _, _ = struct.unpack_from(
            "<IIQQQQQQ", module, entry
        )
        if p_type == 1:
            loads.append((p_vaddr, p_vaddr + p_filesz, p_offset))
        elif p_type == 2:
            dynamic = (p_offset, p_filesz)
    if dynamic is None:
        raise SystemExit("system module lacks PT_DYNAMIC")

    def file_offset(va: int) -> int:
        for first, last, offset in loads:
            if first <= va < last:
                return offset + va - first
        raise SystemExit(f"unmapped dynamic VA {va:#x}")

    tags: dict[int, int] = {}
    for offset in range(dynamic[0], dynamic[0] + dynamic[1], 16):
        tag, value = struct.unpack_from("<QQ", module, offset)
        if tag == 0:
            break
        tags[tag] = value
    count = struct.unpack_from("<II", module, file_offset(tags[4]))[1]
    symtab = file_offset(tags[6])
    strtab = file_offset(tags[5])
    result = []
    for index in range(count):
        entry = symtab + index * tags.get(11, 24)
        name_offset, info, _, shndx, value, size = struct.unpack_from(
            "<IBBHQQ", module, entry
        )
        first = strtab + name_offset
        last = module.index(b"\0", first)
        result.append((module[first:last].decode("ascii", "replace").split("#", 1)[0],
                       info & 0xF, shndx, value, size))
    return result


def expect(blob: bytes, va: int, encoded: str, label: str) -> None:
    wanted = bytes.fromhex(encoded)
    actual = blob[FILE_BIAS + va:FILE_BIAS + va + len(wanted)]
    if actual != wanted:
        raise SystemExit(f"{label} changed at {va:#x}: {actual.hex()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", type=Path,
                        default=Path("research/gpu/dumps/system-libSceAgc.sprx"))
    parser.add_argument("--runtime", type=Path,
                        default=Path("research/gpu/dumps/game-libSceAgc.sprx.bin"))
    parser.add_argument("--analysis", type=Path,
                        default=Path("research/gpu/ghidra/game-libSceAgc.analysis.elf"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    system, runtime, analysis = (args.system.read_bytes(), args.runtime.read_bytes(),
                                 args.analysis.read_bytes())

    matches = [(kind, section, value, size) for name, kind, section, value, size
               in dynamic_symbols(system) if name == "MqAdbRMdNz4"]
    if matches != [(2, 3, START, END - START)]:
        raise SystemExit(f"LinkShaders dynsym mismatch: {matches}")
    function = system[FILE_BIAS + START:FILE_BIAS + END]
    if function != runtime[START:END]:
        raise SystemExit("runtime LinkShaders differs from system module")
    if function != analysis[FILE_BIAS + START:FILE_BIAS + END]:
        raise SystemExit("Ghidra analysis LinkShaders differs from system module")

    pins = {
        "rdx_is_optional_aux_shader": (0x103FA, "4989d2"),
        "cx_optional": (0x103FD, "4885ff0f84ff030000"),
        "cx_fixed_word_100": (0x10417, "48898700010000"),
        "cx_fixed_word_108": (0x10421, "48898708010000"),
        "pre_raster_specials_at_28": (0x10431, "488b5128"),
        "primitive_minus_one": (0x1044F, "458d59ff"),
        "primitive_range_1_18": (0x10458, "4183fb11"),
        "primitive_table_load": (0x10461, "488d1db43a01008b1493"),
        "cx_fixed_dword_10c": (0x10470, "89870c010000"),
        "pixel_input_count_50": (0x1047F, "418b4050"),
        "pre_output_count_56": (0x10491, "440fb74956"),
        "pixel_inputs_30": (0x104A0, "498b7030"),
        "pre_outputs_38": (0x104A4, "4c8b5138"),
        "semantic_low_byte_match": (0x104E0, "470fb624ba4130d47416"),
        "cx_semantic_qword_write": (0x1071B, "488914df"),
        "semantic_capacity_32": (0x1079B, "83f81f7739"),
        "aux_specials_or": (0x107DE, "498b42288b97040100000b500c"),
        "uc_optional": (0x10805, "4885f67475"),
        "uc_write_0": (0x1081B, "488906"),
        "uc_write_8": (0x10821, "48895608"),
        "uc_write_10": (0x1082F, "48895610"),
        "uc_write_14": (0x1083D, "895614"),
        "always_return_zero": (0x1087F, "31c0"),
    }
    for label, (offset, encoded) in pins.items():
        expect(system, offset, encoded, label)

    raw = system[FILE_BIAS + PRIMITIVE_TABLE:
                 FILE_BIAS + PRIMITIVE_TABLE + 4 * len(EXPECTED_PRIMITIVE_MAP)]
    primitive_map = list(struct.unpack("<18I", raw))
    if primitive_map != EXPECTED_PRIMITIVE_MAP:
        raise SystemExit(f"primitive map changed: {primitive_map}")

    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "symbol": {
            "name": "sceAgcLinkShaders", "nid": "MqAdbRMdNz4",
            "offset": hex(START), "size": END - START,
            "sha256": hashlib.sha256(function).hexdigest(),
            "dynsym_export_verified": True, "system_runtime_equal": True,
            "ghidra_analysis_equal": True,
        },
        "abi": {
            "rdi": "optional writable CX output (0x110 bytes when non-null)",
            "rsi": "optional writable UC output (0x18 bytes when non-null)",
            "rdx": "optional auxiliary/pre-raster shader, read-only",
            "rcx": "optional primary pre-raster shader, read-only",
            "r8": "optional pixel shader, read-only",
            "r9d": "primitive type (u32)",
            "return": "always zero on every static control-flow exit",
        },
        "outputs": {"cx_bytes": 0x110, "uc_bytes": 0x18,
                    "semantic_entries": 32, "semantic_entry_bytes": 8,
                    "allocation_performed": False,
                    "cx_layout": ["SPI_PS_INPUT_CNTL[32]", "VGT_SHADER_STAGES_EN",
                                  "VGT_GS_OUT_PRIM_TYPE"],
                    "uc_layout": ["GE_CNTL", "GE_USER_VGPR_EN", "VGT_PRIMITIVE_TYPE"],
                    "entry_layout": "{u32 register_offset, u32 register_value}"},
        "semantics": {
            "pixel_input_pointer_offset": "0x30", "pixel_input_count_offset": "0x50",
            "pre_raster_output_pointer_offset": "0x38",
            "pre_raster_output_count_offset": "0x56",
            "match_key": "low byte of each 32-bit semantic word",
            "pixel_input_capacity": 32,
        },
        "primitive": {"accepted_table_inputs": [1, 18],
                      "cx_vgt_gs_out_prim_type_out_of_range_fallback": 2,
                      "uc_vgt_primitive_type_uses_raw_input": True,
                      "mapping": primitive_map},
        "stages": {"type_field_read_by_export": False,
                   "primary_role": "producer/pre-raster specials and outputs",
                   "pixel_role": "consumer inputs",
                   "aux_role": "optional pre-raster specials override",
                   "selected_pair_types": {"pre_raster": 2, "pixel": 1}},
        "workspace": {"argument_present": False, "allocation_present": False},
        "alignment": {"implementation_checks": False,
                      "scalar_x86_access_allows_byte_addressing": True,
                      "documented_C_types_natural_alignment": 4,
                      "planner_policy": 8},
        "safety": {
            "internal_argument_validation": False,
            "compatibility_error_return_available": False,
            "planner_must_prevalidate_all_ranges_and_roles": True,
            "outputs_are_mutated_even_for_semantically_unmatched_inputs": True,
        },
        "pins": {label: {"offset": hex(offset), "bytes": encoded}
                 for label, (offset, encoded) in pins.items()},
        "console_contacted": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
