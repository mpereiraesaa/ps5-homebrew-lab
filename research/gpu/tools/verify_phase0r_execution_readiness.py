#!/usr/bin/env python3
"""Consolidate every non-operator prerequisite for the first GPU submit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


CAPTURES = Path("research/gpu/captures")
ELF = Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0r-batch-first-submit.elf")
SUPERVISOR = Path("tools/night_supervisor.py")
OUTPUT = CAPTURES / "agc-phase0r-execution-readiness.json"


def load(name: str) -> dict:
    return json.loads((CAPTURES / name).read_text())


phase0q = load("agc-phase0q-runtime.json")
phase0r = load("agc-phase0r-draft-safety.json")
runtime = load("agc-phase0r-runtime.json")
queue = load("agc-queue-submit-proof.json")
fence = load("agc-release-fence-proof.json")
supervisor = SUPERVISOR.read_text()
elf_sha256 = hashlib.sha256(ELF.read_bytes()).hexdigest()

checks = {
    "firmware_scope_is_12_02": (
        phase0q["firmware"] == "12.02" and phase0r["firmware_scope"] == "12.02"
    ),
    "owned_native_policy_mapping_accepted": (
        phase0q["mapping"]["physical_type"] == "0x0c"
        and phase0q["mapping"]["batch_protection"] == "0x0cf2"
        and phase0q["mapping"]["accepted"]
        and phase0q["mapping"]["cpu_canaries_passed"]
    ),
    "phase0q_cleanup_complete": (
        phase0q["mapping"]["unmap_completed"]
        and phase0q["mapping"]["physical_release_completed"]
        and phase0q["mapping"]["virtual_release_completed"]
        and phase0q["host_clean_close_verified"]
    ),
    "phase0q_did_not_submit": (
        not phase0q["agc_loaded"] and not phase0q["queue_used"]
        and not phase0q["gpu_submitted"]
    ),
    "class0_backend_and_lazy_registration_pinned": (
        queue["system_runtime_equal"]["class0_backend"]
        and queue["system_runtime_equal"]["class0_lazy_registration"]
    ),
    "submit_acceptance_not_mislabeled_completion": (
        not queue["class0_submit_ioctl"]["submit_success_proves_gpu_completion"]
    ),
    "ownership_fence_semantics_pinned": (
        fence["ownership_protocol_proven"]
        and fence["ownership_cpu_initial"] == 1
        and fence["ownership_gpu_final"] == 0
        and fence["ownership_data_sel"] == 2
    ),
    "phase0r_binary_matches_audit": elf_sha256 == phase0r["elf_sha256"],
    "phase0r_stream_and_ordering_pinned": (
        phase0r["binary_stream_and_ordering_pinned"]
        and phase0r["stream_dwords"] == 15
        and phase0r["target_bytes"] == 4
        and phase0r["ownership_fence_initial"] == 1
        and phase0r["ownership_fence_final"] == 0
    ),
    "phase0r_has_no_videoout": not phase0r["videoout_used"],
    "phase0r_not_in_default_build": not phase0r["default_build"],
    "supervisor_requires_operator_and_hash": (
        phase0r["supervisor_action_present"]
        and phase0r["supervisor_requires_operator_presence"]
        and phase0r["supervisor_requires_exact_artifact_sha256"]
        and f'PHASE0R_SHA256 = "{elf_sha256}"' in supervisor
    ),
    "supervisor_rejects_stale_or_unsafe_cleanup": (
        phase0r["supervisor_rejects_stale_log"]
        and phase0r["supervisor_cleanup_refusal_gate_present"]
        and "require_phase0r_cleanup_safe(log)" in supervisor
    ),
}

if not all(checks.values()):
    failed = [name for name, passed in checks.items() if not passed]
    raise SystemExit("phase 0R readiness failed: " + ", ".join(failed))
if runtime["artifact_sha256"] != elf_sha256:
    raise SystemExit("phase 0R runtime evidence belongs to a different ELF")

result = {
    "schema": 1,
    "firmware_scope": "12.02",
    "checks": checks,
    "non_operator_preconditions_complete": True,
    "operator_presence_observed_by_this_verifier": False,
    "console_contacted": False,
    "deployed": True,
    "executed": True,
    "hardware_completion_proven": runtime["gpu_completion_proven"],
    "runtime_terminal_state": runtime["terminal_state"],
    "resources_retained": runtime["resources_retained"],
    "retry_unchanged_allowed": runtime["automatic_retry_allowed"],
    "automatic_or_unattended_execution_allowed": False,
    "audited_elf_sha256": elf_sha256,
    "next_action": (
        "complete controlled restart, then resolve the native command writer, "
        "VA/segment/backing and queue-execution differences before a new probe"
    ),
}
OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
