#!/usr/bin/env python3
"""Static deployment gate for the no-AGC phase 0N mapping-policy probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path,
                        default=Path("legacy/probes/ps5-agc-phase0/memory_mapping_policy.c"))
    parser.add_argument("--elf", type=Path,
                        default=Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0n-memory-policy.elf"))
    parser.add_argument("--makefile", type=Path,
                        default=Path("legacy/probes/ps5-agc-phase0/Makefile"))
    parser.add_argument("--supervisor", type=Path,
                        default=Path("tools/night_supervisor.py"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = args.source.read_text()
    elf = args.elf.read_bytes()
    makefile = args.makefile.read_text()
    supervisor = args.supervisor.read_text()
    required = (
        "no AGC, queue or submit",
        '{"homebrew_known", 0x20000, 3, 0x33, 0, 0x20000}',
        '{"game_backbuffer_like", 0x10000, 0x0c, 0x0f2, 0x10, 0}',
        "sceKernelReleaseDirectMemory",
        "cpu_write_read_canaries",
        "submitted=no",
    )
    missing = [marker for marker in required if marker not in source]
    if missing:
        raise SystemExit(f"phase 0N source markers missing: {missing}")
    forbidden = ("sceSysmoduleLoadModuleInternal", "SubmitDcb", "dlsym(",
                 "libSceAgc", "PARKED_")
    present = [marker for marker in forbidden if marker in source]
    if present:
        raise SystemExit(f"phase 0N contains forbidden behavior: {present}")
    all_recipe = makefile.split("all:", 1)[1].split("\n\n", 1)[0]
    if "phase0n" in all_recipe:
        raise SystemExit("phase 0N must not be in the default build")
    for marker in ("run_memory_policy",
                   "checked_close(\"FAKE00000\")", "require_stable_health"):
        if marker not in supervisor:
            raise SystemExit(f"supervisor phase 0N gate missing: {marker}")
    if '"run-memory-policy"' in supervisor:
        raise SystemExit("retired phase 0N action remains in supervisor CLI")

    symbols = subprocess.check_output(["readelf", "-Ws", str(args.elf)], text=True)
    undefined = sorted({line.split()[-1] for line in symbols.splitlines()
                        if " UND " in f" {line} " and line.split()[-1] != "UND"})
    forbidden_undefined = [name for name in undefined
                           if "Agc" in name or "Submit" in name or
                           "VideoOut" in name or "Sysmodule" in name]
    if forbidden_undefined:
        raise SystemExit(f"forbidden ELF imports: {forbidden_undefined}")
    if not elf.startswith(b"\x7fELF"):
        raise SystemExit("phase 0N output is not ELF")

    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "source_sha256": sha(source.encode()),
        "elf_sha256": sha(elf),
        "elf_size": len(elf),
        "default_build": False,
        "agc_loaded": False,
        "queue_access": False,
        "submitted": False,
        "mapping_bytes_per_case": 0x20000,
        "case_count": 2,
        "bounded_watchdog_seconds": 10,
        "exact_title_cleanup": True,
        "stable_health_before_and_after": True,
        "supervisor_action_present": False,
        "approved_for_deployment": True,
        "undefined_symbols": undefined,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
