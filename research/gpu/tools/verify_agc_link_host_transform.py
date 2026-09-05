#!/usr/bin/env python3
"""Execute the pinned, self-contained LinkShaders transform on the host.

The module and authorized inputs are mapped privately. Only hashes, write ranges,
and canary results are emitted; no module, header, shader, CX, or UC bytes are
written to disk.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import mmap
import struct
from pathlib import Path


MODULE_SHA = "5e51617fb06c16c745c549101481b4e079b902f7c630edc3d0e43aa2a56fcf84"
FUNCTION_OFFSET = 0x103F0
CX_BYTES, UC_BYTES, GUARD = 0x110, 0x18, 32
POINTER_FIELDS = (0x08, 0x18, 0x20, 0x28, 0x30, 0x38)
NESTED_FIELDS = (0, 8, 16, 24, 32)


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def shader(asset_root: Path, header_name: str, code_name: str):
    raw = bytearray((asset_root / header_name).read_bytes())
    header = ctypes.create_string_buffer(bytes(raw), len(raw))
    header_address = ctypes.addressof(header)
    code_bytes = (asset_root / code_name).read_bytes()
    code = ctypes.create_string_buffer(code_bytes, len(code_bytes))
    struct.pack_into("<Q", header, 0x10, ctypes.addressof(code))
    for field in POINTER_FIELDS:
        relative = struct.unpack_from("<Q", raw, field)[0]
        if relative:
            struct.pack_into("<Q", header, field, header_address + field + relative)
    user_relative = struct.unpack_from("<Q", raw, 0x08)[0]
    if user_relative:
        user_offset = 0x08 + user_relative
        user_address = header_address + user_offset
        for field in NESTED_FIELDS:
            relative = struct.unpack_from("<Q", raw, user_offset + field)[0]
            if relative:
                struct.pack_into("<Q", header, user_offset + field,
                                 user_address + field + relative)
    return header, code


def guarded(size: int, fill: int):
    buffer = ctypes.create_string_buffer(b"\xC3" * GUARD + bytes([fill]) * size + b"\x3C" * GUARD,
                                         GUARD + size + GUARD)
    return buffer, ctypes.addressof(buffer) + GUARD


def run_case(function, asset_root: Path, *, cx_present=True, uc_present=True,
             pre_present=True, pixel_present=True, primitive=6, fill=0xA5) -> dict:
    pre, pre_code = shader(asset_root, "geometry.header.bin", "geometry.text.bin")
    pixel, pixel_code = shader(asset_root, "pixel.header.bin", "pixel.text.linear-buffer.bin")
    pre_before, pixel_before = bytes(pre), bytes(pixel)
    cx, cx_address = guarded(CX_BYTES, fill)
    uc, uc_address = guarded(UC_BYTES, fill)
    result = function(cx_address if cx_present else None,
                      uc_address if uc_present else None, None,
                      ctypes.addressof(pre) if pre_present else None,
                      ctypes.addressof(pixel) if pixel_present else None, primitive)

    def output(buffer, size, present):
        raw = bytes(buffer)
        payload = raw[GUARD:GUARD + size]
        return {
            "present": present,
            "sha256": sha(payload) if present else None,
            "prefix_canary_intact": raw[:GUARD] == b"\xC3" * GUARD,
            "suffix_canary_intact": raw[GUARD + size:] == b"\x3C" * GUARD,
        }

    return {
        "return": result, "primitive": primitive,
        "inputs_unchanged_after_relocation": bytes(pre) == pre_before and bytes(pixel) == pixel_before,
        "cx": output(cx, CX_BYTES, cx_present), "uc": output(uc, UC_BYTES, uc_present),
        "retained_objects": len((pre, pre_code, pixel, pixel_code)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path,
                        default=Path("research/gpu/dumps/game-libSceAgc.sprx.bin"))
    parser.add_argument("--assets", type=Path,
                        default=Path("third_party/ProsperoTV/assets/private"))
    parser.add_argument("--output", type=Path,
                        default=Path("research/gpu/captures/agc-link-host-transform.json"))
    args = parser.parse_args()
    module = args.module.read_bytes()
    if sha(module) != MODULE_SHA:
        raise SystemExit("runtime module hash mismatch")
    mapping = mmap.mmap(-1, len(module), prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
    mapping.write(module)
    base = ctypes.addressof(ctypes.c_char.from_buffer(mapping))
    prototype = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_uint32)
    function = prototype(base + FUNCTION_OFFSET)
    cases = {
        "selected_pair_a": run_case(function, args.assets),
        "selected_pair_b": run_case(function, args.assets, fill=0x5A),
        "cx_only": run_case(function, args.assets, uc_present=False),
        "uc_only": run_case(function, args.assets, cx_present=False),
        "no_pre_raster": run_case(function, args.assets, pre_present=False),
        "no_pixel": run_case(function, args.assets, pixel_present=False),
        "no_shaders": run_case(function, args.assets, pre_present=False, pixel_present=False),
        "primitive_zero": run_case(function, args.assets, primitive=0),
        "primitive_nineteen": run_case(function, args.assets, primitive=19),
    }
    if (cases["selected_pair_a"]["return"] != cases["selected_pair_b"]["return"] or
            cases["selected_pair_a"]["cx"]["sha256"] != cases["selected_pair_b"]["cx"]["sha256"] or
            cases["selected_pair_a"]["uc"]["sha256"] != cases["selected_pair_b"]["uc"]["sha256"]):
        raise SystemExit("selected transform is nondeterministic")
    if any(case["return"] != 0 for case in cases.values()):
        raise SystemExit("a host transform did not return zero")
    for case in cases.values():
        if not case["inputs_unchanged_after_relocation"]:
            raise SystemExit("LinkShaders mutated an input")
        for output in (case["cx"], case["uc"]):
            if not output["prefix_canary_intact"] or not output["suffix_canary_intact"]:
                raise SystemExit("LinkShaders crossed an output boundary")
    result = {
        "schema": 1, "firmware_scope": "12.02", "module_sha256": MODULE_SHA,
        "function_offset": hex(FUNCTION_OFFSET), "execution": "isolated host process only",
        "cases": cases, "selected_pair_deterministic": True,
        "selected_outputs_fully_overwritten_by_prefill_differential": True,
        "selected_cx_sha256": cases["selected_pair_a"]["cx"]["sha256"],
        "selected_uc_sha256": cases["selected_pair_a"]["uc"]["sha256"],
        "all_returns_zero": True, "all_canaries_intact": True,
        "all_inputs_unchanged": True, "raw_outputs_emitted": False,
        "console_contacted": False, "gpu_submission": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
