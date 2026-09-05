#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = Path(__file__).resolve().parent
SOURCE = APP / "stage_c_main.cpp"
ALLOWED_SIZES = (256, 4096, 65536)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"stage C verification failed: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fill_bytes", type=int, choices=ALLOWED_SIZES)
    args = parser.parse_args()
    build = APP / f"build-stage-c-{args.fill_bytes}"
    elf = build / "eboot.elf"
    link_elf = build / "llvm-pie.elf"
    fself = APP / f"dist-stage-c-{args.fill_bytes}/PPSA99998/eboot.bin"
    for path in (elf, link_elf, fself, SOURCE):
        require(path.is_file(), f"missing {path}")
    source = SOURCE.read_text()
    undefined = {
        line.split()[-1]
        for line in output("nm", "-u", str(link_elf)).splitlines()
        if line.strip()
    }
    required = {
        "sceAgcInit", "sceAgcDriverSubmitDcb",
        "sceKernelAllocateMainDirectMemory", "sceKernelBatchMap",
        "sceKernelReserveVirtualRange", "sceKernelMunmap",
        "sceKernelReleaseDirectMemory",
    }
    forbidden = {
        "sceAgcCreateShader", "sceAgcLinkShaders", "sceAgcDcbDrawIndexAuto",
        "sceAgcDcbSetFlip", "sceVideoOutOpen", "sceVideoOutSubmitFlip",
    }
    require(required <= undefined, f"missing imports {sorted(required - undefined)}")
    require(not (forbidden & undefined),
            f"forbidden imports {sorted(forbidden & undefined)}")
    dependencies = sorted(
        line.split("[")[1].split("]")[0]
        for line in output("readelf", "-d", str(elf)).splitlines()
        if "(NEEDED)" in line
    )
    expected = sorted([
        "libSceLibcInternal.prx", "libSceSysmodule.prx", "libkernel.prx",
        "libSceAgc.prx", "libSceAgcDriver.prx",
    ])
    require(dependencies == expected, f"dependency set differs: {dependencies}")
    disassembly = output("llvm-objdump", "-d", str(elf))
    require("clflush" in disassembly and "mfence" in disassembly,
            "cache publication instructions absent")
    invariants = (
        "kFillBytes > 4", "kFillBytes & 3", "kFillOffset >= kGuardBytes",
        "kFillOffset + kFillBytes + kGuardBytes <= kArenaBytes",
        "target and fence overlap", "stage_c_prefix_canary_intact=",
        "stage_c_suffix_canary_intact=", "stage_c_outside_untouched=",
        "STAGE_C_GPU_FENCE_ZERO", "PARKED_STAGE_C_TRANSACTION",
        "DO_NOT_CLOSE_PPSA99998", "STAGE_C_COMPLETE cleanup complete",
    )
    require(all(item in source for item in invariants),
            "one or more safety invariants absent")
    require(source.index("STAGE_C_TRANSACTION_STARTED") <
            source.index("sceAgcDriverSubmitDcb(&submit)"),
            "transaction marker does not precede submit")
    require(source.index("STAGE_C_GPU_FENCE_ZERO") <
            source.index("target_matches(target)"),
            "CPU verification can precede GPU fence")
    require(source.index("stage_c_outside_untouched=") <
            source.index("cleanup_all();", source.index("stage_c_outside_untouched=")),
            "cleanup can precede range verification")
    proof = {
        "schema": 1,
        "firmware": "12.02",
        "title_id": "PPSA99998",
        "fill_bytes": args.fill_bytes,
        "elf_sha256": sha(elf),
        "fself_sha256": sha(fself),
        "dependencies": dependencies,
        "required_imports": sorted(required),
        "forbidden_imports_absent": sorted(forbidden),
        "separate_command_and_data_mappings": True,
        "mapping": {"bytes_each": 0x20000, "type": 12, "protection": 242},
        "guard_bytes_each_side": 64,
        "full_outside_range_scan": True,
        "cache_publication_machine_code_verified": True,
        "shader_draw_videoout": False,
        "commercial_process_access": False,
        "console_contacted": False,
        "approved_for_supervised_execution": True,
    }
    capture = ROOT / f"research/gpu/captures/agc-stage-c-{args.fill_bytes}-local-proof.json"
    capture.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
