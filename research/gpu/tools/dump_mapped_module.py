#!/usr/bin/env python3
"""Read-only dump of one exactly named mapped module with a JSON manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "rehd_mods"))
from ps5debug import PS5Debug  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=744)
    parser.add_argument("--process", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--chunk-size", type=lambda x: int(x, 0), default=0x40000)
    args = parser.parse_args()
    if not 0x4000 <= args.chunk_size <= 0x100000:
        raise SystemExit("chunk size must be between 0x4000 and 0x100000")

    with PS5Debug(args.host, args.port, 30) as dbg:
        candidates = [p for p in dbg.get_process_list() if p.name == args.process]
        if len(candidates) != 1:
            raise SystemExit(f"expected one process named {args.process!r}, got {len(candidates)}")
        proc = candidates[0]
        segments = [m for m in dbg.get_process_maps(proc.pid)
                    if m.name == args.module and "r" in m.perms]
        if not segments:
            raise SystemExit(f"no readable mappings named {args.module!r}")
        segments.sort(key=lambda m: m.start)
        base = segments[0].start
        end = max(m.end for m in segments)
        if end <= base or end - base > 0x10000000:
            raise SystemExit(f"refusing unexpected module span {base:#x}..{end:#x}")

        args.output.parent.mkdir(parents=True, exist_ok=True)
        records = []
        aggregate = hashlib.sha256()
        with args.output.open("wb") as output:
            output.truncate(end - base)
            for segment in segments:
                digest = hashlib.sha256()
                output.seek(segment.start - base)
                address = segment.start
                while address < segment.end:
                    size = min(args.chunk_size, segment.end - address)
                    block = dbg.read_memory(proc.pid, address, size)
                    if len(block) != size:
                        raise SystemExit(f"short read at {address:#x}")
                    output.write(block)
                    digest.update(block)
                    aggregate.update(block)
                    address += size
                records.append({
                    "start": hex(segment.start), "end": hex(segment.end),
                    "offset": hex(segment.offset), "size": segment.size,
                    "perms": segment.perms, "sha256": digest.hexdigest(),
                })

    manifest = {
        "schema": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "process_name": args.process,
        "pid": proc.pid,
        "module_name": args.module,
        "base": hex(base),
        "end": hex(end),
        "sparse_image_size": end - base,
        "readable_bytes_sha256": aggregate.hexdigest(),
        "segments": records,
        "target_writes": 0,
        "debugger_attach": False,
        "remote_calls": 0,
    }
    manifest_path = args.output.with_suffix(args.output.suffix + ".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
