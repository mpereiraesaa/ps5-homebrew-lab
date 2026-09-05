#!/usr/bin/env python3
"""Compare the default graphics-queue object in authorized runtime dumps."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


QUEUE_OFFSET = 0x228B8
QUEUE_BYTES = 0x50
DRIVER_STATE_OFFSET = 0x22908
DRIVER_STATE_BYTES = 0x20
SUBMIT_DCB_OFFSET = 0x2960
SUBMIT_DCB = bytes.fromhex(
    "48 89 fe 48 8d 3d 4e ff 01 00 e9 41 f0 ff ff"
)


def parse(path: Path) -> dict[str, object]:
    blob = path.read_bytes()
    if blob[SUBMIT_DCB_OFFSET : SUBMIT_DCB_OFFSET + len(SUBMIT_DCB)] != SUBMIT_DCB:
        raise SystemExit(f"{path}: SubmitDcb wrapper mismatch")
    q = blob[QUEUE_OFFSET : QUEUE_OFFSET + QUEUE_BYTES]
    state = blob[DRIVER_STATE_OFFSET : DRIVER_STATE_OFFSET + DRIVER_STATE_BYTES]
    if len(q) != QUEUE_BYTES:
        raise SystemExit(f"{path}: queue object is outside dump")
    if len(state) != DRIVER_STATE_BYTES:
        raise SystemExit(f"{path}: driver state is outside dump")
    u32 = lambda off: struct.unpack_from("<I", q, off)[0]
    u64 = lambda off: struct.unpack_from("<Q", q, off)[0]
    if u32(0) != 0x38:
        raise SystemExit(f"{path}: unexpected queue header {u32(0):#x}")
    return {
        "file": str(path),
        "header_size": u32(0),
        "queue_type_or_mode": u32(4),
        "gc_handle_nonzero": struct.unpack_from("<I", state, 4)[0] != 0,
        "ioctl_process_class_low16": struct.unpack_from("<I", state, 8)[0],
        "ioctl_process_flags_high16": struct.unpack_from("<I", state, 12)[0],
        "token_nonzero": u64(8) != 0,
        "field_10_nonzero": u64(0x10) != 0,
        "field_18_nonzero": u64(0x18) != 0,
        "field_20_nonzero": u64(0x20) != 0,
        "field_28_nonzero": u64(0x28) != 0,
        "field_30_nonzero": u64(0x30) != 0,
        "lock_context_nonzero": u64(0x38) != 0,
        "aux_40_nonzero": u64(0x40) != 0,
        "created_sentinel": q[0x48],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--menu",
        type=Path,
        default=Path("research/gpu/dumps/menu-libSceAgcDriver.sprx.bin"),
    )
    parser.add_argument(
        "--game",
        type=Path,
        default=Path("research/gpu/dumps/game-libSceAgcDriver.sprx.bin"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    menu = parse(args.menu)
    game = parse(args.game)
    result = {
        "firmware": "12.02",
        "queue_offset": hex(QUEUE_OFFSET),
        "submit_dcb_selects_this_object": True,
        "snapshots": {"AgcCompositor": menu, "SanAndreas": game},
        "invariants": {
            "header_size_equal": menu["header_size"] == game["header_size"] == 0x38,
            "lock_context_present_both": bool(menu["lock_context_nonzero"])
            and bool(game["lock_context_nonzero"]),
            "context_dependent_mode": menu["queue_type_or_mode"]
            != game["queue_type_or_mode"],
            "ioctl_class_routes_to_expected_queue_both":
            menu["ioctl_process_class_low16"] == 1
            and menu["queue_type_or_mode"] == 3
            and game["ioctl_process_class_low16"] == 0
            and game["queue_type_or_mode"] == 0,
            "gc_handle_present_both": bool(menu["gc_handle_nonzero"])
            and bool(game["gc_handle_nonzero"]),
            "created_sentinel_exact_both": menu["created_sentinel"] == 1
            and game["created_sentinel"] == 1,
        },
        "types_semantically_proven": False,
        "submitted_or_executed": False,
    }
    if not all(result["invariants"].values()):
        raise SystemExit("queue snapshot invariant failed")
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
