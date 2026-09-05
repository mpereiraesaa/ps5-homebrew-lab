#!/usr/bin/env python3
"""Static gate for phase 0P's bounded, read-only backend-state probe."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path

source_path = Path("legacy/probes/ps5-agc-phase0/driver_backend_state.c")
elf_path = Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0p-backend-state.elf")
source = source_path.read_text(); elf = elf_path.read_bytes()
makefile = Path("legacy/probes/ps5-agc-phase0/Makefile").read_text()
supervisor = Path("tools/night_supervisor.py").read_text()
required = (
    "STATE_OFFSET UINT64_C(0x22908)", "READY_OFFSET (STATE_OFFSET + UINT64_C(0x08))",
    "CALLBACK_OFFSET (STATE_OFFSET + UINT64_C(0x50))",
    "SELECTOR_OFFSET (STATE_OFFSET + UINT64_C(0x120))",
    "callback == (uint64_t)(base + GRAPHICS_BACKEND_OFFSET)",
    "writes=0; submitted=no",
)
missing = [x for x in required if x not in source]
if missing: raise SystemExit(f"phase 0P source markers missing: {missing}")
forbidden = [x for x in ("dlsym(", "SubmitDcb", "CreateQueue(", "sceKernelWrite", "PARKED_") if x in source]
if forbidden: raise SystemExit(f"phase 0P forbidden behavior: {forbidden}")
if "phase0p" in makefile.split("all:",1)[1].split("\n\n",1)[0]:
    raise SystemExit("phase 0P must not be in default build")
for marker in ("run_backend_state", 'checked_close("FAKE00000")', "require_stable_health"):
    if marker not in supervisor: raise SystemExit(f"supervisor phase 0P gate missing: {marker}")
symbols = subprocess.check_output(["readelf","-Ws",str(elf_path)], text=True)
undefined = sorted({line.split()[-1] for line in symbols.splitlines() if " UND " in f" {line} " and line.split()[-1] != "UND"})
if any("Agc" in x or "Submit" in x or "VideoOut" in x for x in undefined):
    raise SystemExit("phase 0P ELF contains forbidden imports")
result = {
    "schema":1, "firmware_scope":"12.02",
    "source_sha256":hashlib.sha256(source.encode()).hexdigest(),
    "elf_sha256":hashlib.sha256(elf).hexdigest(), "elf_size":len(elf),
    "read_offsets":["0x22910","0x22958","0x22a28"], "data_bytes_read":16,
    "code_reads":False, "queue_calls":False, "writes":False, "submitted":False,
    "default_build":False, "bounded_watchdog_seconds":10,
    "exact_title_cleanup":True, "stable_health_before_and_after":True,
    "approved_for_single_execution":False, "retired_after_single_execution":True,
    "undefined_symbols":undefined,
}
Path("research/gpu/captures/agc-phase0p-safety.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
print(json.dumps(result,indent=2,sort_keys=True))
