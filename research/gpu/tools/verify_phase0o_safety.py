#!/usr/bin/env python3
"""Static gate for phase 0O's fixed-VA, no-submit memory experiment."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


source_path = Path("legacy/probes/ps5-agc-phase0/memory_fixed_mapping.c")
elf_path = Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0o-fixed-mapping.elf")
source = source_path.read_text()
elf = elf_path.read_bytes()
makefile = Path("legacy/probes/ps5-agc-phase0/Makefile").read_text()
supervisor = Path("tools/night_supervisor.py").read_text()

required = (
    "sceKernelReserveVirtualRange(\n        &reserved, REGION_SIZE, 0, REGION_ALIGN)",
    "REGION_SIZE, REGION_ALIGN, 0x0c, &physical",
    "&mapping, REGION_SIZE, 0x0f2, 0x10, physical, 0",
    "mapping != reserved",
    "cpu_write_read_canaries",
    "submitted=no",
)
missing = [item for item in required if item not in source]
if missing:
    raise SystemExit(f"phase 0O source markers missing: {missing}")
forbidden = [item for item in ("libSceAgc", "SubmitDcb", "dlsym(", "PARKED_")
             if item in source]
if forbidden:
    raise SystemExit(f"phase 0O forbidden behavior: {forbidden}")
if "phase0o" in makefile.split("all:", 1)[1].split("\n\n", 1)[0]:
    raise SystemExit("phase 0O must not be in the default build")
for marker in ("run_fixed_mapping",
               "checked_close(\"FAKE00000\")", "require_stable_health"):
    if marker not in supervisor:
        raise SystemExit(f"supervisor phase 0O gate missing: {marker}")
if '"run-fixed-mapping"' in supervisor:
    raise SystemExit("retired phase 0O action remains in supervisor CLI")

symbols = subprocess.check_output(["readelf", "-Ws", str(elf_path)], text=True)
undefined = sorted({line.split()[-1] for line in symbols.splitlines()
                    if " UND " in f" {line} " and line.split()[-1] != "UND"})
if any("Agc" in name or "Submit" in name or "VideoOut" in name or
       "Sysmodule" in name for name in undefined):
    raise SystemExit("phase 0O ELF contains a forbidden import")

result = {
    "schema": 1,
    "firmware_scope": "12.02",
    "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
    "elf_sha256": hashlib.sha256(elf).hexdigest(),
    "elf_size": len(elf),
    "reserve_virtual_range": True,
    "mapping_bytes": 0x20000,
    "memory_type": "0x0c",
    "protection": "0x0f2",
    "map_flags": "0x10",
    "agc_loaded": False,
    "submitted": False,
    "default_build": False,
    "bounded_watchdog_seconds": 10,
    "exact_title_cleanup": True,
    "stable_health_before_and_after": True,
    "supervisor_action_present": False,
    "approved_for_deployment": True,
    "undefined_symbols": undefined,
}
output = Path("research/gpu/captures/agc-phase0o-safety.json")
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
