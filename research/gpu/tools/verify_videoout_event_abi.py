#!/usr/bin/env python3
"""Pin the firmware-12.02 VideoOut flip-event data ABI."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FILE_BIAS = 0x4000
START = 0x128F0
END = 0x12941


def expect(blob: bytes, offset: int, encoded: str, label: str) -> None:
    expected = bytes.fromhex(encoded)
    actual = blob[FILE_BIAS + offset:FILE_BIAS + offset + len(expected)]
    if actual != expected:
        raise SystemExit(f"{label} changed at {offset:#x}: {actual.hex()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--system", type=Path,
        default=Path("research/gpu/dumps/system-libSceVideoOut.sprx"),
    )
    parser.add_argument(
        "--runtime", type=Path,
        default=Path("research/gpu/dumps/san-andreas-libSceVideoOut.sprx.bin"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    system = args.system.read_bytes()
    runtime = args.runtime.read_bytes()
    function = system[FILE_BIAS + START:FILE_BIAS + END]
    if function != runtime[START:END]:
        raise SystemExit("runtime GetEventData differs from system module")

    pins = {
        "null_event_check": (0x128F0, "4885ff"),
        "null_output_check": (0x128F6, "4885f6"),
        "videoout_filter_at_event_plus_8": (0x12905, "66837f08f3"),
        "packed_data_at_event_plus_0x10": (0x12911, "488b4710"),
        "event_ident_at_event_plus_6": (0x12915, "0fb75706"),
        "extract_upper_48_bits": (0x12923, "4889c148c1e910"),
        "flip_internal_ident_6": (0x12934, "83fa06"),
        "write_int64_result": (0x1293D, "48893e"),
    }
    for label, (offset, encoded) in pins.items():
        expect(system, offset, encoded, label)

    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "module": {
            "sha256": hashlib.sha256(system).hexdigest(),
            "bytes": len(system),
        },
        "function": {
            "nid": "rWUTcKdkUzQ",
            "name": "sceVideoOutGetEventData",
            "offset": hex(START),
            "size": END - START,
            "sha256": hashlib.sha256(function).hexdigest(),
            "system_runtime_equal": True,
        },
        "abi": {
            "rdi": "const struct kevent *event",
            "rsi": "int64_t *flip_arg_out",
            "videoout_filter": "0xfff3 at event+0x08",
            "internal_flip_event_ident": 6,
            "ident_offset": "0x06",
            "packed_event_data_offset": "0x10",
            "flip_arg_encoding": "signed upper 48 bits of packed event data",
            "extraction": "event_data >> 16 with sign extension for ident 6",
            "static_proven": True,
        },
        "completion_use": {
            "wait_equeue_event_can_be_matched_to_exact_flip_arg": True,
            "event_id_and_filter_are_validated_by_library": True,
            "event_count_is_not_a_substitute_for_flip_arg": True,
            "homebrew_runtime_call_proven": False,
        },
        "public_ps4_correlation": {
            "source": "https://github.com/shadps4-emu/shadPS4/blob/main/src/core/libraries/videoout/video_out.cpp",
            "used_as_ps5_proof": False,
            "note": "correlation only; all PS5 claims above are byte-pinned locally",
        },
        "pins": {
            label: {"offset": hex(offset), "bytes": encoded}
            for label, (offset, encoded) in pins.items()
        },
        "console_contacted_for_system_module_read": True,
        "console_process_attached": False,
        "console_memory_read": False,
        "console_written": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
