#!/usr/bin/env python3
"""Local-only structural gate for the isolated native AGC phase-0 title."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path


def program_headers(blob: bytes) -> list[dict[str, int]]:
    if blob[:6] != b"\x7fELF\x02\x01":
        raise SystemExit("eboot.elf is not little-endian ELF64")
    phoff = struct.unpack_from("<Q", blob, 0x20)[0]
    phentsize = struct.unpack_from("<H", blob, 0x36)[0]
    phnum = struct.unpack_from("<H", blob, 0x38)[0]
    result: list[dict[str, int]] = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        p_type, flags, _file, _va, _pa, filesz, memsz, align = (
            struct.unpack_from("<IIQQQQQQ", blob, offset)
        )
        result.append({
            "type": p_type,
            "flags": flags,
            "offset": _file,
            "vaddr": _va,
            "filesz": filesz,
            "memsz": memsz,
            "align": align,
        })
    return result


def load_segments(blob: bytes) -> list[dict[str, int]]:
    return [item for item in program_headers(blob) if item["type"] == 1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parent)
    parser.add_argument("--title-id", default="AGCP12002")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if re.fullmatch(r"[A-Z]{4}[0-9]{5}", args.title_id) is None:
        raise SystemExit("Title ID does not match observed AAAA99999 form")
    title = args.root / args.title_id
    user_meta = json.loads((title / "sce_sys/param.json").read_text())
    system_meta = json.loads((title / "sce_sys/param.json.system").read_text())
    minimal_keys = {"applicationCategoryType", "localizedParameters", "titleId"}
    if set(user_meta) != minimal_keys:
        raise SystemExit(f"user param differs from minimal SDK schema: {sorted(user_meta)}")
    if set(system_meta) != minimal_keys:
        raise SystemExit(f"system param differs from minimal SDK schema: {sorted(system_meta)}")
    if user_meta.get("titleId") != args.title_id:
        raise SystemExit("user param title mismatch")
    if system_meta.get("titleId") != args.title_id:
        raise SystemExit("system param title mismatch")
    if user_meta.get("applicationCategoryType") != 0:
        raise SystemExit("unexpected user application category")
    if system_meta.get("applicationCategoryType") != 33554432:
        raise SystemExit("unexpected system application category")

    elf_path = args.root / "eboot.elf"
    fself_path = title / "eboot.bin"
    user_meta_path = title / "sce_sys/param.json"
    system_meta_path = title / "sce_sys/param.json.system"
    elf = elf_path.read_bytes()
    headers = program_headers(elf)
    segments = [item for item in headers if item["type"] == 1]
    if len(segments) != 3 or [item["flags"] for item in segments] != [1, 4, 6]:
        raise SystemExit(f"expected non-empty RX/R/RW PT_LOADs, got {segments!r}")
    if any(item["filesz"] == 0 or item["memsz"] == 0 for item in segments):
        raise SystemExit("one required PT_LOAD is empty")
    if any(item["align"] != 0x4000 for item in segments):
        raise SystemExit("unexpected PT_LOAD alignment")
    if any(item["flags"] & 3 == 3 for item in segments):
        raise SystemExit("W^X violation: a PT_LOAD is both writable and executable")
    if any(item["type"] == 2 for item in headers):
        raise SystemExit("unexpected PT_DYNAMIC in the static lifecycle probe")

    entrypoint = struct.unpack_from("<Q", elf, 0x18)[0]
    entry_segments = [
        item for item in segments
        if item["vaddr"] <= entrypoint < item["vaddr"] + item["memsz"]
    ]
    if len(entry_segments) != 1 or entry_segments[0]["flags"] != 1:
        raise SystemExit("entrypoint is not uniquely contained in the RX PT_LOAD")

    forbidden_dwords = {
        "EVENT_WRITE": bytes.fromhex("005005c0"),
        "RELEASE_MEM": bytes.fromhex("004906c0"),
        "WAIT_REG_MEM": bytes.fromhex("003c05c0"),
        "ACQUIRE_MEM": bytes.fromhex("005806c0"),
    }
    present_packets = [name for name, marker in forbidden_dwords.items() if marker in elf]
    if present_packets:
        raise SystemExit(f"forbidden PM4 packet headers found: {present_packets!r}")
    forbidden_names = [b"SubmitDcb", b"CreateQueue", b"VideoOut"]
    present_names = [name.decode() for name in forbidden_names if name in elf]
    if present_names:
        raise SystemExit(f"forbidden GPU/queue names found: {present_names!r}")
    required_names = [
        b"/system/common/lib/libSceSysmodule.sprx",
        b"sceSysmoduleLoadModuleInternal",
        b"sceSysmoduleUnloadModuleInternal",
        b"sysmodule lifecycle only; no submit",
    ]
    missing_names = [name.decode() for name in required_names if name not in elf]
    if missing_names:
        raise SystemExit(f"expected lifecycle names missing: {missing_names!r}")

    fself = fself_path.read_bytes()
    if not fself.startswith(bytes.fromhex("4f153d1d")):
        raise SystemExit("eboot.bin is not the expected fake-SELF container")
    self_num_entries = struct.unpack_from("<H", fself, 24)[0]
    if self_num_entries != 6:
        raise SystemExit(f"expected six SELF entries, got {self_num_entries}")
    embedded_offset = fself.find(b"\x7fELF")
    if embedded_offset < 0:
        raise SystemExit("fake-SELF does not contain an embedded ELF header")
    embedded_segments = load_segments(fself[embedded_offset:])
    embedded_phnum = struct.unpack_from("<H", fself, embedded_offset + 0x38)[0]
    if embedded_phnum != 4:
        raise SystemExit(f"expected four embedded program headers, got {embedded_phnum}")
    if embedded_segments != segments:
        raise SystemExit(
            "fake-SELF embedded program headers differ from eboot.elf: "
            f"{embedded_segments!r} != {segments!r}"
        )

    result = {
        "title_id": args.title_id,
        "title_id_shape_observed": True,
        "metadata_consistent": True,
        "metadata_matches_minimal_sdk_schema": True,
        "load_segments": segments,
        "required_load_flags": ["RX", "R", "RW"],
        "entrypoint": entrypoint,
        "entrypoint_in_rx_load": True,
        "wx_load_segments": False,
        "pt_dynamic_present": False,
        "forbidden_pm4_headers_present": [],
        "forbidden_gpu_queue_names_present": [],
        "lifecycle_scope_only": True,
        "artifact_sha256": {
            "eboot.elf": hashlib.sha256(elf).hexdigest(),
            f"{args.title_id}/eboot.bin": hashlib.sha256(fself).hexdigest(),
            f"{args.title_id}/sce_sys/param.json": hashlib.sha256(
                user_meta_path.read_bytes()
            ).hexdigest(),
            f"{args.title_id}/sce_sys/param.json.system": hashlib.sha256(
                system_meta_path.read_bytes()
            ).hexdigest(),
        },
        "fself_container": True,
        "fself_embedded_elf_offset": embedded_offset,
        "fself_entry_count": self_num_entries,
        "fself_embedded_program_header_count": embedded_phnum,
        "fself_program_headers_match_source": True,
        "console_contacted": False,
        "launchability_proven": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
