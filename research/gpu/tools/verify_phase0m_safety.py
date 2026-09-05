#!/usr/bin/env python3
"""Static deployment gate for the phase 0M draft. Never contacts the PS5."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import struct
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path,
                        default=Path("legacy/probes/ps5-agc-phase0/driver_first_submit.c"))
    parser.add_argument("--elf", type=Path,
                        default=Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0m-first-submit.elf"))
    parser.add_argument("--makefile", type=Path,
                        default=Path("legacy/probes/ps5-agc-phase0/Makefile"))
    parser.add_argument("--supervisor", type=Path,
                        default=Path("tools/night_supervisor.py"))
    parser.add_argument("--submit-proof", type=Path,
                        default=Path("research/gpu/captures/agc-queue-submit-proof.json"))
    parser.add_argument("--fence-proof", type=Path,
                        default=Path("research/gpu/captures/agc-release-fence-proof.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = args.source.read_text()
    elf = args.elf.read_bytes()
    makefile = args.makefile.read_text()
    supervisor = args.supervisor.read_text()
    submit_proof = json.loads(args.submit_proof.read_text())
    fence_proof = json.loads(args.fence_proof.read_text())
    ioctl_proof = submit_proof.get("class0_submit_ioctl", {})
    if (ioctl_proof.get("request") != "0xc0188132" or
            ioctl_proof.get("submit_success_proves_gpu_completion") is not False or
            ioctl_proof.get("kernel_pinning_or_command_copy_proven") is not False):
        raise SystemExit("phase 0M lacks the pinned class-0 asynchronous-submit proof")
    if (fence_proof.get("ownership_protocol_proven") is not True or
            fence_proof.get("ownership_cpu_initial") != 1 or
            fence_proof.get("ownership_gpu_final") != 0 or
            fence_proof.get("ownership_data_sel") != 2 or
            fence_proof.get("submitted_or_executed") is not False or
            fence_proof.get("homebrew_gpu_mapping_and_submit_proven") is not False):
        raise SystemExit("phase 0M lacks the bounded ownership-fence proof")
    required = [
        '#define SUBMIT_NID "UglJIZjGssM"',
        "const uint32_t stream[15]",
        "0xc0055000, 0xc0300000",
        "0xc0064900, 0x06000528, 0x42010000",
        "struct submit_info info = {(const uint32_t *)b, 15, 0",
        "sceKernelReserveVirtualRange(&reserved, REGION_SIZE, 0, REGION_ALIGN)",
        "REGION_SIZE, REGION_ALIGN, 0x0c",
        "REGION_SIZE, 0x0f2, 0x10",
        "mapping != reserved",
        "read32(state + 0x08) == 0",
        "read64(state + 0x50) == base + CLASS0_CALLBACK_OFFSET",
        "read32(state + 0x120) == 0",
        "read32(state + 0x1cc) == 0",
        "submit_started = 1;",
        "__atomic_thread_fence(__ATOMIC_SEQ_CST);",
        "__atomic_load_n(fence, __ATOMIC_ACQUIRE)",
        "PARKED_AFTER_SUBMIT; resources retained; DO_NOT_CLOSE_FAKE00000",
        "PARKED_SUBMIT_ERROR; enqueue state unknown; DO_NOT_CLOSE_FAKE00000",
        "PARKED_FENCE_TIMEOUT; resources retained; DO_NOT_CLOSE_FAKE00000",
        '"command stream must not overlap target"',
        '"target alignment"',
        '"fence alignment"',
        '"target must not overlap fence"',
        '"fence must remain inside direct-memory mapping"',
    ]
    missing = [item for item in required if item not in source]
    if missing:
        raise SystemExit(f"phase 0M source gate missing: {missing}")
    all_recipe = makefile.split("all:", 1)[1].split("\n\n", 1)[0]
    if "phase0m" in all_recipe:
        raise SystemExit("phase 0M must not be in the default build")
    if "run-first-submit" in supervisor or "run_first_submit" in supervisor:
        raise SystemExit("phase 0M must not be runnable from the supervisor")
    if "require_phase0m_cleanup_safe" not in supervisor or \
       "classify_phase0m_log" not in supervisor:
        raise SystemExit("supervisor lacks the phase 0M cleanup refusal gate")

    symbols = subprocess.check_output(
        ["readelf", "-Ws", str(args.elf)], text=True
    )
    undefined = sorted({line.split()[-1] for line in symbols.splitlines()
                        if " UND " in f" {line} " and line.split()[-1] != "UND"})
    if b"UglJIZjGssM" not in elf or b"libSceAgcDriver.sprx" not in elf:
        raise SystemExit("phase 0M ELF lacks the pinned driver/NID strings")

    # This SDK emits .text at file offset 0x4000, virtual address zero. Pin the
    # optimized stores that assemble all 15 DWORDs, including dynamic pointers.
    def require_text(virtual: int, expected: bytes, label: str) -> None:
        actual = elf[0x4000 + virtual:0x4000 + virtual + len(expected)]
        if actual != expected:
            raise SystemExit(
                f"{label} mismatch at text+{virtual:#x}: "
                f"expected={expected.hex()} actual={actual.hex()}"
            )

    require_text(0x3FA, bytes.fromhex(
        "488d7dc0be00000200b90000010031d2"), "ReserveVirtualRange call setup")
    require_text(0x42C, bytes.fromhex(
        "488d4d98bf00000200be00000100ba0c000000"),
        "type=0x0c allocation setup")
    require_text(0x45A, bytes.fromhex(
        "488d7da0be00000200baf2000000b9100000004531c9"),
        "fixed-VA prot=0xf2 flags=0x10 map setup")
    require_text(0x51C, bytes.fromhex("c5f81100"), "DMA prefix store")
    require_text(0x520, bytes.fromhex("897010"), "target-low store")
    require_text(0x528, bytes.fromhex("894814"), "target-high store")
    require_text(0x52B, bytes.fromhex("c5fa7f4818"), "packet join store")
    require_text(0x530, bytes.fromhex("44896028"), "fence-low store")
    require_text(0x534, bytes.fromhex("89502c"), "fence-high store")
    require_text(0x537, bytes.fromhex("48c7403000000000"), "tail zero qword")
    require_text(0x53F, bytes.fromhex("c7403800000000"), "tail zero dword")
    require_text(0x562, bytes.fromhex("48c78568ffffff0f000000"),
                 "size=15 and field_0c=0 descriptor store")
    require_text(0x5A1, bytes.fromhex("0faef0"),
                 "CPU ordering MFENCE immediately before submit")
    dma_prefix = struct.pack("<4I", 0xC0055000, 0xC0300000, 0, 0)
    packet_join = struct.pack(
        "<4I", 4, 0xC0064900, 0x06000528, 0x42010000
    )
    if elf.count(dma_prefix) != 1 or elf.count(packet_join) != 1:
        raise SystemExit("compiled packet constants are missing or ambiguous")
    forbidden_undefined = [name for name in undefined
                           if "VideoOut" in name or "Submit" in name]
    if forbidden_undefined:
        raise SystemExit(f"unexpected direct imports: {forbidden_undefined}")

    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "elf_sha256": hashlib.sha256(elf).hexdigest(),
        "elf_size": len(elf),
        "console_contacted": False,
        "deployed": False,
        "submitted": False,
        "default_build": False,
        "supervisor_action_present": False,
        "supervisor_cleanup_refusal_gate_present": True,
        "stream_dwords": 15,
        "compiled_stream_layout_verified": True,
        "submit_info_field_0c": 0,
        "class0_runtime_gate": {
            "process_class": 0,
            "selector": 0,
            "callback_offset": "0x1100",
            "lazy_registration_counter": 0,
        },
        "target_bytes": 4,
        "single_mapping_layout": {
            "region_bytes": 0x20000,
            "stream_offset": 0,
            "stream_bytes": 15 * 4,
            "target_offset": 0x1000,
            "target_alignment": 4,
            "fence_offset": 0x1008,
            "fence_alignment": 8,
            "non_overlapping_and_in_range": True,
        },
        "memory_policy": "reserved fixed VA; type=0x0c; prot=0xf2; flags=0x10",
        "fence_initial": 1,
        "game_ownership_fence_static_proven": True,
        "ownership_data_sel": 2,
        "ownership_gpu_final": 0,
        "homebrew_gpu_visibility_proven": False,
        "cpu_gpu_cache_coherency_proven": False,
        "cpu_cache_maintenance_api_proven": False,
        "atomic_fence_is_cache_maintenance": False,
        "cpu_submit_ordering_mfence_compiled": True,
        "runtime_blocker": (
            "prove the direct-memory CPU/GPU coherency contract or the exact "
            "cache clean/invalidate sequence before deployment"
        ),
        "success_requires_fence_zero": True,
        "timeout_policy": "park forever retaining process, module, and mapping",
        "submit_error_policy": "park forever because enqueue state is unknown",
        "class0_submit_ioctl": "0xc0188132",
        "submit_success_proves_gpu_completion": False,
        "kernel_pinning_or_command_copy_proven": False,
        "cleanup_requires_observed_fence": True,
        "automatic_close_after_uncertain_submit": False,
        "approved_for_deployment": False,
        "undefined_symbols": undefined,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
