#!/usr/bin/env python3
"""Verify the attachment-derived branches in San Andreas' AGC control helper."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


EBOOT_BASE = 0x400000
AGC_BASE = 0x80058C000


def expect(blob: bytes, address: int, expected: bytes, label: str) -> None:
    offset = address - EBOOT_BASE
    actual = blob[offset : offset + len(expected)]
    if actual != expected:
        raise SystemExit(
            f"{label}: expected {expected.hex()} at {address:#x}, got {actual.hex()}"
        )


def expect_offset(blob: bytes, offset: int, expected: bytes, label: str) -> None:
    actual = blob[offset : offset + len(expected)]
    if actual != expected:
        raise SystemExit(
            f"{label}: expected {expected.hex()} at file+{offset:#x}, got {actual.hex()}"
        )


def resolve_thunk(blob: bytes, address: int) -> int:
    offset = address - EBOOT_BASE
    if blob[offset : offset + 2] != b"\xff\x25":
        raise SystemExit(f"{address:#x} is not a RIP-indirect thunk")
    displacement = struct.unpack_from("<i", blob, offset + 2)[0]
    got = address + 6 + displacement
    return struct.unpack_from("<Q", blob, got - EBOOT_BASE)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("eboot", type=Path)
    parser.add_argument("runtime_agc", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    eboot = args.eboot.read_bytes()
    agc = args.runtime_agc.read_bytes()

    # Mode 2 emits selector 0x10 and seeds the derived control mask with 0x7fc0.
    expect(eboot, 0x4DB842A,
           bytes.fromhex("83fb0174154c89f7be1000000031d2e88289000041bfc07f0000"),
           "mode-2 partial-flush prefix")
    # Bit 0x800 emits selector 0x2e.  Bit 0x2000 then chooses whether the
    # second selector 0x2c and the deeper label chain are needed.
    expect(eboot, 0x4DB8444,
           bytes.fromhex("41f7c500080000752341f7c5002000000f84a7020000"),
           "color/depth control split")
    expect(eboot, 0x4DB8470,
           bytes.fromhex("4c89f7be2e00000031d24c89bd70fbffffe83a890000"),
           "color event 0x2e")
    expect(eboot, 0x4DB8486,
           bytes.fromhex("41f7c500200000750fc7858cfbfffffffbffff41b72d"),
           "color-only mask and completion event")
    expect(eboot, 0x4DB849E,
           bytes.fromhex("c7858cfbffffffebffff41b714"),
           "color-plus-depth mask and completion event")
    expect(eboot, 0x4DB84AB,
           bytes.fromhex("4c89f7be2c00000031d2e806890000"),
           "depth event 0x2c")
    # The shared RELEASE_MEM call selects a 64-bit immediate payload of one.
    # Its address starts as zero and is patched to the private label later.
    expect(eboot, 0x4DB8552,
           bytes.fromhex(
               "410fb6f748898550fbffff4889dfba00000000b901000000"
               "41b80000000041b9000000006a006a006a016a006a016a01"
               "e899860000"),
           "private-label RELEASE_MEM call")
    expect_offset(agc, 0x284D,
                  bytes.fromhex(
                      "49c1e33dc701004906c0410fb6c041c1e60c410fb6d548c1e330"
                      "c1e01948c1e23841c1e4084109f48b75d04509e64409f04809c3"
                      "8b45384809da498d94130005000048895104488b55c825ffffff07"
                      "89710c448949104489791489511889411c48"),
                  "RELEASE_MEM field encoding and stores")
    expect_offset(agc, 0xD320,
                  bytes.fromhex(
                      "0fb64f01b80c006c8ac1e10881f900490000753648b90000000000"
                      "00000748234f0448ba000000000000000431c04839d174178b570c"
                      "89f148c1ee2083e1fc83e20309ca89570c897710c3"),
                  "RELEASE_MEM address patcher")
    # The shared label chain calls AGC+0x6e00 with ESI=0.  That builder's
    # mode-zero branch emits seven DWORD WAIT_REG_MEM (0x3c); its mode-one
    # WAIT_REG_MEM64 (0x93) branch is not selected by this path.
    expect(eboot, 0x4DB8592,
           bytes.fromhex(
               "4883ec0831f6b8ffffffff4889dfba0300000031c94531c0"
               "4531c96890010000506a01e826880000"),
           "mode-zero WAIT_REG_MEM call")
    expect_offset(agc, 0x6FA5,
                  bytes.fromhex("4c8b7b10488b4b188b73304183c407"),
                  "WAIT_REG_MEM mode-zero branch")
    expect_offset(agc, 0x706F,
                  bytes.fromhex(
                      "c70481003c05c04080e607400fb6f6418d743010448b4520"
                      "09f78b75c041c1e8044080e603400fb6f6c1e61909fe"),
                  "WAIT_REG_MEM header and control encoding")
    expect_offset(agc, 0x709D,
                  bytes.fromhex(
                      "4181f8ffff0000bfffff00008974810489548108488b5510"
                      "448974810c410f42f889548110488b551889548114897c8118"),
                  "WAIT_REG_MEM address/reference/mask/poll stores")
    # After patching the private label into DMA/WAIT/RELEASE, the helper issues
    # ACQUIRE_MEM over the same 32-byte label range. Preserve raw arguments;
    # semantic field names are not assumed from the calling convention alone.
    expect(eboot, 0x4DB86C5,
           bytes.fromhex(
               "41b920000000be01000000ba00000000b9009000004989d8"
               "4c89f76890010000e806870000"),
           "private-label ACQUIRE_MEM call")
    # This runtime image selects the generic (non-specialized) ACQUIRE_MEM
    # encoder path. The packet is address-dependent only through its 256-byte
    # base and one-or-two-unit covered size.
    expect_offset(agc, 0x45F9C, bytes.fromhex("00000000"),
                  "runtime ACQUIRE_MEM encoder mode flags")
    expect_offset(agc, 0x3841,
                  bytes.fromhex(
                      "89c889cb49bf00ffffffffff0000448b6510440fb6d62500c00000"
                      "81cb008000003d00400000410fb6c00f45d94c01c8b1304d29c7"
                      "c4e2f0f5c04805ff0000004c39f84c0f42f8488d"),
                  "ACQUIRE_MEM argument normalization and range rounding")
    expect_offset(agc, 0x39E7,
                  bytes.fromhex(
                      "f7c200000004743989d889d981ca0040000049befeffffffff000000"
                      "41b80001000083e0f483e1f7ffc0f6c3020f45c889cb81e3f7efff"
                      "fff7c1001000000f44d94189d531c0488b"),
                  "ACQUIRE_MEM generic-path selection")
    expect_offset(agc, 0x3AD7,
                  bytes.fromhex(
                      "4c89f24181e5c07f000641c1e21f4c89c649c1e82849c1e72081e3"
                      "ffff0700c701005806c048c1ea204509ea48c1ee084d09c70fb6d2"
                      "448951044489710889510c4889ca8971104c89791489591ceb06"),
                  "ACQUIRE_MEM generic packet stores")

    thunks = {
        "dma_data": (0x4DC0C10, 0x47D0),
        "release_mem": (0x4DC0C20, 0x2700),
        "event_write": (0x4DC0DC0, 0x5CE0),
        "wait_reg_mem_family": (0x4DC0DE0, 0x6E00),
        "acquire_mem": (0x4DC0DF0, 0x3830),
        "write_data": (0x4DC0F00, 0x49B0),
        "raw_packet_allocator": (0x4DC1C30, 0x28D0),
        "raw_payload_resolver": (0x4DC1C40, 0xD040),
        "raw_packet_header": (0x4DC1C90, 0x2640),
        "dma_patch_destination": (0x4DC1CA0, 0xD0C0),
        "wait_patch_address": (0x4DC1CB0, 0xD100),
        "release_patch_address": (0x4DC1CC0, 0xD320),
    }
    resolved = {}
    for name, (thunk, expected_offset) in thunks.items():
        target = resolve_thunk(eboot, thunk)
        if target != AGC_BASE + expected_offset:
            raise SystemExit(
                f"{name}: expected AGC+{expected_offset:#x}, got {target:#x}"
            )
        resolved[name] = f"libSceAgc+0x{expected_offset:x}"

    result = {
        "schema": 1,
        "firmware": "12.02",
        "helper": "eboot+0x4d78380 (runtime 0x4db8380)",
        "mode": 2,
        "paths": {
            "color_only_flags_0x0c00": {
                "event_write_dwords": [
                    ["0xc0004600", "0x00000410"],
                    ["0xc0004600", "0x0000002e"],
                ],
                "derived_terminal_event_type": "0x2d",
                "public_amd_event_candidates": {
                    "0x10": "PS_PARTIAL_FLUSH",
                    "0x2e": "FLUSH_AND_INV_CB_META",
                    "0x2d": "FLUSH_AND_INV_CB_DATA_TS",
                },
                "clears_input_flag": "0x400",
            },
            "color_depth_flags_0x3c00": {
                "event_write_dwords": [
                    ["0xc0004600", "0x00000410"],
                    ["0xc0004600", "0x0000002e"],
                    ["0xc0004600", "0x0000002c"],
                ],
                "derived_terminal_event_type": "0x14",
                "public_amd_event_candidates": {
                    "0x10": "PS_PARTIAL_FLUSH",
                    "0x2e": "FLUSH_AND_INV_CB_META",
                    "0x2c": "FLUSH_AND_INV_DB_META",
                    "0x14": "CACHE_FLUSH_AND_INV_TS_EVENT",
                },
                "clears_input_flags": "0x1400",
            },
        },
        "resolved_builders": resolved,
        "contains_private_label_patch_chain": True,
        "selected_wait_packet": {
            "opcode": "WAIT_REG_MEM (0x3c)",
            "header": "0xc0053c00",
            "dwords": 7,
            "wait_reg_mem64_0x93_selected": False,
            "template_before_address_patch": [
                "0xc0053c00",
                "0x00000013",
                "0x00000000",
                "0x00000000",
                "0x00000001",
                "0xffffffff",
                "0x00000019",
            ],
            "condition": "memory value equals 1 under 0xffffffff mask",
            "address_patch_dwords": [2, 3],
            "poll_interval": "0x19",
        },
        "selected_release_mem_packets": {
            "builder": "libSceAgc+0x2700",
            "header": "0xc0064900",
            "dwords": 8,
            "address_patch_dwords": [3, 4],
            "payload_dwords": [5, 6],
            "payload_u64": "0x0000000000000001",
            "color_only_before_address_patch": [
                "0xc0064900", "0x0000052d", "0x20010000",
                "0x00000000", "0x00000000", "0x00000001",
                "0x00000000", "0x00000000",
            ],
            "color_depth_before_address_patch": [
                "0xc0064900", "0x00000514", "0x20010000",
                "0x00000000", "0x00000000", "0x00000001",
                "0x00000000", "0x00000000",
            ],
            "effect_after_patch": "write 1 to the shared private label",
        },
        "private_label_protocol": [
            "DMA_DATA initializes the shared label to 0",
            "RELEASE_MEM writes 1 after the terminal cache event",
            "WAIT_REG_MEM polls until the label equals 1 under 0xffffffff",
            "ACQUIRE_MEM covers the same 32-byte label allocation",
        ],
        "selected_acquire_mem_call": {
            "builder": "libSceAgc+0x3830",
            "header": "0xc0065800",
            "raw_register_arguments": {
                "esi": "0x1",
                "edx": "0x0",
                "ecx": "0x9000",
                "r8": "aligned private label address",
                "r9d": "0x20",
                "stack_arg_0": "0x190",
            },
            "range_bytes": 32,
            "runtime_encoder_mode_flags": "0x00000000",
            "selected_encoder_path": "generic",
            "packet_formula": [
                "DW0=0xc0065800",
                "DW1=0x80000000",
                "DW2=ceil(((label & 0xff) + 32) / 256), therefore 1 or 2",
                "DW3=0x00000000",
                "DW4=(label >> 8) & 0xffffffff",
                "DW5=(label >> 40) & 0xff",
                "DW6=0x00000019",
                "DW7=0x00009000",
            ],
            "raw_packet_control_dwords": {
                "dw1": "0x80000000",
                "dw6_poll_interval": "0x00000019",
                "dw7": "0x00009000",
            },
            "range_crosses_256_byte_boundary_when_label_low8_gt": "0xe0",
            "exact_cache_field_semantics_proven": False,
        },
        "safe_minimal_sequence_proven": False,
        "cache_semantics_proven": False,
        "public_amd_names_are_ps5_abi_proof": False,
        "submitted_or_executed": False,
        "target_writes": 0,
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
