#!/usr/bin/env python3
"""Decode only PS5 mapping-protection bits supported by public evidence."""

from __future__ import annotations

import argparse


KNOWN_BITS = {
    0x001: "CPU_READ",
    0x002: "CPU_WRITE",
    0x004: "CPU_EXEC",
    0x010: "GPU_READ",
    0x020: "GPU_WRITE",
}


def decode(value: int) -> tuple[list[str], int]:
    names = [name for bit, name in KNOWN_BITS.items() if value & bit]
    known_mask = sum(KNOWN_BITS)
    return names, value & ~known_mask


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("values", nargs="+", type=lambda text: int(text, 0))
    args = parser.parse_args()
    for value in args.values:
        names, unknown = decode(value)
        rendered = " | ".join(names) if names else "none"
        print(f"0x{value:x}: {rendered}; unknown=0x{unknown:x}")


if __name__ == "__main__":
    main()
