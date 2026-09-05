#!/usr/bin/env python3
"""Wrap a sparse runtime module dump in an ELF64 container for analysis."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
PROGRAM_HEADER = struct.Struct("<IIQQQQQQ")
PAGE = 0x4000


def align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & -alignment


def perms_flags(perms: str) -> int:
    return ((4 if "r" in perms else 0) |
            (2 if "w" in perms else 0) |
            (1 if "x" in perms else 0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    source = args.dump.read_bytes()
    base = int(manifest["base"], 0)
    segments = manifest["segments"]
    phoff = ELF_HEADER.size
    data_offset = align(phoff + len(segments) * PROGRAM_HEADER.size, PAGE)

    payloads = []
    phdrs = []
    cursor = data_offset
    for segment in segments:
        start = int(segment["start"], 0)
        end = int(segment["end"], 0)
        size = end - start
        blob = source[start - base:start - base + size]
        if len(blob) != size:
            raise SystemExit(f"short source segment at {start:#x}")
        cursor = align(cursor, PAGE)
        phdrs.append(PROGRAM_HEADER.pack(
            1, perms_flags(segment["perms"]), cursor, start, start,
            size, size, PAGE,
        ))
        payloads.append((cursor, blob))
        cursor += size

    ident = b"\x7fELF" + bytes((2, 1, 1, 0)) + bytes(8)
    header = ELF_HEADER.pack(
        ident, 2, 62, 1, 0, phoff, 0, 0,
        ELF_HEADER.size, PROGRAM_HEADER.size, len(phdrs), 0, 0, 0,
    )
    image = bytearray(cursor)
    image[:len(header)] = header
    for index, phdr in enumerate(phdrs):
        off = phoff + index * PROGRAM_HEADER.size
        image[off:off + len(phdr)] = phdr
    for off, blob in payloads:
        image[off:off + len(blob)] = blob
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)
    print(f"wrote {args.output} with {len(segments)} PT_LOAD segments")


if __name__ == "__main__":
    main()
