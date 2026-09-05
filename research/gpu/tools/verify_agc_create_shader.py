#!/usr/bin/env python3
"""Pin the firmware-12.02 sceAgcCreateShader wrapper and guest-visible ABI."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


FILE_BIAS = 0x4000
START = 0xEF70
END = 0xF2E8
RELOCATE_START = 0xF5B0
RELOCATE_END = 0xF684
STAGE_TABLE = 0x23DCC


def verify_dynsym(module: bytes) -> None:
    phoff = struct.unpack_from("<Q", module, 0x20)[0]
    phentsize = struct.unpack_from("<H", module, 0x36)[0]
    phnum = struct.unpack_from("<H", module, 0x38)[0]
    loads = []
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
        for start, end, offset in loads:
            if start <= va < end:
                return offset + va - start
        raise SystemExit(f"unmapped dynamic VA {va:#x}")

    tags = {}
    for offset in range(dynamic[0], dynamic[0] + dynamic[1], 16):
        tag, value = struct.unpack_from("<QQ", module, offset)
        if tag == 0:
            break
        tags[tag] = value
    symbol_count = struct.unpack_from("<II", module, file_offset(tags[4]))[1]
    symbol_table = file_offset(tags[6])
    string_table = file_offset(tags[5])
    matches = []
    for index in range(symbol_count):
        entry = symbol_table + index * tags.get(11, 24)
        name_offset, info, _, shndx, value, size = struct.unpack_from(
            "<IBBHQQ", module, entry
        )
        start = string_table + name_offset
        end = module.index(b"\0", start)
        name = module[start:end].decode("ascii", "replace")
        if name.split("#", 1)[0] == "f3dg2CSgRKY":
            matches.append((info & 0xF, shndx, value, size))
    if matches != [(2, 3, START, END - START)]:
        raise SystemExit(f"CreateShader dynsym mismatch: {matches}")


def expect(blob: bytes, va: int, expected: bytes, label: str) -> None:
    actual = blob[FILE_BIAS + va:FILE_BIAS + va + len(expected)]
    if actual != expected:
        raise SystemExit(f"{label} changed at {va:#x}: {actual.hex()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--system", type=Path,
        default=Path("research/gpu/dumps/system-libSceAgc.sprx"),
    )
    parser.add_argument(
        "--runtime", type=Path,
        default=Path("research/gpu/dumps/game-libSceAgc.sprx.bin"),
    )
    parser.add_argument(
        "--analysis", type=Path,
        default=Path("research/gpu/ghidra/game-libSceAgc.analysis.elf"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    system = args.system.read_bytes()
    runtime = args.runtime.read_bytes()
    analysis = args.analysis.read_bytes()
    verify_dynsym(system)
    function = system[FILE_BIAS + START:FILE_BIAS + END]
    if function != runtime[START:END]:
        raise SystemExit("runtime sceAgcCreateShader differs from system module")
    if function != analysis[FILE_BIAS + START:FILE_BIAS + END]:
        raise SystemExit("Ghidra analysis ELF sceAgcCreateShader differs")

    pins = {
        "file_header_1234": (0xEF70, "813e31323334"),
        "version_0x18": (0xEF7D, "837e0418"),
        "unbound_code_required": (0xEF88, "48837e1000"),
        "shader_size_read": (0xF08D, "8b4644"),
        "footer_marker_barefoot": (0xF090, "49b862617265666f6f74"),
        "relocate_header_call": (0xF14E, "e85d040000"),
        "bind_code_pointer": (0xF153, "49895f10"),
        "shader_type_read": (0xF15E, "410fb6475a"),
        "sh_register_count_read": (0xF17D, "0fb6795c"),
        "sh_register_array_read": (0xF18F, "488b7120"),
        "write_destination": (0xF2C6, "48890a"),
        "return_bad_magic": (0xEF76, "b803006c8a"),
        "return_bad_version": (0xEF81, "b804006c8a"),
        "return_already_bound": (0xEF8D, "b81f006c8a"),
        "return_runtime_unready": (0xEFAA, "b82f006c8a"),
        "return_target_policy": (0xEFE9, "b83d006c8a"),
        "return_target_helper": (0xF080, "b842006c8a"),
        "return_missing_stage_register": (0xF181, "b805006c8a"),
        "success_zero": (0xF2C9, "31c0"),
    }
    for label, (offset, encoded) in pins.items():
        expect(system, offset, bytes.fromhex(encoded), label)

    stage_raw = system[FILE_BIAS + STAGE_TABLE:FILE_BIAS + STAGE_TABLE + 32]
    stage_offsets = [int.from_bytes(stage_raw[i:i + 4], "little", signed=True)
                     for i in range(0, 32, 4)]
    stage_destinations = [STAGE_TABLE + offset for offset in stage_offsets]
    expected_destinations = [0xF17D, 0xF21C, 0xF1AE, 0xF24F,
                             0xF2C6, 0xF2C6, 0xF27B, 0xF1E5]
    if stage_destinations != expected_destinations:
        raise SystemExit(f"stage dispatch changed: {stage_destinations}")

    relocation = system[FILE_BIAS + RELOCATE_START:FILE_BIAS + RELOCATE_END]
    if relocation != runtime[RELOCATE_START:RELOCATE_END]:
        raise SystemExit("runtime relocation helper differs from system module")

    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "symbol": {
            "nid": "f3dg2CSgRKY",
            "name": "sceAgcCreateShader",
            "offset": hex(START),
            "size": END - START,
            "sha256": hashlib.sha256(function).hexdigest(),
            "system_runtime_equal": True,
            "dynsym_export_verified": True,
            "ghidra_analysis_equal": True,
        },
        "abi": {
            "rdi": "AgcShader **destination",
            "rsi": "mutable AgcShader header",
            "rdx": "256-byte-aligned shader code",
            "success_effect": "bind header+0x10 to code and write header to *destination",
            "static_proven": True,
            "homebrew_call_proven": False,
        },
        "header_contract": {
            "file_header_offset": "0x00",
            "file_header_value": "0x34333231 ('1234')",
            "version_offset": "0x04",
            "version_value": "0x18",
            "code_offset": "0x10",
            "sh_registers_offset": "0x20",
            "shader_size_offset": "0x44",
            "target_offset": "0x4c",
            "type_offset": "0x5a",
            "num_sh_registers_offset": "0x5c",
            "header_is_mutated_in_place": True,
            "code_must_be_unbound_on_entry": True,
            "minimum_prefix_bytes": 96,
            "self_relative_pointer_offsets": ["0x08", "0x18", "0x20", "0x28", "0x30", "0x38"],
        },
        "dispatch": {
            "accepted_stage_range": [0, 7],
            "destinations": [hex(value) for value in stage_destinations],
            "stages_without_register_search": [4, 5],
            "other_stages_require_matching_sh_register": True,
        },
        "return_codes": {
            "success": "0x00000000",
            "bad_magic": "0x8a6c0003",
            "bad_version": "0x8a6c0004",
            "missing_stage_register": "0x8a6c0005",
            "already_bound": "0x8a6c001f",
            "runtime_unready": "0x8a6c002f",
            "target_policy": "0x8a6c003d",
            "target_helper": "0x8a6c0042",
        },
        "relocation_helper": {
            "offset": hex(RELOCATE_START),
            "size": RELOCATE_END - RELOCATE_START,
            "sha256": hashlib.sha256(relocation).hexdigest(),
            "system_runtime_equal": True,
        },
        "caller_requirements": {
            "destination_non_null": "required by planner; export dereferences on success",
            "header_non_null": "required by planner; export dereferences immediately",
            "code_non_null": "required by planner; export footer probe and binding require it",
            "code_alignment": 256,
            "alignment_checked_inside_export": False,
            "all_ranges_prevalidated": True,
        },
        "lifecycle": {
            "allocation_performed_by_export": False,
            "destination_aliases_mutated_header": True,
            "caller_owns_header_and_code": True,
            "destroy_shader_export_identified": False,
            "release_rule": "only after downstream references are zero and GPU/pipeline use is quiescent",
            "missing_stage_register_failure_occurs_after_mutation": True,
            "post_mutation_failure_action": "discard mutable copy; never retry it",
        },
        "implications": {
            "raw_shader_text_alone_is_sufficient": False,
            "matching_shader_header_required": True,
            "header_and_code_pair_can_be_registered_by_public_agc_api": True,
            "command_buffer_pipeline_state_still_required": True,
            "shader_not_required_for_dma_clear_stage": True,
        },
        "pins": {
            label: {"offset": hex(offset), "bytes": encoded}
            for label, (offset, encoded) in pins.items()
        },
        "console_contacted": False,
        "future_probe_authorized": False,
        "uncertainties": [
            "stage names and a compatible graphics pair remain unselected",
            "nested user-data payload semantics remain opaque although their ranges are bounded",
            "the optional firmware shader-cache path must be excluded or modeled for a live probe",
            "successful construction does not prove pipeline compatibility or GPU execution",
        ],
        "future_probe_conditions": [
            "select one legally usable pair without publishing its bytes",
            "prove its stage role and any graphics partner compatibility",
            "use a fresh mutable header copy and retained 256-byte-aligned code storage",
            "exclude or model the optional shader-cache path",
            "prevalidate every header, nested and code range with the host planner",
            "define rollback, partial-mutation discard and indeterminate retention paths",
            "obtain separate explicit authorization before any console call",
        ],
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
