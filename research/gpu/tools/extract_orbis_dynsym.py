#!/usr/bin/env python3
"""Extract dynamic symbols from sectionless Orbis/Prospero ELF modules."""

import argparse
import struct
from pathlib import Path


PT_LOAD = 1
PT_DYNAMIC = 2
DT_NULL = 0
DT_HASH = 4
DT_STRTAB = 5
DT_SYMTAB = 6
DT_SYMENT = 11


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("module", type=Path)
    parser.add_argument(
        "--offset", action="append", type=lambda value: int(value, 0), default=[]
    )
    args = parser.parse_args()
    data = args.module.read_bytes()

    phoff = struct.unpack_from("<Q", data, 0x20)[0]
    phentsize = struct.unpack_from("<H", data, 0x36)[0]
    phnum = struct.unpack_from("<H", data, 0x38)[0]
    loads = []
    dynamic = None
    for index in range(phnum):
        entry = phoff + index * phentsize
        p_type, _, p_offset, p_vaddr, _, p_filesz, _, _ = struct.unpack_from(
            "<IIQQQQQQ", data, entry
        )
        if p_type == PT_LOAD:
            loads.append((p_vaddr, p_vaddr + p_filesz, p_offset))
        elif p_type == PT_DYNAMIC:
            dynamic = (p_offset, p_filesz)

    def file_offset(vaddr: int) -> int:
        for start, end, offset in loads:
            if start <= vaddr < end:
                return offset + vaddr - start
        raise ValueError(f"virtual address {vaddr:#x} is not file-backed")

    if dynamic is None:
        raise SystemExit("module has no PT_DYNAMIC")

    tags = {}
    dynamic_offset, dynamic_size = dynamic
    for entry in range(dynamic_offset, dynamic_offset + dynamic_size, 16):
        tag, value = struct.unpack_from("<QQ", data, entry)
        if tag == DT_NULL:
            break
        tags[tag] = value

    required = (DT_HASH, DT_STRTAB, DT_SYMTAB)
    if any(tag not in tags for tag in required):
        raise SystemExit("module lacks DT_HASH, DT_STRTAB, or DT_SYMTAB")
    syment = tags.get(DT_SYMENT, 24)
    _, symbol_count = struct.unpack_from("<II", data, file_offset(tags[DT_HASH]))
    wanted = set(args.offset)

    print("index value      size   bind type shndx NID/library/module")
    for index in range(symbol_count):
        entry = file_offset(tags[DT_SYMTAB]) + index * syment
        name_offset, info, _, shndx, value, size = struct.unpack_from(
            "<IBBHQQ", data, entry
        )
        if wanted and value not in wanted:
            continue
        start = file_offset(tags[DT_STRTAB]) + name_offset
        end = data.index(b"\0", start)
        name = data[start:end].decode("ascii", "replace")
        print(
            f"{index:5d} {value:#010x} {size:#06x} {info >> 4:4d} "
            f"{info & 0xf:4d} {shndx:#05x} {name}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
