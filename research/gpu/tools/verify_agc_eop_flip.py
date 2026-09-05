#!/usr/bin/env python3
"""Pin the firmware-12.02 AgcDriver end-of-pipe VideoOut bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


START = 0x71D0
END = 0x744C
FILE_BIAS = 0x4000
WRAPPER_START = 0x7B70
WRAPPER_END = 0x7C2C


def expect(blob: bytes, va: int, expected: bytes, label: str) -> None:
    actual = blob[FILE_BIAS + va:FILE_BIAS + va + len(expected)]
    if actual != expected:
        raise SystemExit(f"{label} changed at {va:#x}: {actual.hex()}")


def rel32_target(blob: bytes, call_va: int) -> int:
    offset = FILE_BIAS + call_va
    if blob[offset] != 0xE8:
        raise SystemExit(f"expected CALL rel32 at {call_va:#x}")
    return call_va + 5 + struct.unpack_from("<i", blob, offset + 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", type=Path,
                        default=Path("research/gpu/dumps/system-libSceAgcDriver.sprx"))
    parser.add_argument("--runtime", type=Path,
                        default=Path("research/gpu/dumps/game-libSceAgcDriver.sprx.bin"))
    parser.add_argument("--system-agc", type=Path,
                        default=Path("research/gpu/dumps/system-libSceAgc.sprx"))
    parser.add_argument("--runtime-agc", type=Path,
                        default=Path("research/gpu/dumps/game-libSceAgc.sprx.bin"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    system = args.system.read_bytes()
    runtime = args.runtime.read_bytes()
    system_agc = args.system_agc.read_bytes()
    runtime_agc = args.runtime_agc.read_bytes()
    function = system[FILE_BIAS + START:FILE_BIAS + END]
    if function != runtime[START:END]:
        raise SystemExit("runtime AgcDriver EOP bridge differs from system module")
    wrapper = system_agc[FILE_BIAS + WRAPPER_START:FILE_BIAS + WRAPPER_END]
    if wrapper != runtime_agc[WRAPPER_START:WRAPPER_END]:
        raise SystemExit("runtime sceAgcDcbSetFlip wrapper differs from system module")
    # The DCB wrapper always passes EDX=0 as the driver's queue/event selector.
    if system_agc[FILE_BIAS + 0x7C09:FILE_BIAS + 0x7C0B] != bytes.fromhex("31d2"):
        raise SystemExit("sceAgcDcbSetFlip no longer selects driver mode zero")
    wrapper_call = 0x7C0E
    wrapper_target = wrapper_call + 5 + struct.unpack_from(
        "<i", system_agc, FILE_BIAS + wrapper_call + 1
    )[0]
    if system_agc[FILE_BIAS + wrapper_call] != 0xE8 or wrapper_target != 0x16DF0:
        raise SystemExit("sceAgcDcbSetFlip driver thunk changed")

    calls = {
        "submit_eop_flip": (0x724C, 0xB820),
        "get_buffer_label_address": (0x726B, 0xB810),
        "get_videoout_state": (0x72AC, 0xB830),
        "reserve_release_mem": (0x7349, 0x6CB0),
    }
    for label, (site, target) in calls.items():
        actual = rel32_target(system, site)
        if actual != target:
            raise SystemExit(f"{label} call target changed: {actual:#x}")

    expect(system, 0x7372, bytes.fromhex("c70481004906c0"),
           "RELEASE_MEM header store")
    expect(system, 0x73A0, bytes.fromhex(
        "488b75a08b55b083e2fc8954810c8b55b489548110895c8114"
        "c744811800000000baffffff0f2355b88954811c"
    ), "flip label/payload stores")
    error = b"sceVideoOutSubmitEopFlip failed"
    if system.count(error) != 1:
        raise SystemExit("SubmitEopFlip diagnostic string missing or ambiguous")
    expect(system, 0x71B0, bytes.fromhex("b840000000c3"),
           "DCB SetFlip maximum-size query")

    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "function": {
            "offset": hex(START),
            "size": END - START,
            "sha256": hashlib.sha256(function).hexdigest(),
            "system_runtime_equal": True,
        },
        "dcb_wrapper": {
            "nid": "YUeqkyT7mEQ",
            "name": "sceAgcDcbSetFlip",
            "offset": hex(WRAPPER_START),
            "size": WRAPPER_END - WRAPPER_START,
            "sha256": hashlib.sha256(wrapper).hexdigest(),
            "system_runtime_equal": True,
            "driver_thunk": "0x16df0",
            "driver_mode": 0,
        },
        "calls": {name: {"site": hex(site), "target": hex(target)}
                  for name, (site, target) in calls.items()},
        "release_mem_header": "0xc0064900",
        "dcb_graphics_release_mem_dw1": "0x0620062f",
        "direct_driver_builder": {
            "nid": "cwbxjPSJ7WQ",
            "max_dwords": 64,
            "abi_from_wrapper": [
                "writer_cursor_pointer",
                "capacity_dwords",
                "driver_mode_zero",
                "videoout_handle",
                "display_buffer_index",
                "flip_mode",
                "flip_arg_u64_on_stack",
            ],
            "abi_static_proven": True,
            "homebrew_dlsym_and_call_proven": False,
            "pure_packet_builder": False,
            "videoout_submit_eop_flip_occurs_before_packet_emit": 0x724C < 0x7372,
            "build_only_with_live_handle_allowed": False,
            "transaction_required": "build SetFlip then submit that same stream and retain state through completion",
        },
        "gfx10_public_field_correlation": {
            "event_type": "0x2f (CS_DONE)",
            "event_index": "6 (shader_done)",
            "gcr_cntl": "0x200 (GL2 writeback)",
            "warning": "PAL treats cache sync on EOS as noncanonical; retain PS5-specific uncertainty",
        },
        "gl2_writeback_bit_static_proven": True,
        "full_display_coherency_proven": False,
        "valid_buffer_index_uses_label_base_plus_index_times_8": True,
        "valid_buffer_index_payload": 1,
        "negative_buffer_index_payload": 0,
        "submit_eop_flip_metadata_mask": "0x0fffffff",
        "eop_flip_bridge_static_proven": True,
        "exact_cache_event_semantics_proven": False,
        "homebrew_hardware_execution_proven": False,
        "console_contacted": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
