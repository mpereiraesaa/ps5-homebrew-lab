#!/usr/bin/env python3
"""Test public hash hypotheses without emitting proprietary shader values."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import struct
import zlib
from pathlib import Path


MASK64 = (1 << 64) - 1


def rol(value: int, bits: int) -> int:
    return ((value << bits) | (value >> (64 - bits))) & MASK64


def xxh64(data: bytes, seed: int = 0) -> int:
    p1, p2 = 11400714785074694791, 14029467366897019727
    p3, p4, p5 = 1609587929392839161, 9650029242287828579, 2870177450012600261

    def rnd(acc: int, lane: int) -> int:
        acc = (acc + lane * p2) & MASK64
        return (rol(acc, 31) * p1) & MASK64

    pos = 0
    if len(data) >= 32:
        v1, v2, v3, v4 = (seed + p1 + p2) & MASK64, (seed + p2) & MASK64, seed, (seed - p1) & MASK64
        while pos <= len(data) - 32:
            v1 = rnd(v1, struct.unpack_from("<Q", data, pos)[0]); pos += 8
            v2 = rnd(v2, struct.unpack_from("<Q", data, pos)[0]); pos += 8
            v3 = rnd(v3, struct.unpack_from("<Q", data, pos)[0]); pos += 8
            v4 = rnd(v4, struct.unpack_from("<Q", data, pos)[0]); pos += 8
        value = (rol(v1, 1) + rol(v2, 7) + rol(v3, 12) + rol(v4, 18)) & MASK64
        for lane in (v1, v2, v3, v4):
            value ^= rnd(0, lane)
            value = (value * p1 + p4) & MASK64
    else:
        value = (seed + p5) & MASK64
    value = (value + len(data)) & MASK64
    while pos <= len(data) - 8:
        lane = rnd(0, struct.unpack_from("<Q", data, pos)[0])
        value ^= lane
        value = (rol(value, 27) * p1 + p4) & MASK64
        pos += 8
    if pos <= len(data) - 4:
        value ^= struct.unpack_from("<I", data, pos)[0] * p1
        value = (rol(value, 23) * p2 + p3) & MASK64
        pos += 4
    while pos < len(data):
        value ^= data[pos] * p5
        value = (rol(value, 11) * p1) & MASK64
        pos += 1
    value ^= value >> 33; value = (value * p2) & MASK64
    value ^= value >> 29; value = (value * p3) & MASK64
    return value ^ (value >> 32)


def fnv64(data: bytes) -> int:
    value = 14695981039346656037
    for byte in data:
        value ^= byte
        value = (value * 1099511628211) & MASK64
    return value


def halves(value: int) -> tuple[int, int]:
    return value & 0xFFFFFFFF, value >> 32


def checksum_pair(header: bytes) -> tuple[int, int] | None:
    stage = header[0x5A]
    wanted = 0x006 if stage == 1 else 0x080 if stage == 2 else None
    if wanted is None:
        return None
    count = header[0x5C]
    start = 0x20 + struct.unpack_from("<Q", header, 0x20)[0]
    values = [struct.unpack_from("<II", header, start + i * 8)[1]
              for i in range(count)
              if struct.unpack_from("<II", header, start + i * 8)[0] == wanted]
    return tuple(values) if len(values) == 2 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path("research/gpu/shaders/san-andreas-authorized"))
    args = parser.parse_args()
    matches: dict[str, int] = {}
    total = 0
    for name in glob.glob(str(args.root / "*.header.bin")):
        header = Path(name).read_bytes()
        observed = checksum_pair(header)
        if observed is None:
            continue
        code = Path(name.replace(".header.bin", ".code.bin")).read_bytes()
        scrubbed = bytearray(header)
        count = header[0x5C]
        start = 0x20 + struct.unpack_from("<Q", header, 0x20)[0]
        for i in range(count):
            offset = struct.unpack_from("<I", header, start + i * 8)[0]
            if offset in (0x006, 0x080):
                scrubbed[start + i * 8 + 4:start + i * 8 + 8] = b"\0" * 4
        variants = {
            "code": code,
            "code_pad16": code + b"\0" * (-len(code) % 16),
            "code_pad64": code + b"\0" * (-len(code) % 64),
            "code_pad256": code + b"\0" * (-len(code) % 256),
            "header_scrubbed": bytes(scrubbed),
            "header_scrubbed_code": bytes(scrubbed) + code,
            "code_header_scrubbed": code + bytes(scrubbed),
        }
        candidates = {}
        for variant, payload in variants.items():
            candidates.update({
                f"{variant}:fnv1a64": halves(fnv64(payload)),
                f"{variant}:xxhash64_seed0": halves(xxh64(payload)),
                f"{variant}:blake2b64": halves(int.from_bytes(
                    hashlib.blake2b(payload, digest_size=8).digest(), "little")),
                f"{variant}:sha256_first64": struct.unpack_from(
                    "<II", hashlib.sha256(payload).digest()),
                f"{variant}:crc32_adler32": (
                    zlib.crc32(payload) & 0xFFFFFFFF,
                    zlib.adler32(payload) & 0xFFFFFFFF),
            })
        for label, candidate in candidates.items():
            if observed == candidate:
                matches[label] = matches.get(label, 0) + 1
            if observed == candidate[::-1]:
                matches[label + "_swapped"] = matches.get(label + "_swapped", 0) + 1
        total += 1
    print(json.dumps({
        "schema": 1,
        "graphics_headers": total,
        "proprietary_values_emitted": False,
        "exact_pair_matches": matches,
        "all_candidates_rejected": not matches,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
