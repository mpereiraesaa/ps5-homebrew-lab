#!/usr/bin/env python3
"""Extract cross-validated raw AGC header/code pairs from authorized dumps."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path


MAGIC_VERSION = b"1234" + struct.pack("<I", 0x18)
EBOOT_BASE = 0x400000
SAN_SHA256 = "93749b4991d4b7a4536f7c5a85d31e3678443438bce800464955df4b03944066"
GAME_SHA256 = "d18dd54dea2f8b7364dfb7dfa48d2c8bb90d5959c3049215a1598ca32268921f"
SAN_HEADER_START = 0x62DC000
SAN_CODE_START = 0x62E0000
GAME_HEADER_START = 0x67FC000
GAME_CODE_START = 0x680C000
POINTER_FIELDS = (0x08, 0x18, 0x20, 0x28, 0x30, 0x38)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def find_headers(blob: bytes) -> list[int]:
    result: list[int] = []
    position = 0
    while True:
        position = blob.find(MAGIC_VERSION, position)
        if position < 0:
            return result
        result.append(position)
        position += 1


def u32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


def u64(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", blob, offset)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--san", type=Path,
                        default=Path("research/gpu/dumps/san-andreas-eboot-runtime.bin"))
    parser.add_argument("--cross-check", type=Path,
                        default=Path("research/gpu/dumps/game-eboot-runtime.bin"))
    parser.add_argument("--extract-dir", type=Path,
                        default=Path("research/gpu/shaders/san-andreas-authorized"))
    parser.add_argument("--output", type=Path,
                        default=Path("research/gpu/captures/agc-authorized-shader-pairs.json"))
    args = parser.parse_args()
    san = args.san.read_bytes()
    game = args.cross_check.read_bytes()
    if digest(san) != SAN_SHA256 or digest(game) != GAME_SHA256:
        raise SystemExit("authorized eboot hash mismatch")
    san_headers = find_headers(san)
    game_headers = find_headers(game)
    if len(san_headers) != 47 or len(game_headers) != 195:
        raise SystemExit("AGC header inventory count changed")
    if san_headers[0] != SAN_HEADER_START or game_headers[0] != GAME_HEADER_START:
        raise SystemExit("AGC header arena start changed")

    args.extract_dir.mkdir(parents=True, exist_ok=True)
    expected_names = {
        f"shader-{index:03d}.{suffix}.bin"
        for index in range(47) for suffix in ("header", "code")
    }
    stale = {path.name for path in args.extract_dir.iterdir() if path.is_file()} - expected_names
    if stale:
        raise SystemExit(f"unexpected stale shader artifacts: {sorted(stale)}")
    entries: list[dict[str, object]] = []
    san_code_cursor = SAN_CODE_START
    for index, (san_off, game_off) in enumerate(zip(san_headers, game_headers[:47])):
        if san_off - SAN_HEADER_START != game_off - GAME_HEADER_START:
            raise SystemExit(f"header {index}: cross-title relative offset differs")
        # Fields not modified by sceAgcCreateShader must match byte-for-byte.
        for field, size in ((0, 8), (0x40, 0x20)):
            if san[san_off + field:san_off + field + size] != \
               game[game_off + field:game_off + field + size]:
                raise SystemExit(f"header {index}: immutable field block differs")
        if u64(san, san_off + 0x10) != 0:
            raise SystemExit(f"header {index}: source header code field is bound")
        game_header_va = EBOOT_BASE + game_off
        for field in POINTER_FIELDS:
            relative = u64(san, san_off + field)
            relocated = u64(game, game_off + field)
            expected = game_header_va + field + relative if relative else 0
            if relocated != expected:
                raise SystemExit(f"header {index}: relocation mismatch at +{field:#x}")

        code_va = u64(game, game_off + 0x10)
        code_size = u32(game, game_off + 0x44)
        if code_va % 0x100 or code_size < 0x30:
            raise SystemExit(f"header {index}: invalid code alignment/size")
        game_code_off = code_va - EBOOT_BASE
        if not (0 <= game_code_off <= len(game) - code_size):
            raise SystemExit(f"header {index}: code outside capture")
        code = game[game_code_off:game_code_off + code_size]
        san_code_off = san.find(code, san_code_cursor)
        if san_code_off < san_code_cursor:
            raise SystemExit(f"header {index}: San Andreas code mismatch")
        if san_code_off % 0x100:
            raise SystemExit(f"header {index}: San Andreas code is misaligned")
        san_code_cursor = san_code_off + ((code_size + 0xFF) & ~0xFF)
        if code[-0x30:-0x28] != b"barefoot":
            raise SystemExit(f"header {index}: code footer missing")

        header_end = san_headers[index + 1] if index + 1 < 47 else SAN_CODE_START
        header = san[san_off:header_end]
        header_name = f"shader-{index:03d}.header.bin"
        code_name = f"shader-{index:03d}.code.bin"
        (args.extract_dir / header_name).write_bytes(header)
        (args.extract_dir / code_name).write_bytes(code)
        entries.append({
            "index": index,
            "type_raw": san[san_off + 0x5A],
            "stage_name_proven": False,
            "target_raw": u32(san, san_off + 0x4C),
            "num_sh_registers": san[san_off + 0x5C],
            "source_header_offset": hex(san_off),
            "source_code_offset": hex(san_code_off),
            "header_file": header_name,
            "header_bytes": len(header),
            "header_sha256": digest(header),
            "header_code_field_initially_null": True,
            "code_file": code_name,
            "code_bytes": len(code),
            "code_sha256": digest(code),
            "code_alignment_required": 0x100,
            "footer_barefoot": True,
        })

    type_counts = Counter(entry["type_raw"] for entry in entries)
    if type_counts != Counter({0: 31, 1: 15, 2: 1}):
        raise SystemExit(f"unexpected shader type inventory: {dict(type_counts)}")
    manifest = {
        "schema": 1,
        "firmware_scope": "12.02",
        "source": str(args.san),
        "source_sha256": digest(san),
        "cross_check_source": str(args.cross_check),
        "cross_check_sha256": digest(game),
        "console_contacted": False,
        "submitted_or_executed": False,
        "pairs_extracted": len(entries),
        "type_raw_counts": {str(k): v for k, v in sorted(type_counts.items())},
        "all_code_256_aligned_in_capture": True,
        "all_footers_verified": True,
        "all_self_relative_relocations_cross_checked": True,
        "all_code_cross_checked_between_captures": True,
        "constructor_input_header_form": "unrelocated mutable copy with code field null",
        "constructor_code_storage_requirement": "copy code to 256-byte-aligned retained GPU-visible memory",
        "stage_names_proven": False,
        "graphics_pair_selected": False,
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "entries"},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
