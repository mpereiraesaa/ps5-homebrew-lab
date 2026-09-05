#!/usr/bin/env python3
"""Capture a read-only ps5debug-NG process/map inventory as JSON."""

from __future__ import annotations

import argparse
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
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--foreground-only", action="store_true",
                        help="capture maps only for the current foreground PID")
    parser.add_argument("--title-id",
                        help="capture maps only for processes with this exact title ID")
    args = parser.parse_args()

    with PS5Debug(args.host, args.port, args.timeout) as dbg:
        version = dbg.get_version()
        branding = dbg.get_branding().split("\0", 1)[0]
        foreground = dbg.get_foreground_app()
        processes = dbg.get_process_list()
        if args.foreground_only:
            processes = [proc for proc in processes if proc.pid == foreground.pid]
        if args.title_id:
            selected = []
            for proc in processes:
                try:
                    info = dbg.get_process_info(proc.pid)
                except Exception:
                    continue
                if info.titleid == args.title_id:
                    selected.append(proc)
            processes = selected
        records = []
        for proc in processes:
            try:
                maps = dbg.get_process_maps(proc.pid)
            except Exception as exc:  # preserve partial inventory
                records.append({
                    "name": proc.name,
                    "pid": proc.pid,
                    "maps_error": type(exc).__name__,
                    "maps": [],
                })
                continue
            records.append({
                "name": proc.name,
                "pid": proc.pid,
                "maps": [{
                    "name": entry.name,
                    "start": hex(entry.start),
                    "end": hex(entry.end),
                    "size": entry.size,
                    "perms": entry.perms,
                    "offset": hex(entry.offset),
                } for entry in maps],
            })

    result = {
        "schema": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "debugger_protocol": version,
        "debugger_branding": branding,
        "foreground": {
            "pid": foreground.pid,
            "name": foreground.name,
            "title_id": foreground.titleid,
            "app_version": foreground.app_ver,
        },
        "processes": records,
        "target_writes": 0,
        "debugger_attach": False,
        "remote_calls": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"captured {len(records)} processes -> {args.output}")


if __name__ == "__main__":
    main()
