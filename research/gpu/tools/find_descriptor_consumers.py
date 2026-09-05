#!/usr/bin/env python3
"""Rank x86-64 functions that may consume an AGC register-pair descriptor.

The runtime image is a sparse, base-addressed dump rather than an ELF with
function symbols.  GNU objdump consequently labels the whole image as one
section.  This tool reconstructs conservative function islands from runs of
INT3 padding, then ranks only islands that both read a selected object offset
and exhibit evidence of command emission (calls, an 0x80-byte copy, or the
known render-target register IDs).

It is a triage aid, not proof of data flow.  A reported candidate must still be
checked manually to show that the value read from object+offset reaches the
backend unchanged.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


ADDRESS_RE = re.compile(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*)$")
MEMORY_RE_TEMPLATE = r"(?:0x)?{offset:x}\(%(?:r|e)[a-z0-9]+(?:,%[^)]*)?\)"
RT_IDS = {0x02, 0x05, 0x07, 0x0A, 0x0B, 0x10, 0x11, 0x12,
          0x13, 0x14, 0x15, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E}


def integer(value: str) -> int:
    return int(value, 0)


@dataclass(frozen=True)
class Instruction:
    address: int
    raw: bytes
    text: str


def disassemble(dump: Path, base: int, start: int, stop: int) -> list[Instruction]:
    command = [
        "objdump", "-D", "-b", "binary", "-m", "i386:x86-64",
        "--adjust-vma", hex(base), "--start-address", hex(start),
        "--stop-address", hex(stop), str(dump),
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    instructions: list[Instruction] = []
    for line in result.stdout.splitlines():
        match = ADDRESS_RE.match(line)
        if not match:
            continue
        instructions.append(Instruction(
            int(match.group(1), 16),
            bytes.fromhex(match.group(2)),
            match.group(3).strip(),
        ))
    return instructions


def direct_call_targets(instructions: list[Instruction]) -> set[int]:
    targets = set()
    for instruction in instructions:
        # GNU AT&T output is normally `call  1f2f640`; tolerate a 0x prefix.
        match = re.match(r"call\s+(?:0x)?([0-9a-f]+)(?:\s|$)", instruction.text)
        if match:
            targets.add(int(match.group(1), 16))
    return targets


def split_islands(instructions: list[Instruction], minimum_int3: int) -> list[list[Instruction]]:
    starts = direct_call_targets(instructions)
    islands: list[list[Instruction]] = []
    current: list[Instruction] = []
    padding: list[Instruction] = []
    for instruction in instructions:
        if instruction.raw == b"\xcc":
            padding.append(instruction)
            continue
        if len(padding) >= minimum_int3 and current:
            islands.append(current)
            current = []
        elif padding:
            current.extend(padding)
        padding = []
        if instruction.address in starts and current:
            islands.append(current)
            current = []
        current.append(instruction)
        # A return terminates a control-flow path.  This can split a function
        # with several epilogues, which is acceptable for local triage and is
        # substantially safer than merging many adjacent functions.
        if instruction.text.startswith("ret"):
            islands.append(current)
            current = []
    if current:
        islands.append(current)
    return islands


def immediates(text: str) -> set[int]:
    values = set()
    for token in re.findall(r"\$0x([0-9a-f]+)", text):
        values.add(int(token, 16))
    return values


def direct_target(instruction: Instruction) -> int | None:
    match = re.match(r"call\s+(?:0x)?([0-9a-f]+)(?:\s|$)", instruction.text)
    return int(match.group(1), 16) if match else None


def score_island(island: list[Instruction], object_offset: int) -> dict | None:
    memory_re = re.compile(MEMORY_RE_TEMPLATE.format(offset=object_offset))
    loads = []
    for ins in island:
        if not memory_re.search(ins.text):
            continue
        # In AT&T syntax the source precedes the comma.  Keep genuine loads
        # (and LEAs) but reject stores to an object field at the same offset.
        operands = ins.text.split(None, 1)
        if len(operands) != 2 or "," not in operands[1]:
            continue
        source = operands[1].split(",", 1)[0]
        if memory_re.search(source):
            loads.append(ins)
    if not loads:
        return None
    calls = [ins for ins in island if ins.text.startswith("call")]
    nearby_backend_calls = []
    load_addresses = {ins.address for ins in loads}
    for index, instruction in enumerate(island):
        if instruction.address not in load_addresses:
            continue
        for following in island[index + 1:index + 49]:
            target = direct_target(following)
            if target is not None and 0x4DC0000 <= target < 0x4DC4000:
                nearby_backend_calls.append({
                    "load": hex(instruction.address),
                    "call": hex(following.address),
                    "target": hex(target),
                })
    copy_80 = [ins for ins in island if "$0x80" in ins.text or "$0x10" in ins.text]
    found_ids = set()
    for ins in island:
        found_ids.update(immediates(ins.text) & RT_IDS)
    score = 10 * len(loads) + min(len(calls), 8)
    score += 8 if any("$0x80" in ins.text for ins in copy_80) else 0
    score += 2 * len(found_ids)
    score += 20 * len(nearby_backend_calls)
    return {
        "start": hex(island[0].address),
        "end": hex(island[-1].address + len(island[-1].raw)),
        "score": score,
        "offset_accesses": [hex(ins.address) for ins in loads],
        "calls": [hex(ins.address) for ins in calls],
        "nearby_backend_calls": nearby_backend_calls,
        "rt_ids": [hex(value) for value in sorted(found_ids)],
        "has_0x80_immediate": any("$0x80" in ins.text for ins in copy_80),
        "instructions": len(island),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--start", type=integer, required=True)
    parser.add_argument("--stop", type=integer, required=True)
    parser.add_argument("--object-offset", type=integer, default=0x30)
    parser.add_argument("--minimum-int3", type=int, default=4)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    base = int(manifest["base"], 0)
    instructions = disassemble(args.dump, base, args.start, args.stop)
    islands = split_islands(instructions, args.minimum_int3)
    candidates = [candidate for island in islands
                  if (candidate := score_island(island, args.object_offset))]
    candidates.sort(key=lambda item: (-item["score"], int(item["start"], 0)))
    result = {
        "schema": 1,
        "dump": str(args.dump),
        "range": [hex(args.start), hex(args.stop)],
        "object_offset": hex(args.object_offset),
        "boundary_heuristic": (
            f">={args.minimum_int3} consecutive INT3 instructions or in-range "
            "direct CALL target"
        ),
        "islands": len(islands),
        "candidates": candidates,
        "warning": "Candidates are triage hints; manually prove value identity.",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{len(instructions)} instructions, {len(islands)} islands, "
          f"{len(candidates)} candidates")
    for candidate in candidates[:args.limit]:
        print(candidate["start"], f"score={candidate['score']}",
              f"loads={','.join(candidate['offset_accesses'])}",
              f"calls={len(candidate['calls'])}",
              f"backend={len(candidate['nearby_backend_calls'])}",
              f"ids={','.join(candidate['rt_ids']) or '-'}",
              f"imm80={candidate['has_0x80_immediate']}")


if __name__ == "__main__":
    main()
