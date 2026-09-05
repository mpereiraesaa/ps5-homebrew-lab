#!/usr/bin/env python3
"""Find aligned pointers from selected process maps into a mapped module."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "rehd_mods"))
from ps5debug import PS5Debug  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--process", required=True)
    parser.add_argument("--target-module", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-map", action="append", default=[],
                        help="scan only mappings with this exact name (repeatable)")
    parser.add_argument("--max-map-size", type=lambda x: int(x, 0), default=0x4000000)
    parser.add_argument("--chunk-size", type=lambda x: int(x, 0), default=0x100000)
    args = parser.parse_args()

    with PS5Debug(args.host, 744, 60) as dbg:
        proc = next((p for p in dbg.get_process_list() if p.name == args.process), None)
        if proc is None:
            raise SystemExit("process not found")
        maps = dbg.get_process_maps(proc.pid)
        targets = [m for m in maps if m.name == args.target_module and "x" in m.perms]
        if not targets:
            raise SystemExit("executable target module mapping not found")
        target_start = min(m.start for m in targets)
        target_end = max(m.end for m in targets)
        hits = []
        scanned = []
        for mapping in maps:
            if "r" not in mapping.perms or "x" in mapping.perms:
                continue
            if args.source_map and mapping.name not in args.source_map:
                continue
            if not mapping.name or mapping.size > args.max_map_size:
                continue
            if any(word in mapping.name.lower() for word in ("garlic", "gpu", "dumparea")):
                continue
            address = mapping.start
            carry = b""
            while address < mapping.end:
                size = min(args.chunk_size, mapping.end - address)
                block = dbg.read_memory(proc.pid, address, size)
                data = carry + block
                data_base = address - len(carry)
                first = (-data_base) & 7
                for offset in range(first, len(data) - 7, 8):
                    value = struct.unpack_from("<Q", data, offset)[0]
                    if target_start <= value < target_end:
                        hits.append({
                            "slot": hex(data_base + offset),
                            "target": hex(value),
                            "target_offset": hex(value - target_start),
                            "source_map": mapping.name,
                            "source_perms": mapping.perms,
                        })
                carry = data[-7:]
                address += size
            scanned.append({"name": mapping.name, "start": hex(mapping.start),
                            "end": hex(mapping.end), "perms": mapping.perms})

    result = {
        "schema": 1, "process": args.process, "pid": proc.pid,
        "target_module": args.target_module,
        "target_executable_start": hex(target_start),
        "target_executable_end": hex(target_end),
        "hits": hits, "scanned_maps": scanned,
        "target_writes": 0, "debugger_attach": False, "remote_calls": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"found {len(hits)} aligned pointers into {args.target_module}")
    for hit in hits:
        print(hit["slot"], "->", hit["target"],
              f"({hit['target_offset']})", hit["source_map"])


if __name__ == "__main__":
    main()
