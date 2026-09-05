#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parents[2]
BUILD = APP / "build-stage-e"
ELF = BUILD / "eboot.elf"
LINK = BUILD / "llvm-pie.elf"
FSELF = APP / "dist-stage-e/PPSA99998/eboot.bin"
SOURCE = APP / "stage_b_main.cpp"
PROOF = ROOT / "research/gpu/captures/agc-stage-e-live-local-proof.json"
RUNTIME_CAPTURE = ROOT / "research/gpu/captures/agc-stage-e-centered-triangle-runtime.json"


def output(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True)


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"stage E verification failed: {message}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    tests = (
        ("shader-header", "test_stage_e_shader_header.c", "stage_e_shader_header.c"),
        ("color", "test_stage_e_color_target.c", "stage_e_color_target.c"),
        ("defaults", "test_stage_e_runtime_defaults.c", "stage_e_runtime_defaults.c"),
        ("registers", "test_stage_e_pipeline_registers.c", "stage_e_pipeline_registers.c"),
        ("dcb", "test_stage_e_dcb_offline.c", "stage_e_dcb_offline.c"),
    )
    for name, test, unit in tests:
        binary = f"/tmp/test-stage-e-live-{name}"
        run("cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I.",
            f"research/gpu/tools/{test}", f"legacy/probes/ps5-agc-phase0/{unit}",
            "-o", binary)
        run(binary)

    undefined = {line.split()[-1] for line in output("nm", "-u", str(LINK)).splitlines()
                 if line.strip()}
    required = {
        "sceAgcInit", "sceAgcCreateShader", "sceAgcLinkShaders",
        "sceAgcGetRegisterDefaults", "sceAgcDcbSetFlip",
        "sceAgcDcbDrawIndexAuto",
        "sceAgcDcbSetCxRegistersIndirect",
        "sceAgcDcbSetUcRegistersIndirect", "sceAgcDcbSetShRegistersIndirect",
        "sceAgcDriverSubmitDcb",
        "sceAgcDriverGetWaitRenderingPacketSizeInDwords",
        "sceAgcDriverWaitUntilSafeForRendering", "sceVideoOutOpen",
        "sceVideoOutRegisterBuffers2", "sceVideoOutAddFlipEvent",
        "sceVideoOutGetEventData", "sceVideoOutUnregisterBuffers",
        "sceKernelAllocateMainDirectMemory", "sceKernelMapDirectMemory",
        "sceKernelBatchMap", "sceKernelReserveVirtualRange",
    }
    require(required <= undefined, f"missing imports: {sorted(required - undefined)}")
    forbidden = {name for name in undefined if
                 "ps5debug" in name.lower() or "get_process" in name.lower()}
    require(not forbidden, f"commercial/debug access imports: {sorted(forbidden)}")
    dependencies = sorted(line.split("[")[1].split("]")[0]
                          for line in output("readelf", "-d", str(ELF)).splitlines()
                          if "(NEEDED)" in line)
    expected = sorted(["libSceAgc.prx", "libSceAgcDriver.prx",
                       "libSceLibcInternal.prx", "libSceSysmodule.prx",
                       "libSceVideoOut.prx", "libkernel.prx"])
    require(dependencies == expected, f"dependency set differs: {dependencies}")
    # Inspect the ordinary linked ELF. The native container carries the same
    # text but can make llvm-objdump spend minutes walking container metadata.
    disassembly = output("llvm-objdump", "-d", str(LINK))
    require("clflush" in disassembly and "mfence" in disassembly,
            "cache publication instructions absent")

    source = SOURCE.read_text()
    checkpoint_match = re.search(
        r"stage_e_runtime_checkpoint\s*=\s*(\d+)\s*;", source)
    require(checkpoint_match is not None, "runtime checkpoint initializer absent")
    checkpoint = int(checkpoint_match.group(1))
    require(checkpoint in (5, 6), f"unsupported runtime checkpoint: {checkpoint}")
    invariants = (
        "STAGE_E_PREFLIGHT_COMPLETE", "STAGE_E_DCB_COMPOSE_STARTED no_submit_yet=true",
        "STAGE_E_TRANSACTION_STARTED one_submit=true",
        "stage_e_compose_dcb_offline", "stage_e_select_runtime_color_defaults",
        "stage_e_build_color_target", "stage_e_build_pipeline_registers",
        "stage_e_shader_aliases_own_headers=true",
        "stage_e_shader_objects_distinct=true",
        "stage_e_shader_code_bound=true",
        "stage_e_gs_start", "stage_e_ps_start", "STAGE_E_GPU_FENCE_ZERO",
        "registers=84/12/3", "target=gfx1013",
        "STAGE_E_GUARDS_INTACT", "STAGE_E_RECOVERY_BUFFER_UNTOUCHED",
        "STAGE_E_SHADER_ARENA_SCRUBBED", "STAGE_E_COMPLETE cleanup complete",
        "ownership fence timeout", "VideoOut completion mismatch or timeout",
        "retain process, AGC, VideoOut, buffers and mappings",
    )
    # The common runtime logs the generic Stage-B fence marker; require and
    # classify that exact marker instead of asserting a nonexistent alias.
    invariants = tuple(x for x in invariants if x != "STAGE_E_GPU_FENCE_ZERO") + (
        "STAGE_B_GPU_FENCE_ZERO",)
    require(all(item in source for item in invariants), "safety invariant absent")
    require(source.count("return sceAgcDriverSubmitDcb(&submit);") == 1,
            "submit adapter is not unique")
    dcb_marker = source.index("STAGE_E_DCB_COMPOSE_STARTED no_submit_yet=true")
    dcb_compose = source.index("stage_e_compose_dcb_offline(command_words")
    dcb_transaction = source.index(
        "STAGE_E_TRANSACTION_STARTED one_submit=true", dcb_compose)
    dcb_submit = source.index("submit_adapter(command_words", dcb_transaction)
    require(dcb_marker < dcb_compose < dcb_transaction < dcb_submit,
            "full-pipeline composition/transaction/submit markers are out of order")
    isolation_marker = source.index("STAGE_E_DRAW_ISOLATION buffer=1")
    isolation_submit = source.rfind("submit_adapter(command_words", 0,
                                    dcb_marker)
    require(isolation_submit != -1 and isolation_marker < isolation_submit,
            "wait-flip isolation marker/submit are out of order")
    require(source.index("STAGE_B_GPU_FENCE_ZERO") <
            source.index("STAGE_E_GUARDS_INTACT"),
            "guard observation can precede ownership fence")

    runtime_capture = (json.loads(RUNTIME_CAPTURE.read_text())
                       if RUNTIME_CAPTURE.is_file() else {})
    hardware_validated = (
        runtime_capture.get("artifact_fself_sha256") == sha(FSELF) and
        runtime_capture.get("gpu_fence_zero") is True and
        runtime_capture.get("videoout_event_exact") is True and
        runtime_capture.get("teardown_complete") is True)
    proof = {
        "schema": 1, "firmware": "12.02", "title_id": "PPSA99998",
        "elf_sha256": sha(ELF), "fself_sha256": sha(FSELF),
        "dependencies": dependencies, "required_imports": sorted(required),
        "host_tests": [name for name, _, _ in tests],
        "own_shader_sources": True, "runtime_defaults_embedded": False,
        "runtime_defaults_semantic_selector": "unique 0x38e92c91 in cx[0..83]",
        "command_mapping": "BatchMap type=0x0c protection=0xf2",
        "framebuffer_mapping": "MapDirectMemory type=3 protection=0x33",
        "shader_mapping": "MapDirectMemory type=0x0c protection=0x33",
        "selected_buffer": 1, "recovery_buffer": 0,
        "runtime_checkpoint": checkpoint,
        "dcb_register_packet_order": ["cx_indirect", "uc_indirect", "sh_indirect"],
        "pipeline_register_counts": {"cx": 84, "sh": 12, "uc": 3},
        "shader_cx_order": ["link_34", "pre_raster_10", "pixel_9"],
        "packet_builder_evidence": "FW 12.02 native CX/UC/SH builders emit five DWORD",
        "submission_reachable_in_this_build": checkpoint == 6,
        "submission_limit": 2, "fence_deadline_seconds": 2,
        "videoout_deadline_seconds": 2, "watchdog_seconds": 20,
        "post_transaction_ambiguity_policy": "park and retain all resources",
        "commercial_process_access": False, "deployed": False,
        "gpu_executed": hardware_validated,
        "iteration_mode": "bounded_classified_retries",
        "hardware_validation_capture": str(RUNTIME_CAPTURE.relative_to(ROOT)),
        "approved_for_supervised_execution": checkpoint == 6,
    }
    PROOF.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
