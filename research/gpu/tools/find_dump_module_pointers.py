#!/usr/bin/env python3
"""Find aligned pointers in an offline runtime dump into another module."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def integer(value: str) -> int:
    return int(value, 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--target-start", type=integer, required=True)
    parser.add_argument("--target-end", type=integer, required=True)
    parser.add_argument("--target-module", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    base = int(manifest["base"], 0)
    blob = args.dump.read_bytes()
    hits = []
    scanned = []
    for segment in manifest["segments"]:
        if "r" not in segment["perms"] or "x" in segment["perms"]:
            continue
        start = int(segment["start"], 0)
        end = int(segment["end"], 0)
        scanned.append({"name": "executable", "start": hex(start),
                        "end": hex(end), "perms": segment["perms"]})
        for address in range((start + 7) & ~7, end, 8):
            offset = address - base
            if offset < 0 or offset + 8 > len(blob):
                continue
            value = struct.unpack_from("<Q", blob, offset)[0]
            if args.target_start <= value < args.target_end:
                hits.append({
                    "slot": hex(address), "target": hex(value),
                    "target_offset": hex(value - args.target_start),
                    "source_map": "executable", "source_perms": segment["perms"],
                })
    result = {
        "schema": 1, "source": "offline-runtime-dump",
        "dump": str(args.dump), "target_module": args.target_module,
        "target_executable_start": hex(args.target_start),
        "target_executable_end": hex(args.target_end),
        "hits": hits, "scanned_maps": scanned,
        "target_writes": 0, "debugger_attach": False, "remote_calls": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"found {len(hits)} aligned pointers into {args.target_module}")


if __name__ == "__main__":
    main()
