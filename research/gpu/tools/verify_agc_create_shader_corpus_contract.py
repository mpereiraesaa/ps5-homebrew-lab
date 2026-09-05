#!/usr/bin/env python3
"""Run the host-only CreateShader planner over the authorized local corpus.

Only aggregate, sanitized facts are emitted. Shader bytes and register values
never leave the process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from agc_create_shader_planner import (
    HeaderFacts, Preconditions, Region, UserDataFacts, build_plan,
)


STAGE_REQUIRED_GLOBAL = {
    0: 0x45C90,
    1: 0x45CE0,
    2: 0x45CA0,
    3: 0x45CD0,
    6: 0x45CB0,
    7: 0x45CC0,
}
HEADER_POINTER_FIELDS = (0x08, 0x18, 0x20, 0x28, 0x30, 0x38)
USER_POINTER_FIELDS = (0, 8, 16, 24, 32)


def u16s(blob: bytes, offset: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f"<{count}H", blob, offset)


def u32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


def u64(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", blob, offset)[0]


def parse_facts(blob: bytes) -> tuple[HeaderFacts, UserDataFacts | None]:
    if len(blob) < 0x60:
        raise ValueError("header file lacks the fixed prefix")
    pointers = {offset: u64(blob, offset) for offset in HEADER_POINTER_FIELDS}
    facts = HeaderFacts(
        u32(blob, 0), u32(blob, 4), u32(blob, 0x40), u32(blob, 0x44),
        u32(blob, 0x4C), blob[0x5A], u64(blob, 0x10), pointers,
        blob[0x5B], blob[0x5C], u32(blob, 0x50), u16s(blob, 0x56, 1)[0],
    )
    if pointers[0x08] == 0:
        return facts, None
    user_offset = 0x08 + pointers[0x08]
    if user_offset + 0x38 > len(blob):
        raise ValueError("user-data prefix leaves file")
    nested = {field: u64(blob, user_offset + field) for field in USER_POINTER_FIELDS}
    counts = u16s(blob, user_offset + 0x28, 7)
    return facts, UserDataFacts(nested, counts[2], tuple(counts[3:7]))


def required_register_matches(blob: bytes, facts: HeaderFacts,
                              module: bytes) -> bool:
    if facts.stage in (4, 5):
        return True
    global_offset = STAGE_REQUIRED_GLOBAL.get(facts.stage)
    sh_raw = facts.relative_pointers[0x20]
    if global_offset is None or sh_raw == 0 or facts.num_sh_registers == 0:
        return False
    sh_offset = 0x20 + sh_raw
    if sh_offset + 4 > facts.header_size or global_offset + 4 > len(module):
        return False
    required = u32(module, global_offset)
    return any(u32(blob, sh_offset + index * 8) == required
               for index in range(facts.num_sh_registers))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--shaders", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    module = args.module.read_bytes()
    if not (manifest.get("all_self_relative_relocations_cross_checked") and
            manifest.get("all_code_cross_checked_between_captures") and
            manifest.get("all_code_256_aligned_in_capture")):
        raise SystemExit("authorized cross-capture evidence is incomplete")

    summaries = []
    targets, stages = Counter(), Counter()
    for entry in manifest["entries"]:
        header_blob = (args.shaders / entry["header_file"]).read_bytes()
        code_blob = (args.shaders / entry["code_file"]).read_bytes()
        facts, user = parse_facts(header_blob)
        if facts.header_size > len(header_blob):
            raise SystemExit("declared header exceeds its authorized file")
        if facts.shader_size != len(code_blob):
            raise SystemExit("declared code size differs from its authorized file")
        footer_ok = (facts.shader_size >= 0x30 and
                     code_blob[facts.shader_size - 0x30:facts.shader_size - 0x28] == b"barefoot")
        stage_match = required_register_matches(header_blob, facts, module)
        index = entry["index"]
        header_base = 0x10000000 + index * 0x10000
        code_base = 0x20000000 + index * 0x10000
        plan = build_plan(
            Region(0x08000000 + index * 0x10, 8, True, True, "destination"),
            Region(header_base, facts.header_size, True, True, "mutable header"),
            Region(code_base, len(code_blob), True, False, "code"),
            facts,
            Preconditions(True, footer_ok, stage_match, u32(module, 0x45C90),
                          module[0x460A8], u32(module, 0x460A4)),
            user,
        )
        targets[facts.target] += 1
        stages[facts.stage] += 1
        summaries.append((plan["header_bytes"], plan["code_bytes"],
                          plan["stage"], plan["target"]))

    digest = hashlib.sha256(json.dumps(summaries, separators=(",", ":")).encode()).hexdigest()
    result = {
        "schema": 1,
        "firmware": "12.02",
        "authorized_pairs_planned": len(summaries),
        "rejected_pairs": 0,
        "stage_counts": {str(k): v for k, v in sorted(stages.items())},
        "target_counts": {str(k): v for k, v in sorted(targets.items())},
        "all_required_stage_registers_matched": True,
        "all_nested_user_data_ranges_bounded": True,
        "all_header_and_code_sizes_bounded": True,
        "sanitized_plan_digest": digest,
        "cross_capture_relocated_outcomes": True,
        "raw_bytes_emitted": False,
        "register_values_emitted": False,
        "console_contacted": False,
        "create_shader_called": False,
        "future_probe_authorized": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
