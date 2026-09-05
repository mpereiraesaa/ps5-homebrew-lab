#!/usr/bin/env python3
"""Find x86-64 RIP-relative references to selected runtime pointer slots."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def parse_int(value: str) -> int:
    return int(value, 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("pointers", type=Path)
    parser.add_argument("--source-map", default="executable")
    parser.add_argument("--target-module", default="libSceAgc.sprx")
    parser.add_argument("--slot-start", type=parse_int)
    parser.add_argument("--slot-end", type=parse_int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    pointer_data = json.loads(args.pointers.read_text())
    dump_base = int(manifest["base"], 0)
    blob = args.dump.read_bytes()

    slots = {}
    for hit in pointer_data["hits"]:
        if hit["source_map"] != args.source_map:
            continue
        slot = int(hit["slot"], 0)
        if args.slot_start is not None and slot < args.slot_start:
            continue
        if args.slot_end is not None and slot >= args.slot_end:
            continue
        slots[slot] = hit

    executable_regions = [
        region for region in manifest["segments"] if "x" in region["perms"]
    ]
    refs = []
    # Import thunks use CALL/JMP qword ptr [RIP+disp32]: FF /2 and FF /4.
    # MOV/LEA references are recorded too because engines sometimes cache imports.
    forms = ((b"\xff\x15", "call", 6), (b"\xff\x25", "jmp", 6),
             (b"\x48\x8b\x05", "mov_rax", 7), (b"\x48\x8d\x05", "lea_rax", 7))
    for region in executable_regions:
        start = int(region["start"], 0)
        end = int(region["end"], 0)
        chunk = blob[start - dump_base:end - dump_base]
        for prefix, kind, insn_size in forms:
            position = 0
            while True:
                offset = chunk.find(prefix, position)
                if offset < 0:
                    break
                disp = struct.unpack_from("<i", chunk, offset + len(prefix))[0]
                site = start + offset
                slot = site + insn_size + disp
                if slot in slots:
                    target = int(slots[slot]["target"], 0)
                    refs.append({
                        "site": hex(site), "kind": kind, "slot": hex(slot),
                        "slot_index": (slot - min(slots)) // 8,
                        "target": hex(target),
                        "target_offset": slots[slot]["target_offset"],
                    })
                position = offset + 1

    refs.sort(key=lambda item: int(item["site"], 0))
    thunk_by_address = {
        int(ref["site"], 0): ref for ref in refs if ref["kind"] == "jmp"
    }
    callers = []
    for region in executable_regions:
        start = int(region["start"], 0)
        end = int(region["end"], 0)
        chunk = blob[start - dump_base:end - dump_base]
        position = 0
        while True:
            offset = chunk.find(b"\xe8", position)
            if offset < 0 or offset + 5 > len(chunk):
                break
            disp = struct.unpack_from("<i", chunk, offset + 1)[0]
            site = start + offset
            target = site + 5 + disp
            if target in thunk_by_address:
                thunk = thunk_by_address[target]
                callers.append({
                    "site": hex(site), "thunk": hex(target),
                    "slot": thunk["slot"], "target": thunk["target"],
                    "target_offset": thunk["target_offset"],
                })
            position = offset + 1
    callers.sort(key=lambda item: int(item["site"], 0))
    counts = {}
    for ref in refs:
        key = ref["slot"]
        counts[key] = counts.get(key, 0) + 1
    result = {
        "schema": 1,
        "dump": str(args.dump),
        "target_module": args.target_module,
        "slots": len(slots),
        "references": refs,
        "references_per_slot": counts,
        "callers": callers,
    }
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(f"{len(refs)} references across {len(counts)}/{len(slots)} slots")
    for ref in refs:
        print(ref["site"], ref["kind"], ref["slot"], "->", ref["target_offset"])
    caller_counts = {}
    for caller in callers:
        key = caller["target_offset"]
        caller_counts[key] = caller_counts.get(key, 0) + 1
    print(f"{len(callers)} direct CALLs into the import thunks")
    for target, count in sorted(caller_counts.items(), key=lambda item: -item[1]):
        print(target, count)


if __name__ == "__main__":
    main()
