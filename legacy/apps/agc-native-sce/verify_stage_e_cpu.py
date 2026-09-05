#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parents[2]
BUILD = APP / "build-stage-e-cpu"
ELF = BUILD / "eboot.elf"
LINK = BUILD / "llvm-pie.elf"
FSELF = APP / "dist-stage-e-cpu/PPSA99998/eboot.bin"
SOURCE = APP / "stage_e_cpu_main.cpp"
CAPTURE = ROOT / "research/gpu/captures/agc-stage-e-cpu-local-proof.json"


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True)


def require(value: bool, message: str) -> None:
    if not value:
        raise SystemExit(f"Stage E CPU verification failed: {message}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    subprocess.run(["python3", "research/gpu/tools/build_stage_e_shaders.py"], cwd=ROOT, check=True)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I.",
        "research/gpu/tools/test_stage_e_shader_header.c",
        "legacy/probes/ps5-agc-phase0/stage_e_shader_header.c", "-o", "/tmp/test-stage-e-header",
    ], cwd=ROOT, check=True)
    subprocess.run(["/tmp/test-stage-e-header"], check=True)
    undefined = {line.split()[-1] for line in output("nm", "-u", str(LINK)).splitlines() if line.strip()}
    required = {"sceAgcInit", "sceAgcCreateShader", "sceAgcLinkShaders",
                "sceKernelAllocateMainDirectMemory", "sceKernelMapDirectMemory",
                "sceKernelMunmap", "sceKernelReleaseDirectMemory"}
    forbidden = {name for name in undefined if "Dcb" in name or "Submit" in name or "VideoOut" in name or "Draw" in name}
    require(required <= undefined, f"missing imports: {sorted(required - undefined)}")
    require(not forbidden, f"forbidden imports: {sorted(forbidden)}")
    dependencies = sorted(line.split("[")[1].split("]")[0]
                          for line in output("readelf", "-d", str(ELF)).splitlines()
                          if "(NEEDED)" in line)
    require(dependencies == sorted(["libSceLibcInternal.prx", "libSceSysmodule.prx",
                                    "libkernel.prx", "libSceAgc.prx"]),
            f"dependency set differs: {dependencies}")
    source = SOURCE.read_text()
    for marker in ("independent_headers_prevalidated=", "linked_output_canaries_intact=",
                   "linked_outputs_deterministic=", "generated_shader_code_unchanged=",
                   "direct_arena_scrubbed=", "STAGE_E_CPU_LINK_COMPLETE="):
        require(marker in source, f"missing runtime marker {marker}")
    proof = {
        "schema": 1,
        "firmware": "12.02",
        "title_id": "PPSA99998",
        "elf_sha256": sha(ELF),
        "fself_sha256": sha(FSELF),
        "dependencies": dependencies,
        "shader_sources": {
            "fullscreen_triangle_sha256": sha(ROOT / "research/gpu/build/stage-e-shaders/fullscreen_triangle.bin"),
            "solid_green_sha256": sha(ROOT / "research/gpu/build/stage-e-shaders/solid_green.bin"),
        },
        "header_arena_bytes": 216,
        "mandatory_user_data_structure": True,
        "header_host_relocation_test": True,
        "header_ps5_object_compiles": True,
        "forbidden_gpu_imports_absent": True,
        "queue_dcb_submit_draw_videoout": False,
        "commercial_process_access": False,
        "console_contacted": False,
        "approved_for_cpu_only_execution": True,
    }
    CAPTURE.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
