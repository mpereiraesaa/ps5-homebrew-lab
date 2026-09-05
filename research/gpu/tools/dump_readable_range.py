#!/usr/bin/env python3
"""Dump one explicitly bounded readable range from a uniquely named process."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "rehd_mods"))
from ps5debug import PS5Debug  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--process", required=True)
    p.add_argument("--start", required=True, type=lambda x: int(x, 0))
    p.add_argument("--end", required=True, type=lambda x: int(x, 0))
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    if args.end <= args.start or args.end - args.start > 0x4000000:
        raise SystemExit("range must be positive and no larger than 64 MiB")

    with PS5Debug(args.host, 744, 60) as dbg:
        procs = [x for x in dbg.get_process_list() if x.name == args.process]
        if len(procs) != 1:
            raise SystemExit("process name is not unique")
        proc = procs[0]
        maps = dbg.get_process_maps(proc.pid)
        mapping = next((m for m in maps if "r" in m.perms and
                        m.start <= args.start < args.end <= m.end), None)
        if mapping is None:
            raise SystemExit("range is not wholly contained in one readable mapping")
        data = bytearray()
        address = args.start
        while address < args.end:
            size = min(0x100000, args.end - address)
            data.extend(dbg.read_memory(proc.pid, address, size))
            address += size

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    manifest = {
        "schema": 1, "process": args.process, "pid": proc.pid,
        "start": hex(args.start), "end": hex(args.end), "size": len(data),
        "mapping_name": mapping.name, "mapping_perms": mapping.perms,
        "sha256": hashlib.sha256(data).hexdigest(),
        "target_writes": 0, "debugger_attach": False, "remote_calls": 0,
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
