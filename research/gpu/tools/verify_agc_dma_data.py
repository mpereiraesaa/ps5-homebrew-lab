#!/usr/bin/env python3
"""Verify firmware-12.02 AGC DMA_DATA builders from authorized dumps.

The verifier is intentionally byte-oriented.  It identifies the two exports,
checks their seven-DWORD packet construction, and proves that the runtime game
copy contains the same code.  It does not execute or submit GPU commands.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import mmap
import platform
import struct
from pathlib import Path


PT_LOAD = 1
PT_DYNAMIC = 2
DT_NULL = 0
DT_HASH = 4
DT_STRTAB = 5
DT_SYMTAB = 6
DT_SYMENT = 11


def parse_elf(data: bytes) -> tuple[list[tuple[int, int, int]], dict[int, int]]:
    if data[:4] != b"\x7fELF":
        raise SystemExit("system module is not an ELF")
    phoff = struct.unpack_from("<Q", data, 0x20)[0]
    phentsize = struct.unpack_from("<H", data, 0x36)[0]
    phnum = struct.unpack_from("<H", data, 0x38)[0]
    loads: list[tuple[int, int, int]] = []
    dynamic: tuple[int, int] | None = None
    for index in range(phnum):
        entry = phoff + index * phentsize
        p_type, _, offset, vaddr, _, filesz, _, _ = struct.unpack_from(
            "<IIQQQQQQ", data, entry
        )
        if p_type == PT_LOAD:
            loads.append((vaddr, vaddr + filesz, offset))
        elif p_type == PT_DYNAMIC:
            dynamic = (offset, filesz)
    if dynamic is None:
        raise SystemExit("system module has no PT_DYNAMIC")
    tags: dict[int, int] = {}
    offset, size = dynamic
    for entry in range(offset, offset + size, 16):
        tag, value = struct.unpack_from("<QQ", data, entry)
        if tag == DT_NULL:
            break
        tags[tag] = value
    return loads, tags


def file_offset(loads: list[tuple[int, int, int]], vaddr: int) -> int:
    for start, end, offset in loads:
        if start <= vaddr < end:
            return offset + vaddr - start
    raise SystemExit(f"virtual address {vaddr:#x} is not file-backed")


def symbols(data: bytes, loads: list[tuple[int, int, int]], tags: dict[int, int]) -> dict[int, str]:
    for required in (DT_HASH, DT_STRTAB, DT_SYMTAB):
        if required not in tags:
            raise SystemExit(f"missing dynamic tag {required}")
    _, count = struct.unpack_from("<II", data, file_offset(loads, tags[DT_HASH]))
    syment = tags.get(DT_SYMENT, 24)
    result: dict[int, str] = {}
    for index in range(count):
        entry = file_offset(loads, tags[DT_SYMTAB]) + index * syment
        name_offset, _, _, _, value, _ = struct.unpack_from("<IBBHQQ", data, entry)
        start = file_offset(loads, tags[DT_STRTAB]) + name_offset
        end = data.index(b"\0", start)
        result[value] = data[start:end].decode("ascii", "replace")
    return result


def expect_at(blob: bytes, offset: int, expected: bytes, label: str) -> None:
    actual = blob[offset:offset + len(expected)]
    if actual != expected:
        raise SystemExit(
            f"{label}: mismatch at {offset:#x}: expected {expected.hex()}, got {actual.hex()}"
        )


def encode_dcb_raw(
    arg2: int, arg3: int, arg4: int, destination: int, arg6: int,
    arg7: int, source_or_arg8: int, byte_count: int, arg10: int,
    arg11: int, arg12: int,
) -> list[int]:
    """Reproduce the firmware-12.02 DCB builder without semantic enum names."""
    special_sources = {
        0x14: (0x30174, 0x30148),
        0x24: (0x3017C, 0x30150),
        0x64: (0x30184, 0x30158),
    }
    if arg6 in special_sources:
        source = special_sources[arg6][1 if arg2 == 1 else 0]
    else:
        source = source_or_arg8
    dw1 = (
        ((arg12 & 1) << 31)
        | ((arg6 & 3) << 29)
        | ((arg4 & 3) << 25)
        | ((arg3 & 3) << 20)
        | ((arg7 & 3) << 13)
        | (arg2 & 1)
    )
    dw6 = (
        ((arg11 & 1) << 31)
        | ((arg10 & 1) << 30)
        | ((arg3 & 8) << 26)
        | ((arg6 & 8) << 25)
        | ((arg3 & 4) << 25)
        | ((arg6 & 4) << 24)
        | (byte_count & 0x03FFFFFF)
    )
    return [
        0xC0055000,
        dw1 & 0xFFFFFFFF,
        source & 0xFFFFFFFF,
        (source >> 32) & 0xFFFFFFFF,
        destination & 0xFFFFFFFF,
        (destination >> 32) & 0xFFFFFFFF,
        dw6 & 0xFFFFFFFF,
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("system_agc", type=Path)
    parser.add_argument("runtime_agc", type=Path)
    parser.add_argument("eboot", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--execute-local-builder", action="store_true",
        help="execute the authorized DCB builder bytes in an isolated host buffer",
    )
    args = parser.parse_args()

    system = args.system_agc.read_bytes()
    runtime = args.runtime_agc.read_bytes()
    eboot = args.eboot.read_bytes()
    loads, tags = parse_elf(system)
    dynsym = symbols(system, loads, tags)

    expected_symbols = {
        0x740: "-RnpfpxIhec#G#A",   # sceAgcAcbDmaData
        0x47D0: "WmAc2MEj6Io#G#A",  # sceAgcDcbDmaData
    }
    for address, name in expected_symbols.items():
        if dynsym.get(address) != name:
            raise SystemExit(
                f"symbol mismatch at {address:#x}: expected {name}, got {dynsym.get(address)}"
            )

    # The first executable PT_LOAD maps virtual address zero at file offset
    # 0x4000.  Verify the packet header stores and the following payload stores.
    acb_file = file_offset(loads, 0x740)
    dcb_file = file_offset(loads, 0x47D0)
    acb_header = bytes.fromhex("41c702005005c0")
    dcb_header = bytes.fromhex("41c702005005c0")
    expect_at(system, acb_file + 0xF6, acb_header, "ACB DMA_DATA header")
    expect_at(system, dcb_file + 0x117, dcb_header, "DCB DMA_DATA header")
    expect_at(system, acb_file + 0x176,
              bytes.fromhex("4189520441895a084589420c41894a10"),
              "ACB DMA_DATA address payload stores")
    expect_at(system, acb_file + 0x188,
              bytes.fromhex("45894a14"), "ACB DMA_DATA source-high store")
    expect_at(system, acb_file + 0x194,
              bytes.fromhex("41897a18"), "ACB DMA_DATA control store")
    expect_at(system, dcb_file + 0x1B2,
              bytes.fromhex("41894a0441895a084189720c4589421045894a1441897a18"),
              "DCB DMA_DATA payload stores")

    # The authorized runtime mapping starts at module virtual address zero.
    # Comparing whole exported functions also detects firmware/game drift.
    sizes = {0x740: 0x1AB, 0x47D0: 0x1DD}
    for address, size in sizes.items():
        system_function = system[file_offset(loads, address):file_offset(loads, address) + size]
        runtime_function = runtime[address:address + size]
        if runtime_function != system_function:
            raise SystemExit(f"runtime function differs from system export at {address:#x}")

    eboot_base = 0x400000
    runtime_base = 0x80058C000

    # San Andreas creates a four-byte immediate-zero DMA template.  The call
    # has r8=0 (placeholder destination), r9=2 (ordinary source path), stack
    # args 7..12 = 0,0,4,0,0,1.  Firmware +0x47d0 therefore selects the stack
    # source zero, encodes four bytes, and requests the blocking form.
    expect_at(eboot, 0x4DB8518 - eboot_base,
              bytes.fromhex(
                  "be0000000048898548fbffff4889dfba03000000b90000000041b800000000"
                  "41b9020000006a016a006a006a046a006a00e8c2860000"
              ), "four-byte immediate-zero DMA template")

    def thunk_target(address: int) -> int:
        offset = address - eboot_base
        expect_at(eboot, offset, bytes.fromhex("ff25"), f"thunk {address:#x}")
        displacement = struct.unpack_from("<i", eboot, offset + 2)[0]
        slot = address + 6 + displacement
        return struct.unpack_from("<Q", eboot, slot - eboot_base)[0]

    expected_thunks = {
        0x4DC0C10: runtime_base + 0x47D0,  # sceAgcDcbDmaData
        0x4DC1CA0: runtime_base + 0xD0C0,  # DmaData patch destination
        0x4DC1CB0: runtime_base + 0xD100,  # WaitRegMem patch address
        0x4DC1CC0: runtime_base + 0xD320,  # ReleaseMem patch address
    }
    for thunk, target in expected_thunks.items():
        actual = thunk_target(thunk)
        if actual != target:
            raise SystemExit(
                f"thunk {thunk:#x}: expected target {target:#x}, got {actual:#x}"
            )

    callsite_shapes = [
        # start, end-after-call, sha256, family, raw a2/a3/a4/a6/a7/a9/a10/a11/a12
        (0x1F218EE, 0x1F21921, "b22dde13b6142025109f936aec647545bc5284705ff21777e928803ec31e6bd7",
         "four-byte indexed copy", [0, 0, 3, 1, 3, 4, 0, 0, 1]),
        (0x1F2FDFF, 0x1F2FE3B, "bab6f3cbb820d71ef65e6c2fdc6a7be55c5139b342a528c64022b10e401f8601",
         "four-byte immediate zero", [0, 0, 3, 2, 3, 4, 0, 0, 1]),
        (0x1F2FE9B, 0x1F2FECE, "e19d1cf3a56ae2b6f4a56e99cd04d0546c0a263bf9fe630f971d9171e849d518",
         "four-byte immediate zero", [0, 0, 3, 2, 3, 4, 0, 0, 1]),
        (0x1F31A0D, 0x1F31A3B, "69bc238030fe3915fc6868e385b4f2a0c0a77d173289f1aa8cd3afc5e76565cc",
         "four-byte indexed copy", [0, 0, 3, 1, 3, 4, 1, 0, 1]),
        (0x1F31A5D, 0x1F31A86, "d65d06faa2b20203cb64b55db13a6f9532b8683b3c3f0ba49b109bc7308bdc63",
         "four-byte reverse-direction copy", [0, 1, 3, 0, 3, 4, 1, 0, 1]),
        (0x1F3AC77, 0x1F3ACA8, "43153b4dc11e5b5b37e73097e97b290359f7b2e7324f93430ea483bd4de026b4",
         "dynamic-length copy", [0, 0, 3, 3, 0, "dynamic", 1, 0, 1]),
        (0x1F4C632, 0x1F4C670, "0ef11de8a401c6e7d745af4fd35e70dcdfe3cc47fb4c9d257f7a3c15cd2b15df",
         "dynamic-length copy", [0, 0, 0, 0, 0, "dynamic", 1, 0, 1]),
        (0x1F64BD1, 0x1F64C0D, "c0dada2751da5d0c4175db3f7ecbe1b7e489fb81d80823e053629be3b8c3872b",
         "dynamic-length copy", [0, 0, 0, 0, 0, "dynamic", 1, 0, 1]),
        (0x4DB8518, 0x4DB854E, "5d9bf8d8a802056bbd4ae3831680a66dc0e07e32e29e5095863a99a2e9c21779",
         "four-byte immediate-zero template", [0, 3, 0, 2, 0, 4, 0, 0, 1]),
    ]
    verified_callsites = []
    for start, end, expected_hash, family, raw_constants in callsite_shapes:
        window = eboot[start - eboot_base:end - eboot_base]
        actual_hash = hashlib.sha256(window).hexdigest()
        if actual_hash != expected_hash:
            raise SystemExit(f"DCB callsite window changed at {start:#x}")
        if len(window) < 5 or window[-5] != 0xE8:
            raise SystemExit(f"DCB callsite does not end in rel32 CALL at {end - 5:#x}")
        displacement = struct.unpack_from("<i", window, len(window) - 4)[0]
        target = end + displacement
        if target != 0x4DC0C10:
            raise SystemExit(f"DCB callsite {end - 5:#x} targets {target:#x}")
        verified_callsites.append({
            "site": hex(end - 5),
            "window": [hex(start), hex(end)],
            "sha256": expected_hash,
            "family": family,
            "raw_constants_a2_a3_a4_a6_a7_a9_a10_a11_a12": raw_constants,
            "source_and_destination": "dynamic unless family says immediate zero",
        })

    # Firmware patchers validate opcode byte 0x50 before touching the packet.
    # Destination is the qword at packet+0x10 (DWORD4/5); source is packet+0x08
    # (DWORD2/3).  The destination patch therefore cannot overwrite header,
    # control, immediate zero, or byte count.
    expect_at(system, file_offset(loads, 0xD0C0),
              bytes.fromhex(
                  "0fb64f01b80c006c8ac1e10881f900500000750631c048897710c3"
              ), "DMA destination patcher")
    expect_at(system, file_offset(loads, 0xD0E0),
              bytes.fromhex(
                  "0fb64f01b80c006c8ac1e10881f900500000750631c048897708c3"
              ), "DMA source patcher")

    # The template is copied, rebased into the real command stream and its
    # destination is patched to the same aligned label used by wait/release.
    expect_at(eboot, 0x4DB8634 - eboot_base,
              bytes.fromhex("89db4c89e74c89fe48c1e3024889dae8282c0000"),
              "DMA template copy")
    expect_at(eboot, 0x4DB8653 - eboot_base,
              bytes.fromhex(
                  "488bb548fbffff4c8bbd50fbffff4c8bb558fbffff"
                  "488dbd90fbffff31d24c01a568fbffff"
                  "4c01e64d01e74d01e6"
              ), "DMA template rebase")
    expect_at(eboot, 0x4DB868D - eboot_base,
              bytes.fromhex(
                  "4c89ff4883c3074883e3f84889dee800960000"
                  "4c89f74889dee805960000488bbd68fbffff4889de"
                  "e806960000"
              ), "DMA destination/wait/release patch chain")

    local_execution = False
    if args.execute_local_builder:
        if platform.machine() not in ("x86_64", "AMD64"):
            raise SystemExit("local builder execution requires an x86-64 host")

        class Dcb(ctypes.Structure):
            _fields_ = [
                ("pad0", ctypes.c_uint8 * 0x10),
                ("cursor", ctypes.POINTER(ctypes.c_uint32)),
                ("end", ctypes.POINTER(ctypes.c_uint32)),
                ("grow", ctypes.c_void_p),
                ("grow_arg", ctypes.c_void_p),
                ("reserved", ctypes.c_uint32),
            ]

        code = runtime[0x47D0:0x47D0 + sizes[0x47D0]]
        executable = mmap.mmap(
            -1, len(code),
            prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC,
        )
        executable.write(code)
        function_address = ctypes.addressof(ctypes.c_char.from_buffer(executable))
        function = ctypes.CFUNCTYPE(ctypes.c_void_p, *([ctypes.c_uint64] * 12))(
            function_address
        )
        raw_cases = [
            (0, 3, 0, 0, 2, 0, 0, 4, 0, 0, 1),
            (1, 0xC, 3, 0x1122334455667788, 7, 2,
             0x8877665544332211, 0x03FFFFFF, 1, 1, 0),
            (0, 1, 2, 0xFEDCBA9876543210, 0x14, 3,
             0xDEADBEEFDEADBEEF, 0x1234, 0, 1, 1),
            (1, 2, 0, 0x0102030405060708, 0x24, 0,
             0xBBBBBBBBBBBBBBBB, 0x20, 0, 0, 1),
            (1, 4, 1, 0x0000000100000040, 0x64, 1,
             0xAAAAAAAAAAAAAAAA, 0x40, 1, 0, 0),
        ]
        for raw_case in raw_cases:
            output = (ctypes.c_uint32 * 32)()
            dcb = Dcb()
            dcb.cursor = ctypes.cast(output, ctypes.POINTER(ctypes.c_uint32))
            dcb.end = ctypes.cast(
                ctypes.addressof(output) + ctypes.sizeof(output),
                ctypes.POINTER(ctypes.c_uint32),
            )
            returned = function(ctypes.addressof(dcb), *raw_case)
            expected_packet = encode_dcb_raw(*raw_case)
            cursor_bytes = ctypes.addressof(dcb.cursor.contents) - ctypes.addressof(output)
            if (returned != ctypes.addressof(output)
                    or list(output[:7]) != expected_packet or cursor_bytes != 28):
                raise SystemExit(
                    "isolated local DCB builder differs from raw formula: "
                    f"case={raw_case!r} expected={expected_packet!r} "
                    f"actual={list(output[:7])!r} cursor={cursor_bytes}"
                )
        local_execution = True
        executable.close()

    proof = {
        "firmware_scope": "12.02",
        "packet": {
            "pm4_header": "0xc0055000",
            "dwords": 7,
            "opcode": "DMA_DATA (0x50)",
        },
        "exports": {
            "acb": {"offset": "0x740", "nid": "-RnpfpxIhec", "name": "sceAgcAcbDmaData"},
            "dcb": {"offset": "0x47d0", "nid": "WmAc2MEj6Io", "name": "sceAgcDcbDmaData"},
        },
        "runtime_matches_system": True,
        "immediate_source_form_present": True,
        "raw_dcb_packet_formula": {
            "argument_order_after_dcb": [
                "arg2", "arg3", "arg4", "destination", "arg6", "arg7",
                "source_or_arg8", "byte_count", "arg10", "arg11", "arg12"
            ],
            "byte_count_mask": "0x03ffffff",
            "destination_field": "DWORD4/5",
            "source_field": "DWORD2/3 or firmware special-source table",
            "control_fields": "DW1 and DW6; exact raw bit formula encoded by verifier",
            "ordinary_semantic_field_mapping_proven": True,
            "special_source_enum_names_proven": False,
            "locally_cross_checked_cases": 5 if local_execution else 0,
        },
        "amd_pal_gfx9_correlation": {
            "a2_dw1_bit0": "engine_sel (0=ME, 1=PFP)",
            "a3_low2_dw1_bits20_21": "dst_sel",
            "a3_bit2_dw6_bit27": "das (destination address space)",
            "a3_bit3_dw6_bit29": "daic (destination address increment control)",
            "a4_low2_dw1_bits25_26": "dst_cache_policy",
            "a6_low2_dw1_bits29_30": "src_sel",
            "a6_bit2_dw6_bit26": "sas (source address space)",
            "a6_bit3_dw6_bit28": "saic (source address increment control)",
            "a7_low2_dw1_bits13_14": "src_cache_policy",
            "a12_dw1_bit31": "cp_sync / sync",
            "a10_dw6_bit30": "raw_wait",
            "a11_dw6_bit31": "dis_wc (disable write-confirm)",
            "byte_count_dw6_bits_0_25": True,
            "observed_all_nine_a12": 1,
            "observed_all_nine_a11": 0,
            "ordinary_selector_encoding_proven": True,
            "status": "bit-exact firmware encoding correlated with official AMD GFX9 packet fields",
        },
        "prosper_secondary_correlation": {
            "repository": "https://github.com/mattias800/prosper",
            "commit": "5842615a4b4da06802d505339beda809af96b489",
            "dcb_nid": "WmAc2MEj6Io",
            "corroborates": [
                "seven-DWORD builder size",
                "destination argument and destination patcher",
                "immediate versus address source forms",
                "byte-count argument",
                "four-byte zero label initialization before ReleaseMem"
            ],
            "limitation": "Prosper emits a private translated packet; native PM4 layout is proven from firmware/PAL, not copied from Prosper",
        },
        "observed_safe_case": {
            "game": "PPSA03524 San Andreas",
            "operation": "four-byte immediate-zero label initialization",
            "destination": "placeholder patched before submit",
            "paired_with": ["WaitRegMem", "ReleaseMem"],
            "template_dwords": [
                "0xc0055000", "0xc0300000", "0x00000000",
                "0x00000000", "0x00000000", "0x00000000",
                "0x00000004"
            ],
            "destination_field": "DWORD4/5, patched through sceAgcDmaDataPatchSetDstAddressOrOffset",
            "decoded_controls": {
                "engine": "ME",
                "destination": "dst_addr_using_l2",
                "destination_cache_policy": "lru",
                "source": "immediate data",
                "source_cache_policy": "lru",
                "source_address_space": "memory",
                "destination_address_space": "memory",
                "source_increment": "increment",
                "destination_increment": "increment",
                "cp_sync": True,
                "raw_wait": False,
                "dis_wc": False
            },
            "byte_verified": True,
            "local_builder_execution_verified": local_execution,
        },
        "raw_packet_abi_proven": True,
        "san_andreas_dcb_callsites": {
            "count": len(verified_callsites),
            "all_target_verified_thunk": "0x4dc0c10",
            "entries": verified_callsites,
        },
        "safe_generic_fill_encoding_proven": True,
        "homebrew_gpu_mapping_and_submit_proven": False,
        "safe_generic_fill_hardware_execution_proven": False,
        "submitted_or_executed": False,
    }
    encoded = json.dumps(proof, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
