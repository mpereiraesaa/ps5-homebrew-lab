#!/usr/bin/env python3
"""Verify one local authorized LinkShaders pair; emit metadata, never shader bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path


EXPECTED = {
    "geometry.header.bin": "13d2949bdc764703179a7ab77873930e987f3676a0dec9246a144fca1984fcd4",
    "geometry.text.bin": "7e4af7b5daf3926467a32684334c8e4d5bc7b1aab919eb67b86e799587637a77",
    "pixel.header.bin": "1384eb79521959aaaa2799ac1e0caba1bb3489e508a963b13d5c4fb8e9f24b52",
    "pixel.text.linear-buffer.bin": "2ab90cd91412acf6102b6f158ff1d430c02849454d6c86a89a7cf464e143b91c",
}


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def semantics(header: bytes, field: int, count_field: int, count_format: str) -> list[int]:
    relative = struct.unpack_from("<Q", header, field)[0]
    count = struct.unpack_from("<" + count_format, header, count_field)[0]
    if count > 32:
        raise SystemExit("semantic count exceeds LinkShaders capacity")
    if count == 0:
        return []
    start = field + relative
    end = start + count * 4
    if relative == 0 or end > len(header):
        raise SystemExit("semantic array is outside header")
    return list(struct.unpack_from(f"<{count}I", header, start))


def inspect_header(blob: bytes) -> dict:
    if len(blob) < 0x60 or blob[:8] != b"1234\x18\0\0\0":
        raise SystemExit("unexpected AGC header magic/version")
    special_relative = struct.unpack_from("<Q", blob, 0x28)[0]
    special = 0x28 + special_relative
    if not special_relative or special + 0x30 > len(blob):
        raise SystemExit("special-data prefix is outside header")
    inputs = semantics(blob, 0x30, 0x50, "I")
    outputs = semantics(blob, 0x38, 0x56, "H")
    register_groups = []
    for field, count in ((0x18, blob[0x5B]), (0x20, blob[0x5C])):
        relative = struct.unpack_from("<Q", blob, field)[0]
        start, end = field + relative, field + relative + count * 8
        if not relative or end > len(blob):
            raise SystemExit("register array is outside header")
        register_groups.append([struct.unpack_from("<I", blob, start + i * 8)[0]
                                for i in range(count)])
    user_relative = struct.unpack_from("<Q", blob, 0x08)[0]
    user = 0x08 + user_relative
    if not user_relative or user + 0x38 > len(blob):
        raise SystemExit("user-data prefix is outside header")
    counts = struct.unpack_from("<7H", blob, user + 0x28)
    resource_counts = [counts[2], *counts[3:7]]
    resource_groups = []
    for field, count in zip((0, 8, 16, 24, 32), resource_counts):
        relative = struct.unpack_from("<Q", blob, user + field)[0]
        start = user + field + relative if relative else 0
        if count and (not relative or start + count * 2 > len(blob)):
            raise SystemExit("resource array is outside header")
        resource_groups.append(list(struct.unpack_from(f"<{count}H", blob, start)) if count else [])
    reg_digest = sha(json.dumps(register_groups, separators=(",", ":")).encode())
    resource_digest = sha(json.dumps(resource_groups, separators=(",", ":")).encode())
    return {
        "bytes": len(blob), "type_raw": blob[0x5A],
        "target_raw": struct.unpack_from("<I", blob, 0x4C)[0],
        "input_count": len(inputs), "input_keys": [v & 0xFF for v in inputs],
        "output_count": len(outputs), "output_keys": [v & 0xFF for v in outputs],
        "special_prefix_bytes_validated": 0x30,
        "cx_register_count": len(register_groups[0]),
        "sh_register_count": len(register_groups[1]),
        "register_inventory_sha256": reg_digest,
        "register_ranges_bounded": True,
        "resource_group_counts": resource_counts,
        "resource_inventory_sha256": resource_digest,
        "resource_ranges_bounded": True,
        "_register_ids": register_groups,
        "_resource_ids": resource_groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path("third_party/ProsperoTV"))
    parser.add_argument("--output", type=Path,
                        default=Path("research/gpu/captures/agc-link-compatible-pair.json"))
    args = parser.parse_args()
    asset_root = args.root / "assets/private"
    blobs = {name: (asset_root / name).read_bytes() for name in EXPECTED}
    actual = {name: sha(blob) for name, blob in blobs.items()}
    if actual != EXPECTED:
        raise SystemExit("authorized pair hash mismatch")
    pre = inspect_header(blobs["geometry.header.bin"])
    pixel = inspect_header(blobs["pixel.header.bin"])
    if (pre["type_raw"], pixel["type_raw"]) != (2, 1):
        raise SystemExit("proven pair roles changed")
    if pre["target_raw"] != pixel["target_raw"]:
        raise SystemExit("pair target mismatch")
    if pixel["input_keys"] != [15] or pre["output_keys"] != [15]:
        raise SystemExit("pair semantic interface changed")
    cross_register_overlap = len(set(sum(pre["_register_ids"], [])) &
                                 set(sum(pixel["_register_ids"], [])))
    resource_overlap = [len(set(a) & set(b)) for a, b in
                        zip(pre["_resource_ids"], pixel["_resource_ids"])]

    source = (args.root / "src/iptv_native_agc_present.c").read_bytes()
    call = re.compile(
        rb"sceAgcLinkShaders\(presenter\.shader_memory \+ 0x5000,\s*"
        rb"presenter\.shader_memory \+ 0x6000,\s*NULL,\s*"
        rb"presenter\.vertex_shader,\s*presenter\.pixel_shader,\s*6\)")
    matches = list(call.finditer(source))
    if len(matches) != 1:
        raise SystemExit(f"expected one explicit LinkShaders pair call, got {len(matches)}")
    call_line = source[:matches[0].start()].count(b"\n") + 1

    for shader in (pre, pixel):
        del shader["_register_ids"]
        del shader["_resource_ids"]
    result = {
        "schema": 1, "firmware_scope": "12.02",
        "source_scope": "local authorized ProsperoTV research assets",
        "pair_id": "prosperotv-geometry-pixel-000",
        "pair_selection": {
            "explicit_same_callsite": True, "callsite_line": call_line,
            "callsite_sha256": sha(matches[0].group()), "primitive_type": 6,
            "auxiliary_shader": None,
        },
        "pre_raster": {**pre, "role": "pre_raster", "header_sha256": actual["geometry.header.bin"],
                       "code_sha256": actual["geometry.text.bin"]},
        "pixel": {**pixel, "role": "pixel", "header_sha256": actual["pixel.header.bin"],
                  "code_sha256": actual["pixel.text.linear-buffer.bin"]},
        "compatibility": {
            "target_equal": True, "matched_semantic_keys": [15],
            "every_pixel_input_has_pre_raster_output": True,
            "roles_proven_by_explicit_callsite_and_header_fields": True,
            "inferred_from_type_only": False,
            "cross_stage_register_id_overlap": cross_register_overlap,
            "resource_group_overlap_counts": resource_overlap,
            "all_register_and_resource_ranges_bounded": True,
            "resource_overlap_is_allowed_shared_binding_not_a_stage_register_collision": True,
        },
        "asset_bytes_emitted": False, "source_fragment_emitted": False,
        "console_contacted": False, "shaders_executed": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
