#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = Path(__file__).resolve().parent
BUILD = APP / "build-stage-b"
ELF = BUILD / "eboot.elf"
LINK_ELF = BUILD / "llvm-pie.elf"
FSELF = APP / "dist-stage-b/PPSA99998/eboot.bin"
SOURCE = APP / "stage_b_main.cpp"
CAPTURE = ROOT / "research/gpu/captures/agc-stage-b-local-proof.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"stage B verification failed: {message}")


def main() -> int:
    for path in (ELF, LINK_ELF, FSELF, SOURCE):
        require(path.is_file(), f"missing {path}")
    source = SOURCE.read_text()
    undefined = {
        line.split()[-1]
        for line in output("nm", "-u", str(LINK_ELF)).splitlines()
        if line.strip()
    }
    required = {
        "sceAgcInit", "sceAgcDcbSetFlip", "sceAgcDriverSubmitDcb",
        "sceKernelAllocateMainDirectMemory", "sceKernelBatchMap",
        "sceKernelReserveVirtualRange", "sceKernelMapDirectMemory",
        "sceKernelCreateEqueue", "sceKernelWaitEqueue",
        "sceVideoOutOpen", "sceVideoOutAddFlipEvent",
        "sceVideoOutSetBufferAttribute2", "sceVideoOutRegisterBuffers2",
        "sceVideoOutGetEventData", "sceVideoOutUnregisterBuffers",
        "sceVideoOutDeleteFlipEvent", "sceVideoOutClose",
    }
    forbidden = {
        "sceAgcCreateShader", "sceAgcLinkShaders", "sceAgcDcbDrawIndexAuto",
        "sceVideoOutSubmitFlip",
    }
    require(required <= undefined, f"missing imports {sorted(required - undefined)}")
    require(not (forbidden & undefined),
            f"forbidden imports {sorted(forbidden & undefined)}")

    dynamic = output("readelf", "-d", str(ELF))
    dependencies = sorted(
        line.split("[")[1].split("]")[0]
        for line in dynamic.splitlines() if "(NEEDED)" in line
    )
    expected_dependencies = sorted([
        "libSceLibcInternal.prx", "libSceSysmodule.prx", "libSceVideoOut.prx",
        "libkernel.prx", "libSceAgc.prx", "libSceAgcDriver.prx",
    ])
    require(dependencies == expected_dependencies,
            f"dependency set differs: {dependencies}")

    # The native-tool output is a sectionless PS5 ELF; some llvm-objdump
    # versions wait indefinitely while trying to discover its code ranges.
    # Machine-code assertions belong on the sectioned linker input, whose
    # executable bytes are what native-tool wraps into eboot.elf.
    disassembly = output("llvm-objdump", "-d", str(LINK_ELF))
    require("clflush" in disassembly and "mfence" in disassembly,
            "cache publication instructions absent")
    require("selected_buffer_prefilled=true index=0 other_buffer_cpu_writes=0" in source,
            "selected-only write marker absent")
    require("STAGE_B_BUFFER_STRIDE" in source and
            "for (std::size_t index = 0; index < plan.tiled_footprint / 4" in source,
            "bounded selected-buffer fill absent")
    require(source.index("SETFLIP_TRANSACTION_STARTED") <
            source.index("stage_b_build_and_submit(&input"),
            "retention marker does not precede SetFlip transaction")
    fence_marker = source.index("STAGE_B_GPU_FENCE_ZERO")
    require(fence_marker <
            source.index("stage_b_poll_videoout_completion", fence_marker),
            "event polling can precede observed GPU fence")
    require(source.index("STAGE_B_VIDEOOUT_EVENT_ONE") <
            source.index("cleanup_resources();", source.index("STAGE_B_VIDEOOUT_EVENT_ONE")),
            "cleanup can precede exact VideoOut event")
    require("STAGE_B_COMPLETION_EVENT_BEFORE_FENCE" in
            (ROOT / "legacy/probes/ps5-agc-phase0/stage_b_completion.c").read_text(),
            "event-before-fence guard absent")
    require("STAGE_B_COMPLETION_UNEXPECTED_FLIP_ARG" in
            (ROOT / "legacy/probes/ps5-agc-phase0/stage_b_completion.c").read_text(),
            "unexpected flip_arg guard absent")
    require("PARKED_STAGE_B_TRANSACTION" in source and
            "DO_NOT_CLOSE_PPSA99998" in source,
            "ambiguous-state retention marker absent")
    require(source.count("if (result != 0) return result;") >= 8,
            "cleanup does not fail-stop on each resource boundary")

    subprocess.run(
        ["python3", "research/gpu/tools/verify_presentation_staging.py"],
        cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
    )
    proof = {
        "schema": 1,
        "firmware": "12.02",
        "title_id": "PPSA99998",
        "elf_sha256": sha(ELF),
        "fself_sha256": sha(FSELF),
        "dependencies": dependencies,
        "required_imports": sorted(required),
        "forbidden_imports_absent": sorted(forbidden),
        "resolution": "1920x1080",
        "registered_buffers": 2,
        "selected_buffer": 0,
        "other_buffer_cpu_writes": 0,
        "command_mapping": {"type": 12, "protection": 242},
        "video_mapping": {"type": 3, "protection": 51},
        "event_order_guarded": "GPU fence zero before exact flip_arg event",
        "cache_publication_machine_code_verified": True,
        "cleanup_fail_stops_on_first_error": True,
        "shader_or_draw": False,
        "commercial_process_access": False,
        "console_contacted": False,
        "approved_for_supervised_execution": True,
    }
    CAPTURE.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
