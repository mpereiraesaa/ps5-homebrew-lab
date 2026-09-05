#!/usr/bin/env python3
"""Pin the native CPU-to-AGC visibility boundary without contacting the PS5."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EBOOT_BASE = 0x400000
EXPECTED_EBOOT_SHA256 = (
    "93749b4991d4b7a4536f7c5a85d31e3678443438bce800464955df4b03944066"
)

RANGES = {
    "submission_producer": (
        0x1F21FD0, 0x1F225D2,
        "190b9d353536035835b0607d9e433a740a062b10ecc7baae61538d20a1bada5f",
    ),
    "segment_rotation": (
        0x1F22770, 0x1F22940,
        "8559a40e3eaac363ce8bd0c4eb9a68f767dc7968d8cedf734bddabcc8ee94728",
    ),
    "submission_worker": (
        0x1F24BB0, 0x1F24E00,
        "0f9730414040b77c56231d4951c541702ea0b3ebd731fce3b59ed07ab604265c",
    ),
    "work_queue_dequeue": (
        0x1F24E00, 0x1F25040,
        "15397604b9635afa8671f9740e960b53bcf211608a61b22aefab236ae75d199b",
    ),
}

# Literal encodings sufficient to distinguish explicit x86 cache-line/global
# maintenance from the MFENCE instructions used by the lock-free CPU queue.
CACHE_MAINTENANCE_PREFIXES = {
    "wbinvd": bytes.fromhex("0f09"),
    "invd": bytes.fromhex("0f08"),
}
MFENCE = bytes.fromhex("0faef0")
LABEL_STORE = bytes.fromhex("4c894a2049c70101000000")
RELEASE_CALLSITE = bytes.fromhex(
    "488d7c2428be28000000b90100000041b80300000031d2"
    "6a006a026a016a006a006a02e858e7e902"
)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def addresses(blob: bytes, pattern: bytes, base: int) -> list[str]:
    return [hex(base + i) for i in range(len(blob)) if blob.startswith(pattern, i)]


def cache_line_instruction_addresses(blob: bytes, base: int) -> list[str]:
    """Find CLFLUSH/CLFLUSHOPT/CLWB ModRM forms, excluding MFENCE et al."""
    found: list[str] = []
    for i in range(len(blob) - 2):
        prefix = blob[i:i + 3]
        if prefix[:2] == b"\x0f\xae" and not (i > 0 and blob[i - 1] == 0x66):
            modrm = prefix[2]
            if (modrm >> 6) != 3 and ((modrm >> 3) & 7) == 7:
                found.append(hex(base + i))
        if i + 3 < len(blob) and prefix == b"\x66\x0f\xae":
            modrm = blob[i + 3]
            if (modrm >> 6) != 3 and ((modrm >> 3) & 7) in (6, 7):
                found.append(hex(base + i))
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--eboot", type=Path,
        default=Path("research/gpu/dumps/san-andreas-eboot-runtime.bin"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    image = args.eboot.read_bytes()
    if digest(image) != EXPECTED_EBOOT_SHA256:
        raise SystemExit("authorized San Andreas runtime eboot hash mismatch")

    evidence: dict[str, object] = {}
    for name, (start, end, expected) in RANGES.items():
        blob = image[start - EBOOT_BASE:end - EBOOT_BASE]
        if digest(blob) != expected:
            raise SystemExit(f"{name} hash mismatch")
        evidence[name] = {
            "range": [hex(start), hex(end)],
            "sha256": expected,
            "explicit_cache_maintenance_encodings": {
                "cache_line_flush_or_writeback":
                    cache_line_instruction_addresses(blob, start),
                **{
                    label: addresses(blob, opcode, start)
                    for label, opcode in CACHE_MAINTENANCE_PREFIXES.items()
                },
            },
            "mfence_encodings": addresses(blob, MFENCE, start),
        }

    producer_start = RANGES["submission_producer"][0]
    producer = image[
        producer_start - EBOOT_BASE:RANGES["submission_producer"][1] - EBOOT_BASE
    ]
    if addresses(producer, LABEL_STORE, producer_start) != ["0x1f2246d"]:
        raise SystemExit("CPU=1 ownership label initialization changed")
    if addresses(producer, RELEASE_CALLSITE, producer_start) != ["0x1f224a0"]:
        raise SystemExit("ownership RELEASE_MEM callsite changed")

    direct_path_names = (
        "submission_producer", "segment_rotation", "submission_worker"
    )
    if any(
        any(items for items in evidence[name]["explicit_cache_maintenance_encodings"].values())
        for name in direct_path_names
    ):
        raise SystemExit("explicit cache-maintenance encoding appeared in native path")
    if any(evidence[name]["mfence_encodings"] for name in direct_path_names):
        raise SystemExit("unexpected MFENCE appeared in producer/submit path")

    dequeue_mfences = evidence["work_queue_dequeue"]["mfence_encodings"]
    if dequeue_mfences != [
        "0x1f24e42", "0x1f24e49", "0x1f24e4c", "0x1f24e56",
        "0x1f24e92", "0x1f24e98", "0x1f24e9b", "0x1f24ea2",
    ]:
        raise SystemExit("CPU work-queue MFENCE pattern changed")

    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "source": str(args.eboot),
        "source_sha256": digest(image),
        "console_contacted": False,
        "ranges": evidence,
        "ownership_label_cpu_store": "mov qword [label],1 at 0x1f22471",
        "ownership_release_mem_call": "0x1f224c3",
        "native_command_mapping_policy": "BatchMap protection 0x0cf2",
        "phase0m_mapping_policy": "MapDirectMemory protection 0x0f2 flags 0x10",
        "explicit_cache_line_or_global_flush_in_native_direct_path": False,
        "cpu_queue_mfence_present": True,
        "cpu_queue_mfence_interpretation": (
            "CPU producer/consumer ordering only; not cache-line clean/invalidate"
        ),
        "strong_inference": (
            "native command visibility is supplied by the 0x0cf2 mapping policy, "
            "the driver submit boundary, or both; no explicit x86 cache-maintenance "
            "instruction occurs in the pinned producer/rotation/submit-worker path"
        ),
        "transfer_to_phase0m_proven": False,
        "reason_transfer_unproven": (
            "phase0m uses 0x0f2/flags 0x10 rather than the native command pool's "
            "BatchMap-only 0x0cf2 policy"
        ),
        "phase0m_approved_for_deployment": False,
        "submitted_or_executed": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
