#!/usr/bin/env python3
"""Resolve selected optional AGC exports from an authorized local module dump."""

from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "research/gpu/dumps/system-libSceAgc.sprx"

# Values independently regenerated from the public function names.
EXPECTED = {
    "57labkp+rSQ#G#A": (0x3830, 798),  # sceAgcDcbAcquireMem
    "ZvwO9euwYzc#G#A": (0x4120, 203),  # sceAgcDcbSetCxRegistersIndirect
    "aJf+j5yntiU#G#A": (0x5CE0, 364),  # sceAgcDcbEventWrite
    "h9z6+0hEydk#G#A": (0x8980, 148),   # sceAgcSuspendPoint
    "i1jyy49AjXU#G#A": (0x49B0, 612),  # sceAgcDcbWriteData
    "n2fD4A+pb+g#G#A": (0x28D0, 237),  # sceAgcCbSetShRegisterRangeDirect
    "pFLArOT53+w#G#A": (0x4F10, 163),  # sceAgcDcbSetShRegisterDirect
    "VmW0Tdpy420#G#A": (0x6E00, 798),  # sceAgcDcbWaitRegMem
    "wr23dPKyWc0#G#A": (0x2700, 451),  # sceAgcCbReleaseMem
    "Yw0jKSqop+E#G#A": (0x5240, 195),  # sceAgcDcbDrawIndexAuto
    "q88lQ+GP5Yk#G#A": (0x5310, 229),  # sceAgcDcbDrawIndex
}


def fail(message: str) -> None:
    raise SystemExit(f"optional AGC export verification failed: {message}")


def main() -> int:
    data = MODULE.read_bytes()

    # These addresses come from the module's own PT_DYNAMIC tags. In this dump,
    # the metadata LOAD segment maps file_offset = virtual_address + 0x4000.
    strtab_va, strtab_size = 0x461A0, 5923
    symtab_va, hash_va = 0x478C8, 0x548D0
    bias = 0x4000
    string_offset = strtab_va + bias
    symbol_offset = symtab_va + bias
    _, symbol_count = struct.unpack_from("<II", data, hash_va + bias)

    found: dict[str, tuple[int, int]] = {}
    for index in range(symbol_count):
        name_offset, _, _, _, value, size = struct.unpack_from(
            "<IBBHQQ", data, symbol_offset + index * 24)
        if name_offset >= strtab_size:
            continue
        start = string_offset + name_offset
        end = data.find(b"\0", start)
        if end < 0:
            fail("unterminated dynamic symbol")
        name = data[start:end].decode("ascii", errors="strict")
        if name in EXPECTED:
            found[name] = (value, size)

    if found != EXPECTED:
        fail(f"export map drift: {found!r}")
    print("optional AGC exports passed: direct SH, auto/indexed draw, "
          "acquire/release/event/write/wait synchronization, suspend point")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
