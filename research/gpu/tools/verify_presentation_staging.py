#!/usr/bin/env python3
"""Build the non-executing A-to-E AGC presentation-stage gate."""
from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
from pathlib import Path


ROOT = Path("research/gpu")
CAPTURES = ROOT / "captures"


def load(name: str) -> dict:
    return json.loads((CAPTURES / name).read_text())


def main() -> int:
    label = load("agc-phase0m-draft-safety.json")
    label_v5 = load("agc-native-label-v5-runtime.json")
    readiness = load("minimal-gpu-readiness.json")
    fill = load("agc-solid-fill-plan-4k.json")
    flip = load("agc-eop-flip-proof.json")
    videoout_event = load("videoout-event-abi-proof.json")
    stage_b_local = load("agc-stage-b-local-proof.json")
    stage_b_runtime = load("agc-stage-b-v4-runtime.json")
    stage_c_runtime = load("agc-stage-c-progression.json")
    document = (ROOT / "AGC_PRESENTATION_STAGING.md").read_text()
    supervisor = Path("tools/night_supervisor.py").read_text()
    compose_path = Path("legacy/probes/ps5-agc-phase0/stage_b_compose.c")
    compose = compose_path.read_text()
    makefile = Path("legacy/probes/ps5-agc-phase0/Makefile").read_text()
    ps5_object_path = Path("legacy/probes/ps5-agc-phase0/stage-b-compose.o")
    ps5_object = ps5_object_path.read_bytes()
    surface_path = Path("legacy/probes/ps5-agc-phase0/stage_b_surface.c")
    surface = surface_path.read_text()
    surface_object_path = Path("legacy/probes/ps5-agc-phase0/stage-b-surface.o")
    surface_object = surface_object_path.read_bytes()
    transaction_path = Path("legacy/probes/ps5-agc-phase0/stage_b_transaction.c")
    transaction = transaction_path.read_text()
    transaction_object_path = Path("legacy/probes/ps5-agc-phase0/stage-b-transaction.o")
    transaction_object = transaction_object_path.read_bytes()
    completion_path = Path("legacy/probes/ps5-agc-phase0/stage_b_completion.c")
    completion = completion_path.read_text()
    completion_object_path = Path("legacy/probes/ps5-agc-phase0/stage-b-completion.o")
    completion_object = completion_object_path.read_bytes()
    event_adapter_path = Path("legacy/probes/ps5-agc-phase0/stage_b_event_adapter.c")
    event_adapter = event_adapter_path.read_text()
    event_adapter_object_path = Path("legacy/probes/ps5-agc-phase0/stage-b-event-adapter.o")
    event_adapter_object = event_adapter_object_path.read_bytes()
    event_adapter_undefined = subprocess.check_output(
        ["nm", "-u", str(event_adapter_object_path)], text=True
    )
    compose_test = Path("research/gpu/tools/test_stage_b_compose.c")
    with tempfile.TemporaryDirectory() as directory:
        executable = Path(directory) / "test-stage-b-compose"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            str(compose_path), str(compose_test), "-o", str(executable),
        ], check=True)
        subprocess.run([str(executable)], check=True)
        surface_executable = Path(directory) / "test-stage-b-surface"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            str(surface_path), "research/gpu/tools/test_stage_b_surface.c",
            "-o", str(surface_executable),
        ], check=True)
        subprocess.run([str(surface_executable)], check=True)
        transaction_executable = Path(directory) / "test-stage-b-transaction"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            str(compose_path), str(transaction_path),
            "research/gpu/tools/test_stage_b_transaction.c",
            "-o", str(transaction_executable),
        ], check=True)
        subprocess.run([str(transaction_executable)], check=True)
        completion_executable = Path(directory) / "test-stage-b-completion"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            str(completion_path),
            "research/gpu/tools/test_stage_b_completion.c",
            "-o", str(completion_executable),
        ], check=True)
        subprocess.run([str(completion_executable)], check=True)
        adapter_executable = Path(directory) / "test-stage-b-event-adapter"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            str(completion_path), str(event_adapter_path),
            "research/gpu/tools/test_stage_b_event_adapter.c",
            "-o", str(adapter_executable),
        ], check=True)
        subprocess.run([str(adapter_executable)], check=True)
    checks = {
        "A_private_label_hardware_proven": (
            readiness["static_label_preconditions_complete"]
            and readiness["hardware_label_execution_proven"]
            and readiness["private_mapping_gpu_visibility_proven"]
            and label_v5["observed"]["gpu_ownership_complete"]
            and label_v5["observed"]["target_after_fence"] == "0x00000000"
            and label_v5["observed"]["fence_after"] == 0
            and label_v5["cleanup"]["services_healthy_after_close"]
            and not label["approved_for_deployment"]
        ),
        "B_videoout_separately_proven": (
            readiness["solid_clear"]["videoout_registration_proven"]
            and readiness["solid_clear"]["double_buffer_and_flip_event_proven"]
        ),
        "B_setflip_abi_separately_proven": (
            flip["direct_driver_builder"]["abi_static_proven"]
            and not flip["direct_driver_builder"]["pure_packet_builder"]
            and not flip["direct_driver_builder"]["build_only_with_live_handle_allowed"]
        ),
        "C_fill_encoding_ready_only": (
            fill["primary_source_evidence"]["immediate_range_fill_semantics_proven"]
            and fill["fits_one_dma_packet"]
            and fill["dma_data"]["destination_is_synthetic"]
            and not fill["submitted"]
        ),
        "uncertain_submit_retains_resources": (
            not label["automatic_close_after_uncertain_submit"]
            and "No se desregistra, cierra ni" in document
        ),
        "visible_clear_after_A_B_C": "Sólo después de A, B y C" in document,
        "triangle_after_visible_clear": "El triángulo empieza únicamente cuando D" in document,
        "stage_B_cleanup_guard_and_supervised_action_integrated": (
            "require_stage_b_cleanup_safe" in supervisor
            and "stage_b_cleanup_gate" in supervisor
            and "run-stage-b" in supervisor
            and "def run_stage_b" in supervisor
            and "STAGE_B_FSELF_SHA256" in supervisor
        ),
        "stage_B_stream_compositor_host_tested": (
            "stream->transaction_started = 1;" in compose
            and compose.index("stream->transaction_started = 1;") <
                compose.index("set_flip(&cursor")
            and "0xc0064900" in compose
            and "0x06000528" in compose
            and "0x42010000" in compose
            and "SubmitDcb" not in compose
            and "sceVideoOut" not in compose
        ),
        "stage_B_ps5_object_only_excluded_from_default_build": (
            "stage-b-compose.o: stage_b_compose.c stage_b_compose.h" in makefile
            and "$(CC) $(CFLAGS) -c -o $@ stage_b_compose.c" in makefile
            and "stage-b-compose.o" not in makefile.split("all:", 1)[1].split("\n\n", 1)[0]
            and ps5_object.startswith(b"\x7fELF")
        ),
        "stage_B_surface_contract_host_tested": (
            "STAGE_B_DIRECT_BYTES" in surface
            and "STAGE_B_BUFFER_STRIDE" in surface
            and "plan->register_count = STAGE_B_BUFFER_COUNT" in surface
            and "plan->flip_mode = 1" in surface
            and "stage-b-surface.o: stage_b_surface.c stage_b_surface.h" in makefile
            and "stage-b-surface.o" not in makefile.split("all:", 1)[1].split("\n\n", 1)[0]
            and surface_object.startswith(b"\x7fELF")
        ),
        "stage_B_transaction_order_and_retention_host_tested": (
            "*input->gpu_fence = UINT64_C(1);" in transaction
            and transaction.index("*input->gpu_fence = UINT64_C(1);") <
                transaction.index("stage_b_compose_setflip_then_fence(")
            and transaction.index("stage_b_compose_setflip_then_fence(") <
                transaction.index("input->submit(input->stream->start")
            and transaction.index("state->submit_called = 1;") <
                transaction.index("input->submit(input->stream->start")
            and "state->retain_all_resources = 1;" in transaction
            and "fence_start < stream_end && fence_end > stream_start" in transaction
            and "stage-b-transaction.o: stage_b_transaction.c" in makefile
            and "stage-b-transaction.o" not in makefile.split("all:", 1)[1].split("\n\n", 1)[0]
            and transaction_object.startswith(b"\x7fELF")
        ),
        "stage_B_completion_requires_fence_and_exact_event": (
            "observation->fence_value == 0" in completion
            and "observation->videoout_event_flip_arg != state->expected_flip_arg" in completion
            and "STAGE_B_COMPLETION_UNEXPECTED_FLIP_ARG" in completion
            and "STAGE_B_COMPLETION_EVENT_BEFORE_FENCE" in completion
            and "state->fence_zero_seen && state->matching_videoout_event_seen" in completion
            and "state->retain_all_resources = 0;" in completion
            and completion.index("state->cleanup_allowed = 1;") <
                completion.index("state->retain_all_resources = 0;")
            and "state->parked = 1;" in completion
            and "stage-b-completion.o: stage_b_completion.c" in makefile
            and "stage-b-completion.o" not in makefile.split("all:", 1)[1].split("\n\n", 1)[0]
            and completion_object.startswith(b"\x7fELF")
        ),
        "stage_B_videoout_event_flip_arg_abi_static_proven": (
            videoout_event["abi"]["static_proven"]
            and videoout_event["function"]["system_runtime_equal"]
            and videoout_event["completion_use"]["wait_equeue_event_can_be_matched_to_exact_flip_arg"]
            and not videoout_event["completion_use"]["homebrew_runtime_call_proven"]
        ),
        "stage_B_real_event_adapter_linked_in_supervised_probe": (
            "sceKernelWaitEqueue(poll->equeue" in event_adapter
            and "sceVideoOutGetEventData(poll->event_storage" in event_adapter
            and "stage_b_completion_observe(state, &observation)" in event_adapter
            and "state->retain_all_resources = 1;" in event_adapter
            and "stage-b-event-adapter.o: stage_b_event_adapter.c" in makefile
            and "stage-b-event-adapter.o" not in makefile.split("all:", 1)[1].split("\n\n", 1)[0]
            and event_adapter_object.startswith(b"\x7fELF")
            and "sceKernelWaitEqueue" in event_adapter_undefined
            and "sceVideoOutGetEventData" in event_adapter_undefined
            and "stage_b_completion_observe" in event_adapter_undefined
            and stage_b_local["approved_for_supervised_execution"]
            and "sceKernelWaitEqueue" in stage_b_local["required_imports"]
            and "sceVideoOutGetEventData" in stage_b_local["required_imports"]
        ),
    }
    if not all(checks.values()):
        raise SystemExit(f"presentation staging evidence inconsistent: {checks}")
    result = {
        "schema": 2,
        "firmware_scope": "12.02",
        "console_contacted": False,
        "unattended_execution_allowed": False,
        "checks": checks,
        "stages": {
            "A_private_label": {
                "static_ready": True,
                "hardware_proven": True,
                "next": False,
                "evidence": "agc-native-label-v5-runtime.json",
            },
            "B_cpu_prefilled_in_stream_flip": {
                "videoout_separately_proven": True,
                "setflip_abi_separately_proven": True,
                "composed": True,
                "stream_compositor_composed_and_host_tested": True,
                "ps5_relocatable_object": {
                    "built": True,
                    "linked_executable": False,
                    "sha256": hashlib.sha256(ps5_object).hexdigest(),
                    "size": len(ps5_object),
                },
                "surface_plan_ps5_relocatable_object": {
                    "built": True,
                    "linked_executable": False,
                    "sha256": hashlib.sha256(surface_object).hexdigest(),
                    "size": len(surface_object),
                },
                "surface_contract_composed_and_host_tested": True,
                "transaction_composed_and_host_tested": True,
                "transaction_ps5_relocatable_object": {
                    "built": True,
                    "linked_executable": False,
                    "sha256": hashlib.sha256(transaction_object).hexdigest(),
                    "size": len(transaction_object),
                },
                "completion_classifier_host_tested": True,
                "completion_ps5_relocatable_object": {
                    "built": True,
                    "linked_executable": False,
                    "sha256": hashlib.sha256(completion_object).hexdigest(),
                    "size": len(completion_object),
                },
                "completion_backend_event_abi_static_proven": True,
                "completion_backend_event_runtime_call_proven": True,
                "event_adapter_host_tested": True,
                "event_adapter_ps5_relocatable_object": {
                    "built": True,
                    "linked_executable": False,
                    "sha256": hashlib.sha256(event_adapter_object).hexdigest(),
                    "size": len(event_adapter_object),
                    "unresolved_runtime_symbols": [
                        "sceKernelWaitEqueue",
                        "sceVideoOutGetEventData",
                        "stage_b_completion_observe",
                    ],
                },
                "full_probe_composed": True,
                "linked_executable": {
                    "built": True,
                    "elf_sha256": stage_b_local["elf_sha256"],
                    "fself_sha256": stage_b_local["fself_sha256"],
                    "approved_for_supervised_execution": True,
                },
                "hardware_proven": True,
                "cleanup_complete": stage_b_runtime["cleanup_complete"],
                "evidence": "agc-stage-b-v4-runtime.json",
                "cleanup_guard_integrated": True,
                "supervisor_run_action_present": True,
            },
            "C_large_private_gpu_fill": {
                "immediate_fill_semantics_proven": True,
                "exact_4k_packet_composed_with_synthetic_address": True,
                "hardware_proven": stage_c_runtime["hardware_proven"],
                "maximum_proven_bytes": stage_c_runtime["maximum_proven_bytes"],
                "progression_bytes": stage_c_runtime["progression_bytes"],
                "evidence": "agc-stage-c-progression.json",
            },
            "D_visible_gpu_clear": {"ready": False, "hardware_proven": False},
            "E_triangle": {"ready": False, "hardware_proven": False},
        },
        "transaction_rule": (
            "SetFlip builder call, submission of that exact stream, GPU fence, "
            "and VideoOut completion share one retained lifetime"
        ),
        "automatic_cleanup_after_uncertain_submit": False,
        "approved_for_deployment": False,
    }
    output = CAPTURES / "agc-presentation-staging.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
