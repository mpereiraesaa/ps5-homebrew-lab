#!/usr/bin/env python3
"""Binary/source gate for phase 0R. This verifier never contacts a PS5."""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path


SOURCE = Path("legacy/probes/ps5-agc-phase0/driver_batch_first_submit.c")
ELF = Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0r-batch-first-submit.elf")
MAKEFILE = Path("legacy/probes/ps5-agc-phase0/Makefile")
SUPERVISOR = Path("tools/night_supervisor.py")
OUTPUT = Path("research/gpu/captures/agc-phase0r-draft-safety.json")

source = SOURCE.read_text()
elf = ELF.read_bytes()
makefile = MAKEFILE.read_text()
supervisor = SUPERVISOR.read_text()
required = (
    "stage_a_batch_open(&mapping, &api)",
    "STAGE_A_BATCH_PROTECTION 0x0cf2",
    "const uint32_t stream[15]",
    "0xc0055000, 0xc0300000",
    "0xc0064900, 0x06000528, 0x42010000",
    "__atomic_thread_fence(__ATOMIC_SEQ_CST)",
    "submit_started = 1",
    "GPU ownership complete fence=0 target=0",
    "PARKED_PHASE0R",
    "DO_NOT_CLOSE_FAKE00000",
)
# The protection constant lives in the included lifecycle header.
combined = source + Path("legacy/probes/ps5-agc-phase0/stage_a_batch_mapping.h").read_text()
missing = [item for item in required if item not in combined]
if missing:
    raise SystemExit(f"phase 0R source contract missing: {missing}")
all_recipe = makefile.split("all:", 1)[1].split("\n\n", 1)[0]
if "phase0r" in all_recipe:
    raise SystemExit("phase 0R entered the default build")
if "require_phase0r_cleanup_safe" not in supervisor or \
        "classify_phase0r_log" not in supervisor:
    raise SystemExit("phase 0R cleanup-refusal guard is not integrated")
supervisor_contract = (
    '"run-phase0r-first-submit"',
    "def run_phase0r_first_submit(self, operator_present: bool,",
    "if not operator_present:",
    "confirmed_sha256 != PHASE0R_SHA256",
    "candidate != old_log",
    "self.require_phase0r_cleanup_safe(log)",
    'self.checked_close("FAKE00000")',
    "completion_proven=decision[\"completion_proven\"]",
)
missing_supervisor = [item for item in supervisor_contract if item not in supervisor]
if missing_supervisor:
    raise SystemExit(f"phase 0R supervisor contract missing: {missing_supervisor}")
elf_sha256 = hashlib.sha256(elf).hexdigest()
if f'PHASE0R_SHA256 = "{elf_sha256}"' not in supervisor:
    raise SystemExit("phase 0R supervisor hash differs from audited binary")

symbols = subprocess.check_output(["readelf", "-Ws", str(ELF)], text=True)
undefined = sorted({line.split()[-1] for line in symbols.splitlines()
                    if " UND " in f" {line} " and line.split()[-1] != "UND"})
forbidden = [name for name in undefined if "VideoOut" in name]
if forbidden:
    raise SystemExit(f"phase 0R unexpectedly imports VideoOut: {forbidden}")
if "sceKernelBatchMap" not in undefined:
    raise SystemExit("phase 0R lacks BatchMap import")
if b"UglJIZjGssM" not in elf or b"libSceAgcDriver.sprx" not in elf:
    raise SystemExit("phase 0R lacks pinned submit identity")

def require_text(virtual: int, expected: bytes, label: str) -> None:
    actual = elf[0x4000 + virtual:0x4000 + virtual + len(expected)]
    if actual != expected:
        raise SystemExit(f"{label} mismatch at text+{virtual:#x}")

require_text(0x4FE, bytes.fromhex("c4c1781106"), "DMA prefix store")
require_text(0x503, bytes.fromhex("41895e10"), "target-low store")
require_text(0x507, bytes.fromhex("41894614"), "target-high store")
require_text(0x50B, bytes.fromhex("c4c17a7f4e18"), "packet join store")
require_text(0x511, bytes.fromhex("45896e28"), "fence-low store")
require_text(0x515, bytes.fromhex("41894e2c"), "fence-high store")
require_text(0x519, bytes.fromhex("49c7463000000000"), "fence tail zero")
require_text(0x529, bytes.fromhex("41c786001000005a5aa5a5"), "target canary")
require_text(0x534, bytes.fromhex("49c7860810000001000000"), "fence initial one")
require_text(0x577, bytes.fromhex("48c78568ffffff0f000000"), "submit size and field")
require_text(0x589, bytes.fromhex("0faef0"), "pre-submit MFENCE")
require_text(0x58C, bytes.fromhex("48c705893a010001000000"), "submit-started store")
if elf.count(struct.pack("<4I", 0xC0055000, 0xC0300000, 0, 0)) != 1:
    raise SystemExit("DMA prefix is missing or ambiguous")
if elf.count(struct.pack("<4I", 4, 0xC0064900, 0x06000528, 0x42010000)) != 1:
    raise SystemExit("DMA/fence join is missing or ambiguous")

result = {
    "schema": 1,
    "firmware_scope": "12.02",
    "source": str(SOURCE),
    "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
    "elf": str(ELF),
    "elf_sha256": elf_sha256,
    "elf_bytes": len(elf),
    "mapping_policy": "owned type=0x0c BatchMap prot=0x0cf2",
    "mapping_policy_runtime_accepted_by_phase0q": True,
    "stream_dwords": 15,
    "target_bytes": 4,
    "ownership_fence_initial": 1,
    "ownership_fence_final": 0,
    "binary_stream_and_ordering_pinned": True,
    "videoout_used": False,
    "console_contacted": False,
    "deployed": False,
    "executed": False,
    "approved_for_deployment": False,
    "default_build": False,
    "timeout_policy": "park and retain all post-submit resources",
    "supervisor_cleanup_refusal_gate_present": True,
    "supervisor_action_present": True,
    "supervisor_requires_operator_presence": True,
    "supervisor_requires_exact_artifact_sha256": True,
    "supervisor_rejects_stale_log": True,
    "undefined_symbols": undefined,
}
OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
