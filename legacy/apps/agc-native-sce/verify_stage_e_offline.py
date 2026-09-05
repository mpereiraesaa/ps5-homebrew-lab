#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parents[2]
BUILD = APP / "build-stage-e-offline"
ELF = BUILD / "eboot.elf"
LINK = BUILD / "llvm-pie.elf"
FSELF = APP / "dist-stage-e-offline/PPSA99998/eboot.bin"
PROOF = ROOT / "research/gpu/captures/agc-stage-e-offline-proof.json"

def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    run("cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I.",
        "research/gpu/tools/test_stage_e_color_target.c",
        "legacy/probes/ps5-agc-phase0/stage_e_color_target.c", "-o", "/tmp/test-stage-e-color")
    run("/tmp/test-stage-e-color")
    run("cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I.",
        "research/gpu/tools/test_stage_e_dcb_offline.c",
        "legacy/probes/ps5-agc-phase0/stage_e_dcb_offline.c", "-o", "/tmp/test-stage-e-dcb")
    run("/tmp/test-stage-e-dcb")
    run("cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I.",
        "research/gpu/tools/test_stage_e_pipeline_registers.c",
        "legacy/probes/ps5-agc-phase0/stage_e_pipeline_registers.c", "-o", "/tmp/test-stage-e-regs")
    run("/tmp/test-stage-e-regs")
    run("cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I.",
        "research/gpu/tools/test_stage_e_runtime_defaults.c",
        "legacy/probes/ps5-agc-phase0/stage_e_runtime_defaults.c",
        "-o", "/tmp/test-stage-e-runtime-defaults")
    run("/tmp/test-stage-e-runtime-defaults")
    undefined = subprocess.check_output(["nm", "-u", str(LINK)], text=True)
    forbidden = ("sceAgc", "sceVideoOut", "Submit", "ps5debug", "get_process")
    if any(token in undefined for token in forbidden):
        raise SystemExit("offline artifact contains a forbidden runtime import")
    dynamic = subprocess.check_output(["readelf", "-d", str(ELF)], text=True)
    dependencies = sorted(line.split("[")[1].split("]")[0]
                          for line in dynamic.splitlines() if "(NEEDED)" in line)
    if dependencies != ["libSceLibcInternal.prx"]:
        raise SystemExit(f"unexpected build-only dependencies: {dependencies}")
    source = (APP / "stage_e_offline_main.cpp").read_text()
    if ("stage_e_compose_dcb_offline" not in source or
            "stage_e_build_color_target" not in source or
            "STAGE_E_CX_REGISTER_COUNT" not in source):
        raise SystemExit("offline pipeline is not integrated")
    proof = {
        "schema": 1, "title_id": "PPSA99998", "firmware": "12.02",
        "elf_sha256": sha(ELF), "fself_sha256": sha(FSELF),
        "packet_order": ["wait_safe_for_rendering", "cx_indirect", "uc_indirect", "sh_indirect",
                         "draw_index_auto_3", "set_flip_callback", "ownership_release"],
        "register_counts": {"cx": 65, "sh": 12, "uc": 3,
                            "render_target": 16, "viewport_scissor": 15},
        "render_target_requires_matching_runtime_defaults": True,
        "render_target_defaults_embedded": False,
        "runtime_default_selector_host_test": True,
        "runtime_default_selector": {
            "semantic_key": "0x38e92c91", "bank": "cx",
            "index_policy": "unique index in 0..83",
            "fw_root_count": 137, "fw_cx_count": 84,
        },
        "host_bounds_alignment_order_canary_tests": True,
        "normalized_dcb_fnv1a64": "0x39a2eb5496ae4d8a",
        "synthetic_register_plan_fnv1a64": "0xf4b51fe90d71879a",
        "ps5_objects_linked": True, "build_only": True,
        "dependencies": dependencies,
        "deployed": False, "submitted": False, "gpu_executed": False,
        "commercial_process_access": False,
        "proprietary_game_or_shader_material": False,
    }
    PROOF.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
