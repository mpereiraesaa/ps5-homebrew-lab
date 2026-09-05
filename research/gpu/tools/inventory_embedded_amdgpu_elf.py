#!/usr/bin/env python3
"""Inventory embedded 64-bit little-endian AMDGPU ELF objects without extraction."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


ELF64_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
ELF64_SECTION = struct.Struct("<IIQQQQIIQQ")


def validate_amdgpu_elf(blob: bytes, base: int) -> dict[str, object] | None:
    """Validate a bounded ELF64 AMDGPU section table without extracting data."""
    if base < 0 or base + ELF64_HEADER.size > len(blob):
        return None
    fields = ELF64_HEADER.unpack_from(blob, base)
    ident = fields[0]
    machine = fields[2]
    shoff, ehsize, shentsize, shnum, shstrndx = (
        fields[6], fields[8], fields[11], fields[12], fields[13]
    )
    if ident[:6] != b"\x7fELF\x02\x01" or ident[6] != 1 or machine != 0xE0:
        return None
    if ehsize != ELF64_HEADER.size or shentsize != ELF64_SECTION.size:
        return None
    if not shnum or shnum > 0x4000 or shstrndx >= shnum:
        return None
    section_table_end = shoff + shnum * shentsize
    if shoff < ehsize or section_table_end > len(blob) - base:
        return None

    sections = [
        ELF64_SECTION.unpack_from(blob, base + shoff + index * shentsize)
        for index in range(shnum)
    ]
    shstr = sections[shstrndx]
    strings_offset, strings_size = shstr[4], shstr[5]
    if strings_offset + strings_size > len(blob) - base:
        return None
    strings = blob[base + strings_offset:base + strings_offset + strings_size]

    names: list[str] = []
    for section in sections:
        name_offset, section_type, offset, size = (
            section[0], section[1], section[4], section[5]
        )
        if name_offset >= len(strings):
            return None
        terminator = strings.find(b"\0", name_offset)
        if terminator < 0:
            return None
        if section_type != 8 and offset + size > len(blob) - base:  # SHT_NOBITS
            return None
        names.append(strings[name_offset:terminator].decode("ascii", "replace"))

    required = {".shader_header", ".shader_text"}
    present = sorted(required.intersection(names))
    return {
        "offset": hex(base),
        "machine": "EM_AMDGPU (0xe0)",
        "section_count": shnum,
        "shader_sections": present,
        "has_shader_pair": required.issubset(names),
    }


def inventory(path: Path) -> dict[str, object]:
    blob = path.read_bytes()
    offsets: list[int] = []
    amdgpu: list[dict[str, object]] = []
    position = 0
    while True:
        position = blob.find(b"\x7fELF", position)
        if position < 0:
            break
        offsets.append(position)
        candidate = validate_amdgpu_elf(blob, position)
        if candidate is not None:
            amdgpu.append(candidate)
        position += 4
    return {
        "path": str(path),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "elf_magic_count": len(offsets),
        "elf_magic_offsets": [hex(offset) for offset in offsets],
        "amdgpu_elf_count": len(amdgpu),
        "amdgpu_shader_pair_count": sum(
            bool(candidate["has_shader_pair"]) for candidate in amdgpu
        ),
        "amdgpu_candidates": amdgpu,
        "content_extracted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = [inventory(path) for path in args.inputs]
    result = {
        "schema": 1,
        "scan_kind": "read-only signature inventory",
        "records": records,
        "total_amdgpu_elf": sum(int(record["amdgpu_elf_count"]) for record in records),
        "interpretation": (
            "No embedded AMDGPU ELF exists in these captures; inspect authorized shader "
            "mappings/heaps or asset containers instead."
            if all(record["amdgpu_elf_count"] == 0 for record in records)
            else "One or more candidates require section-table validation before extraction."
        ),
        "console_contacted": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
