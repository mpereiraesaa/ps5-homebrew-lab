#!/usr/bin/env python3
"""Source/binary/supervisor gate for phase 0S; never contacts the console."""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path


SOURCE = Path("legacy/probes/ps5-agc-phase0/driver_batch_fence_submit.c")
ELF = Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0s-batch-fence-submit.elf")
MAKEFILE = Path("legacy/probes/ps5-agc-phase0/Makefile")
SUPERVISOR = Path("tools/night_supervisor.py")
OUTPUT = Path("research/gpu/captures/agc-phase0s-draft-safety.json")

source = SOURCE.read_text()
elf = ELF.read_bytes()
makefile = MAKEFILE.read_text()
supervisor = SUPERVISOR.read_text()
header = Path("legacy/probes/ps5-agc-phase0/stage_a_batch_mapping.h").read_text()
required = (
    "stage_a_batch_open(&mapping, &api)",
    "STAGE_A_BATCH_PROTECTION 0x0cf2",
    "const uint32_t stream[8]",
    "0xc0064900, 0x06000528, 0x42010000",
    "struct submit_info info = {(const uint32_t *)b, 8, 0",
    "__atomic_thread_fence(__ATOMIC_SEQ_CST)",
    "submit_started = 1",
    "GPU ownership complete fence=0",
    "PARKED_PHASE0S",
    "DO_NOT_CLOSE_FAKE00000",
)
missing = [item for item in required if item not in source + header]
if missing:
    raise SystemExit(f"phase 0S source contract missing: {missing}")
if "0xc0055000" in source:
    raise SystemExit("phase 0S is not isolated from DMA_DATA/target state")
all_recipe = makefile.split("all:", 1)[1].split("\n\n", 1)[0]
if "phase0s" in all_recipe:
    raise SystemExit("phase 0S entered the default build")

elf_sha = hashlib.sha256(elf).hexdigest()
contract = (
    "classify_phase0s_log", "require_phase0s_cleanup_safe",
    '"run-phase0s-fence-submit"', "if not operator_present:",
    "confirmed_sha256 != PHASE0S_SHA256", "candidate != old_log",
    'self.checked_close("FAKE00000")',
)
missing = [item for item in contract if item not in supervisor]
if missing:
    raise SystemExit(f"phase 0S supervisor contract missing: {missing}")
if f'PHASE0S_SHA256 = "{elf_sha}"' not in supervisor:
    raise SystemExit("phase 0S supervisor hash differs from audited ELF")

symbols = subprocess.check_output(["readelf", "-Ws", str(ELF)], text=True)
undefined = sorted({line.split()[-1] for line in symbols.splitlines()
                    if " UND " in f" {line} " and line.split()[-1] != "UND"})
if any("VideoOut" in name for name in undefined):
    raise SystemExit("phase 0S unexpectedly imports VideoOut")
if "sceKernelBatchMap" not in undefined:
    raise SystemExit("phase 0S lacks BatchMap")
if b"UglJIZjGssM" not in elf or b"libSceAgcDriver.sprx" not in elf:
    raise SystemExit("phase 0S lacks pinned submit identity")
packed_header_event = struct.pack("<Q", 0x06000528C0064900)
packed_control_store = bytes.fromhex("41c7460800000142")
if elf.count(packed_header_event) != 1 or elf.count(packed_control_store) != 1:
    raise SystemExit("ownership RELEASE_MEM stores are missing or ambiguous")
if elf.count(bytes.fromhex("0faef0")) != 1:
    raise SystemExit("pre-submit MFENCE is missing or ambiguous")

result = {
    "schema": 1, "firmware_scope": "12.02",
    "source": str(SOURCE), "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
    "elf": str(ELF), "elf_sha256": elf_sha, "elf_bytes": len(elf),
    "mapping_policy": "owned type=0x0c BatchMap prot=0x0cf2",
    "stream_dwords": 8, "dma_data_used": False,
    "ownership_fence_initial": 1, "ownership_fence_final": 0,
    "binary_stream_and_ordering_pinned": True, "videoout_used": False,
    "console_contacted": False, "deployed": False, "executed": False,
    "approved_for_deployment": True, "default_build": False,
    "timeout_policy": "park and retain all post-submit resources",
    "operator_presence_required": True, "exact_sha_required": True,
    "undefined_symbols": undefined,
}
OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
