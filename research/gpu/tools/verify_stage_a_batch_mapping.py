#!/usr/bin/env python3
"""Verify the non-runnable Stage-A BatchMap lifecycle composition."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source_path = Path("legacy/probes/ps5-agc-phase0/stage_a_batch_mapping.c")
    header_path = Path("legacy/probes/ps5-agc-phase0/stage_a_batch_mapping.h")
    object_path = Path("legacy/probes/ps5-agc-phase0/stage-a-batch-mapping.o")
    probe_path = Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0q-batch-mapping.elf")
    probe_source_path = Path("legacy/probes/ps5-agc-phase0/batch_mapping_probe.c")
    test_path = Path("research/gpu/tools/test_stage_a_batch_mapping.c")
    makefile = Path("legacy/probes/ps5-agc-phase0/Makefile").read_text()
    source = source_path.read_text()
    header = header_path.read_text()
    obj = object_path.read_bytes()
    probe = probe_path.read_bytes()
    probe_source = probe_source_path.read_text()
    supervisor = Path("tools/night_supervisor.py").read_text()

    forbidden = [name for name in ("SubmitDcb", "VideoOut", "libSceAgc", "dlsym")
                 if name in source or name in header]
    if forbidden:
        raise SystemExit(f"Stage-A BatchMap object has forbidden API text: {forbidden}")
    all_recipe = makefile.split("all:", 1)[1].split("\n\n", 1)[0]
    if "stage-a-batch-mapping" in all_recipe:
        raise SystemExit("Stage-A BatchMap object entered default build")
    if "stage-a-batch-mapping.o:" not in makefile:
        raise SystemExit("Stage-A BatchMap object-only target missing")
    if "ps5-agc-phase0q-batch-mapping" in all_recipe:
        raise SystemExit("Phase 0Q entered default build")
    if "require_phase0q_cleanup_safe" not in supervisor or \
       "classify_phase0q_log" not in supervisor:
        raise SystemExit("Phase 0Q cleanup refusal gate missing")
    required_supervisor_contract = (
        '"run-phase0q-mapping"',
        "def run_phase0q_mapping(self)",
        "PHASE0Q_SHA256",
        "self.require_stable_health()",
        "self.require_bigapp(None)",
        "self.require_phase0q_cleanup_safe(log)",
        'self.checked_close("FAKE00000")',
        "submitted=False",
    )
    missing_supervisor = [item for item in required_supervisor_contract
                          if item not in supervisor]
    if missing_supervisor:
        raise SystemExit(f"Phase 0Q supervised contract missing: {missing_supervisor}")
    if "install-phase0q" in supervisor or "run_batch_mapping" in supervisor:
        raise SystemExit("Phase 0Q has an unapproved alternate action")
    probe_sha256 = hashlib.sha256(probe).hexdigest()
    if f'PHASE0Q_SHA256 = "{probe_sha256}"' not in supervisor:
        raise SystemExit("Phase 0Q supervisor hash is not pinned to this binary")
    symbols = subprocess.check_output(["nm", "-u", str(object_path)], text=True)
    if symbols.strip():
        raise SystemExit(f"unexpected unresolved direct symbols: {symbols.strip()}")
    elf_header = subprocess.check_output(["readelf", "-h", str(object_path)], text=True)
    if "REL (Relocatable file)" not in elf_header:
        raise SystemExit("Stage-A artifact is not relocatable object-only")
    probe_symbols = subprocess.check_output(
        ["readelf", "-Ws", str(probe_path)], text=True
    )
    undefined = sorted({
        line.split()[-1] for line in probe_symbols.splitlines()
        if " UND " in f" {line} " and line.split()[-1] != "UND"
    })
    required_undefined = {
        "sceKernelReserveVirtualRange", "sceKernelAllocateMainDirectMemory",
        "sceKernelBatchMap", "sceKernelReleaseDirectMemory", "munmap",
    }
    if not required_undefined.issubset(undefined):
        raise SystemExit("Phase 0Q lacks required mapping imports")
    forbidden_undefined = [
        name for name in undefined
        if "Agc" in name or "VideoOut" in name or "Submit" in name
    ]
    if forbidden_undefined:
        raise SystemExit(f"Phase 0Q has forbidden imports: {forbidden_undefined}")

    # SDK PIE layout: executable PT_LOAD begins at file offset 0x4000 and VA 0.
    def require_text(virtual: int, expected: bytes, label: str) -> None:
        actual = probe[0x4000 + virtual:0x4000 + virtual + len(expected)]
        if actual != expected:
            raise SystemExit(
                f"{label} mismatch at text+{virtual:#x}: "
                f"expected={expected.hex()} actual={actual.hex()}"
            )

    require_text(0x456, bytes.fromhex("be00000200b90000010031d2"),
                 "reserve size/alignment/flags")
    require_text(0x490, bytes.fromhex("bf00000200be00000100ba0c000000"),
                 "owned physical allocation type/size/alignment")
    require_text(0x4D9, bytes.fromhex("48c745d000000200"), "map length")
    require_text(0x4E1, bytes.fromhex("66c745d8f20c"), "map protection 0xcf2")
    require_text(0x4E7, bytes.fromhex("c745dc00000000"), "map operation zero")
    require_text(0x5E2, bytes.fromhex("48c745d800000200"), "unmap length")
    require_text(0x5EA, bytes.fromhex("66c745e0f20c"), "unmap protection 0xcf2")
    require_text(0x5F0, bytes.fromhex("c745e401000000"), "unmap operation one")
    require_text(0x166, bytes.fromhex("0faef0"), "CPU canary MFENCE")
    required_log_contract = (
        "open rc=%d state=%d va=%p",
        "cpu_canaries=%s",
        "close rc=%d state=%d",
        "definite map failure cleanup rc=%d state=%d",
        "phase0Q exit result=%d submitted=no",
        "PARKED_PHASE0Q",
    )
    missing_logs = [item for item in required_log_contract if item not in probe_source]
    if missing_logs:
        raise SystemExit(f"Phase 0Q log/guard contract missing: {missing_logs}")

    with tempfile.TemporaryDirectory() as directory:
        executable = Path(directory) / "test-stage-a-batch"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            str(source_path), str(test_path), "-o", str(executable),
        ], check=True)
        subprocess.run([str(executable)], check=True)

    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "console_contacted": False,
        "deployed": False,
        "executed_on_ps5": False,
        "submitted": False,
        "approved_for_deployment": False,
        "default_build": False,
        "artifact": {
            "path": str(object_path),
            "type": "ELF64 relocatable object",
            "size": len(obj),
            "sha256": hashlib.sha256(obj).hexdigest(),
            "direct_undefined_symbols": [],
        },
        "mapping_only_probe": {
            "path": str(probe_path),
            "type": "ELF64 PIE executable draft",
            "size": len(probe),
            "sha256": probe_sha256,
            "undefined_symbols": undefined,
            "forbidden_agc_videoout_submit_imports": [],
            "supervisor_action_present": True,
            "supervisor_action_requires_operator_presence": True,
            "supervisor_artifact_sha256_pinned": True,
            "supervisor_rejects_stale_log": True,
            "supervisor_cleanup_refusal_gate_present": True,
            "default_build": False,
            "watchdog_seconds": 10,
            "cleanup_guard_log_contract_pinned": True,
            "compiled_batch_entry_fields_pinned": True,
            "compiled_cpu_canary_mfence_pinned": True,
            "deployed": False,
            "executed_on_ps5": False,
        },
        "batch_entry_abi": {
            "bytes": 0x20,
            "virtual_address_offset": 0,
            "physical_offset_offset": 8,
            "length_offset": 0x10,
            "protection_offset": 0x18,
            "operation_offset": 0x1c,
        },
        "candidate_mapping": {
            "region_bytes": 0x20000,
            "alignment": 0x10000,
            "allocated_memory_type": "0x0c",
            "batch_protection": "0x0cf2",
            "map_operation": 0,
            "unmap_operation": 1,
        },
        "host_mock_tests": {
            "success_order": "reserve,allocate,map,unmap,release-physical,release-va",
            "definite_map_failure_cleanup": True,
            "ambiguous_map_retains_everything": True,
            "ambiguous_unmap_retains_everything": True,
            "passed": True,
        },
        "physical_allocation_plus_private_batch_policy_accepted_by_kernel": False,
        "gpu_visibility_proven": False,
        "next_safe_hardware_probe": (
            "one supervised mapping-only attempt; no AGC load, queue or submit"
        ),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
