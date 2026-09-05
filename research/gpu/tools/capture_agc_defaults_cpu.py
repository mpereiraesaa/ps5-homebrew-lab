#!/usr/bin/env python3
"""Bounded, read-only parser for the live AGC RegisterDefaults table."""

from __future__ import annotations

import argparse
import ftplib
import hashlib
import json
import re
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "rehd_mods"))
from ps5debug import PS5Debug  # noqa: E402

TITLE_ID = "PPSA99998"
LOG_PATH = "/mnt/sandbox/PPSA99998_000/download0/agc-native-sce-phase0.log"
MAX_RECORDS = 4096
ROOT_SIZE = 0x40
TYPE_RECORD_SIZE = 8
POINTER_SIZE = 8


class ParseError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def containing_map(maps, address: int, size: int):
    hits = [m for m in maps
            if "r" in m.perms and m.start <= address and address + size <= m.end]
    if len(hits) != 1:
        raise ParseError(
            f"range {address:#x}+{size:#x} is not in exactly one readable map"
        )
    return hits[0]


def read_checked(dbg, pid: int, maps, address: int, size: int) -> tuple[bytes, object]:
    if size <= 0:
        raise ParseError("zero/negative read refused")
    mapping = containing_map(maps, address, size)
    return dbg.read_memory(pid, address, size), mapping


def decode_type_records(data: bytes, count: int) -> tuple[list[tuple[int, int]], dict[int, list[int]]]:
    if count <= 0 or count > MAX_RECORDS:
        raise ParseError(f"count outside 1..{MAX_RECORDS}: {count}")
    if len(data) != count * TYPE_RECORD_SIZE:
        raise ParseError("type table size does not match count")
    records = [struct.unpack_from("<II", data, i * TYPE_RECORD_SIZE)
               for i in range(count)]
    keys = [key for key, _ in records]
    if len(set(keys)) != len(keys):
        raise ParseError("duplicate type key")
    by_bank: dict[int, list[int]] = {0: [], 1: [], 2: []}
    for _, encoded in records:
        bank = encoded & 3
        index = encoded >> 2
        if bank not in by_bank:
            raise ParseError(f"unsupported bank selector: {bank}")
        by_bank[bank].append(index)
    for bank, name in enumerate(("cx", "sh", "uc")):
        indices = by_bank[bank]
        expected = list(range(len(indices)))
        if indices != expected:
            raise ParseError(f"{name} indices are not unique contiguous ordered values")
    return records, by_bank


def decode_pointer_table(data: bytes, count: int, maps) -> list[int]:
    if count <= 0 or count > MAX_RECORDS:
        raise ParseError(f"pointer count outside 1..{MAX_RECORDS}: {count}")
    if len(data) != count * POINTER_SIZE:
        raise ParseError("pointer table size does not match count")
    pointers = list(struct.unpack(f"<{count}Q", data))
    if any(pointer == 0 or pointer % 8 != 0 for pointer in pointers):
        raise ParseError("pointer table contains null or unaligned pointer")
    for pointer in pointers:
        containing_map(maps, pointer, 8)
    return pointers


def root_from_log(host: str) -> int:
    with ftplib.FTP() as ftp:
        ftp.connect(host, 2121, 8)
        ftp.login()
        data = bytearray()
        ftp.retrbinary(f"RETR {LOG_PATH}", data.extend)
    log = bytes(data).decode("utf-8", "strict")
    required = ("agc_load=0x00000000", "agc_init=0x00000000",
                "phase2 pointer captured; parked-safe")
    if not all(item in log for item in required):
        raise ParseError("phase-2 safe marker is incomplete")
    match = re.search(r"register_defaults_ptr=0x([0-9a-fA-F]{16})", log)
    if not match or int(match.group(1), 16) == 0:
        raise ParseError("non-null defaults pointer missing")
    return int(match.group(1), 16)


def parse(host: str) -> dict[str, object]:
    root_address = root_from_log(host)
    with PS5Debug(host, 744, 15) as dbg:
        candidates = []
        for proc in dbg.get_process_list():
            if proc.name == "eboot.bin":
                info = dbg.get_process_info(proc.pid)
                if info.titleid == TITLE_ID:
                    candidates.append(proc.pid)
        if len(candidates) != 1:
            raise ParseError(f"expected one {TITLE_ID} process, got {len(candidates)}")
        pid = candidates[0]
        maps = dbg.get_process_maps(pid)
        root, root_map = read_checked(dbg, pid, maps, root_address, ROOT_SIZE)
        qwords = struct.unpack("<8Q", root)
        banks = qwords[:4]
        types_address = qwords[6]
        count = qwords[7] & 0xFFFFFFFF
        reserved_3c = qwords[7] >> 32
        if count == 0 or count > MAX_RECORDS:
            raise ParseError(f"count outside 1..{MAX_RECORDS}: {count}")
        if banks[3] != 0 or reserved_3c != 0:
            raise ParseError("table_3/reserved_3c invariant failed")

        types, types_map = read_checked(
            dbg, pid, maps, types_address, count * TYPE_RECORD_SIZE
        )
        records, by_bank = decode_type_records(types, count)
        keys = [key for key, _ in records]

        bank_summaries = []
        pointer_targets: list[int] = []
        for bank, name in enumerate(("cx", "sh", "uc")):
            indices = by_bank[bank]
            pointer_bytes, pointer_map = read_checked(
                dbg, pid, maps, banks[bank], len(indices) * POINTER_SIZE
            )
            pointers = decode_pointer_table(pointer_bytes, len(indices), maps)
            pointer_targets.extend(pointers)
            bank_summaries.append({
                "bank": bank,
                "name": name,
                "entries": len(indices),
                "index_min": indices[0] if indices else None,
                "index_max": indices[-1] if indices else None,
                "pointer_table_map": pointer_map.name,
                "pointer_table_permissions": pointer_map.perms,
                "pointer_table_sha256": sha(pointer_bytes),
                "target_min": hex(min(pointers)),
                "target_max": hex(max(pointers)),
                "targets_strictly_increasing": all(
                    a < b for a, b in zip(pointers, pointers[1:])
                ),
            })

        if len(pointer_targets) != count:
            raise ParseError("sum of bank entries differs from count")

        return {
            "schema": 1,
            "title_id": TITLE_ID,
            "firmware": "12.02",
            "pid_ephemeral": pid,
            "layout_size": ROOT_SIZE,
            "count": count,
            "root_map": root_map.name,
            "root_permissions": root_map.perms,
            "root_sha256": sha(root),
            "types_map": types_map.name,
            "types_permissions": types_map.perms,
            "type_records": count,
            "type_table_sha256": sha(types),
            "unique_keys": len(set(keys)),
            "record_shape": "u32 key + u32 encoded_index",
            "termination_model": "count-delimited; no sentinel",
            "table_3_null": True,
            "banks": bank_summaries,
            "invariants": {
                "count_equals_bank_entry_sum": True,
                "indices_unique_contiguous_ordered_per_bank": True,
                "all_pointers_non_null_aligned_readable": True,
            },
            "safety": {
                "debugger_attach": False,
                "writes": 0,
                "remote_calls": 0,
                "shader_calls": 0,
                "queue_or_dcb_calls": 0,
                "submits": 0,
                "videoout_calls": 0,
                "raw_tables_emitted": False,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = parse(args.host)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
