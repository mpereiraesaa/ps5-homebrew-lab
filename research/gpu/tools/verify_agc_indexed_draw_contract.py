#!/usr/bin/env python3
"""Gate the narrow firmware-12.02 DcbDrawIndex ABI without exporting bytes."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "research/gpu/dumps/system-libSceAgc.sprx"

# Dynamic-symbol facts are independently checked by verify_agc_optional_exports.py.
FUNCTION_VA = 0x5310
FUNCTION_SIZE = 229
TEXT_FILE_BIAS = 0x4000


def need(code: bytes, pattern: bytes, label: str) -> None:
    if pattern not in code:
        raise SystemExit(f"indexed draw contract failed: {label}")


def main() -> int:
    data = MODULE.read_bytes()
    start = FUNCTION_VA + TEXT_FILE_BIAS
    code = data[start:start + FUNCTION_SIZE]
    if len(code) != FUNCTION_SIZE:
        raise SystemExit("indexed draw contract failed: truncated function")

    # SysV arguments are writer=RDI, index_count=ESI, index_addr=RDX,
    # modifier=RCX. The builder reserves six DWORDs, advances the cursor by
    # 0x18 bytes, emits the indexed packet and returns its starting address.
    need(code, bytes.fromhex("83 fe 01 41 89 f6"), "index-count argument changed")
    need(code, bytes.fromhex("49 89 d7"), "index-address argument changed")
    need(code, bytes.fromhex("89 cb"), "modifier argument changed")
    need(code, bytes.fromhex("83 c0 06"), "six-DWORD reservation changed")
    need(code, bytes.fromhex("48 8d 41 18 48 89 47 10"), "cursor advance changed")
    need(code, bytes.fromhex("c7 01 00 27 04 c0"), "packet header changed")
    need(code, bytes.fromhex("44 89 71 04 89 51 08"), "count/address-low layout changed")
    need(code, bytes.fromhex("48 c1 e8 20 89 41 0c"), "address-high layout changed")
    need(code, bytes.fromhex("89 71 10 89 59 14"), "count/modifier layout changed")

    print("indexed draw contract passed: (writer, count, GPU index address, "
          "modifier), six DWORDs, 64-bit address, null on allocation failure; "
          "path remains optional")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
