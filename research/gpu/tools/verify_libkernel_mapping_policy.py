#!/usr/bin/env python3
"""Pin the FW 12.02 direct-map versus batch-map protection-policy evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FILE_OFFSET_BIAS = 0x4000
EXPECTED_FILE_SHA256 = "d87cea22ab1e7c69e0f1ef4a381f4457106af4a6c6521400d76be0330a3291ef"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--libkernel", type=Path,
                        default=Path("research/gpu/dumps/system-libkernel.sprx"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    image = args.libkernel.read_bytes()
    if digest(image) != EXPECTED_FILE_SHA256:
        raise SystemExit("libkernel FW 12.02 dump hash mismatch")

    def va(start: int, end: int) -> bytes:
        return image[FILE_OFFSET_BIAS + start:FILE_OFFSET_BIAS + end]

    slices = {
        "map_direct_export_0x18520_0x18583": (va(0x18520, 0x18583), "c8cb79f96cd5d1e213227af6418a192a378380db8cee9196b4d2e09091772aba"),
        "map_direct_core_0x18590_0x187d6": (va(0x18590, 0x187D6), "06fe4945a827550e0a7eeb41b6870322140bab5d8a130dd4b7b3273fc9de9ed1"),
        "batch_map_export_0x18c30_0x18cd6": (va(0x18C30, 0x18CD6), "c735a71e77ac555dcce7760f4cf35bc4eda678299f43d25aca654351604018c1"),
    }
    for name, (blob, expected) in slices.items():
        if digest(blob) != expected:
            raise SystemExit(f"{name} hash mismatch")

    validation = bytes.fromhex(
        "4489f989f2252fdb9fff81e10cfcffff09c1"
        "488b45d04409e009f809c281e2ff3f000009ca"
    )
    if validation not in slices["map_direct_core_0x18590_0x187d6"][0]:
        raise SystemExit("MapDirectMemory protection-mask sequence missing")

    forbidden_low14 = 0xFC0C
    allowed_low14 = (~forbidden_low14) & 0x3FFF
    candidates = {}
    for value in (0x33, 0xF2, 0xCF2):
        rejected_bits = value & forbidden_low14
        candidates[f"0x{value:x}"] = {
            "rejected_bits": f"0x{rejected_bits:x}",
            "passes_protection_mask": rejected_bits == 0,
        }

    batch_forward = bytes.fromhex(
        "be100000004c89fa4489f1c745d400000000e8558ffeff"
    )
    if batch_forward not in slices["batch_map_export_0x18c30_0x18cd6"][0]:
        raise SystemExit("BatchMap forwarding sequence missing")

    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "source": str(args.libkernel),
        "source_sha256": digest(image),
        "console_contacted": False,
        "map_direct_export_offset": "0x18520",
        "batch_map_export_offset": "0x18c30",
        "map_direct_forbidden_protection_mask_low14": "0xfc0c",
        "map_direct_allowed_protection_mask_low14": f"0x{allowed_low14:x}",
        "candidates": candidates,
        "conclusion": (
            "0x33 and 0xf2 pass MapDirectMemory's protection mask; "
            "0xcf2 carries rejected bits 0xc00 and belongs to the distinct "
            "BatchMap encoding observed in San Andreas"
        ),
        "private_bit_names_resolved": False,
        "agc_command_fetch_with_0x33_proven": False,
        "phase0m_approved_for_deployment": False,
        "function_sha256": {name: expected for name, (_, expected) in slices.items()},
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
