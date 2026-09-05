#!/usr/bin/env python3
"""Inspect pre-entry imports and DT_NEEDED in a sectionless Prospero ELF."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


PT_LOAD = 1
PT_DYNAMIC = 2
DT_NULL = 0
DT_NEEDED = 1
DT_PLTRELSZ = 2
DT_STRTAB = 5
DT_SYMTAB = 6
DT_SYMENT = 11
DT_JMPREL = 23


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("elf", type=Path)
    parser.add_argument("--entry-bytes", type=lambda value: int(value, 0),
                        default=0x48)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    data = args.elf.read_bytes()

    if data[:4] != b"\x7fELF" or data[4:6] != b"\x02\x01":
        raise SystemExit("expected a little-endian ELF64")

    entry = struct.unpack_from("<Q", data, 0x18)[0]
    phoff = struct.unpack_from("<Q", data, 0x20)[0]
    phentsize = struct.unpack_from("<H", data, 0x36)[0]
    phnum = struct.unpack_from("<H", data, 0x38)[0]
    loads: list[tuple[int, int, int]] = []
    dynamic: tuple[int, int] | None = None
    for index in range(phnum):
        pos = phoff + index * phentsize
        p_type, _, offset, vaddr, _, filesz, _, _ = struct.unpack_from(
            "<IIQQQQQQ", data, pos)
        if p_type == PT_LOAD:
            loads.append((vaddr, vaddr + filesz, offset))
        elif p_type == PT_DYNAMIC:
            dynamic = (offset, filesz)

    def file_offset(vaddr: int) -> int:
        for start, end, offset in loads:
            if start <= vaddr < end:
                return offset + vaddr - start
        raise ValueError(f"virtual address {vaddr:#x} is not file-backed")

    if dynamic is None:
        raise SystemExit("ELF has no PT_DYNAMIC")

    tags: dict[int, int] = {}
    needed_offsets: list[int] = []
    for pos in range(dynamic[0], dynamic[0] + dynamic[1], 16):
        tag, value = struct.unpack_from("<QQ", data, pos)
        if tag == DT_NULL:
            break
        if tag == DT_NEEDED:
            needed_offsets.append(value)
        tags[tag] = value

    required = (DT_STRTAB, DT_SYMTAB, DT_JMPREL, DT_PLTRELSZ)
    if any(tag not in tags for tag in required):
        raise SystemExit("missing dynamic string/symbol/PLT metadata")
    strtab = file_offset(tags[DT_STRTAB])
    symtab = file_offset(tags[DT_SYMTAB])
    syment = tags.get(DT_SYMENT, 24)

    def string(offset: int) -> str:
        start = strtab + offset
        return data[start:data.index(b"\0", start)].decode("ascii", "replace")

    needed = [string(offset) for offset in needed_offsets]
    relocations: list[dict[str, object]] = []
    jmprel = file_offset(tags[DT_JMPREL])
    for index in range(tags[DT_PLTRELSZ] // 24):
        target, info, _ = struct.unpack_from("<QQq", data, jmprel + index * 24)
        symbol_index = info >> 32
        name_offset = struct.unpack_from("<I", data,
                                         symtab + symbol_index * syment)[0]
        relocations.append({"index": index, "target": target,
                            "symbol": string(name_offset)})

    code_offset = file_offset(entry)
    code = data[code_offset:code_offset + args.entry_bytes]
    calls: list[dict[str, object]] = []
    pos = 0
    while pos + 5 <= len(code):
        if code[pos] != 0xE8:
            pos += 1
            continue
        displacement = struct.unpack_from("<i", code, pos + 1)[0]
        site = entry + pos
        target = site + 5 + displacement
        record: dict[str, object] = {"site": site, "target": target}
        try:
            stub = file_offset(target)
            # Prospero x86-64 PLT stub: ff 25 disp32; 68 relocation_index.
            if data[stub:stub + 2] == b"\xff\x25" and data[stub + 6] == 0x68:
                reloc_index = struct.unpack_from("<I", data, stub + 7)[0]
                record["plt_index"] = reloc_index
                if reloc_index < len(relocations):
                    record["symbol"] = relocations[reloc_index]["symbol"]
        except ValueError:
            pass
        calls.append(record)
        pos += 5

    result = {
        "file": str(args.elf),
        "entry": entry,
        "needed_count": len(needed),
        "needed": needed,
        "entry_calls": calls,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"entry={entry:#x} needed={len(needed)}")
        for call in calls:
            suffix = f" {call['symbol']}" if "symbol" in call else " direct"
            print(f"call {call['site'] - entry:+#x} -> {call['target']:#x}{suffix}")
        for name in needed:
            print(f"needed {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
