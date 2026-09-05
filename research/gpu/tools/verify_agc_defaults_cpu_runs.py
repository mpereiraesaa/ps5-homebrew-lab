#!/usr/bin/env python3
"""Validate and compare two sanitized AgcRegisterDefaults captures."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path


class VerificationError(RuntimeError):
    pass


SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_BANKS = ((0, "cx", 84), (1, "sh", 32), (2, "uc", 21))
ZERO_SAFETY = {
    "debugger_attach": False,
    "writes": 0,
    "remote_calls": 0,
    "shader_calls": 0,
    "queue_or_dcb_calls": 0,
    "submits": 0,
    "videoout_calls": 0,
    "raw_tables_emitted": False,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def validate_capture(capture: dict) -> None:
    require(capture.get("schema") == 1, "unsupported schema")
    require(capture.get("title_id") == "PPSA99998", "wrong title")
    require(capture.get("firmware") == "12.02", "wrong firmware")
    require(capture.get("layout_size") == 0x40, "wrong root size")
    require(capture.get("count") == 137, "unexpected record count")
    require(capture.get("type_records") == 137, "type count mismatch")
    require(capture.get("unique_keys") == 137, "keys are not unique")
    require(capture.get("record_shape") == "u32 key + u32 encoded_index",
            "wrong record shape")
    require(capture.get("termination_model") == "count-delimited; no sentinel",
            "unsupported or inconsistent termination model")
    require(capture.get("table_3_null") is True, "table 3 must be null")
    for field in ("root_sha256", "type_table_sha256"):
        require(bool(SHA256.fullmatch(str(capture.get(field, "")))), f"bad {field}")
    require("r" in capture.get("root_permissions", ""), "root is unreadable")
    require("r" in capture.get("types_permissions", ""), "types are unreadable")

    banks = capture.get("banks")
    require(isinstance(banks, list) and len(banks) == 3, "need three banks")
    total = 0
    for actual, (bank, name, entries) in zip(banks, EXPECTED_BANKS):
        require(actual.get("bank") == bank and actual.get("name") == name,
                "bank identity/order mismatch")
        require(actual.get("entries") == entries, f"unexpected {name} count")
        require(actual.get("index_min") == 0, f"bad {name} minimum index")
        require(actual.get("index_max") == entries - 1, f"bad {name} maximum index")
        require(actual.get("targets_strictly_increasing") is True,
                f"{name} pointers are not strictly increasing")
        require("r" in actual.get("pointer_table_permissions", ""),
                f"{name} pointer table unreadable")
        require(bool(SHA256.fullmatch(str(actual.get("pointer_table_sha256", "")))),
                f"bad {name} pointer hash")
        lo = int(actual.get("target_min", "invalid"), 16)
        hi = int(actual.get("target_max", "invalid"), 16)
        require(lo != 0 and lo % 8 == 0 and hi >= lo and hi % 8 == 0,
                f"bad {name} pointer range")
        total += entries
    require(total == capture["count"], "bank sum differs from count")

    invariants = capture.get("invariants", {})
    for key in (
        "count_equals_bank_entry_sum",
        "indices_unique_contiguous_ordered_per_bank",
        "all_pointers_non_null_aligned_readable",
    ):
        require(invariants.get(key) is True, f"missing invariant: {key}")
    require(capture.get("safety") == ZERO_SAFETY, "safety envelope changed")
    require(isinstance(capture.get("pid_ephemeral"), int), "missing ephemeral PID")


def reproducible_view(capture: dict) -> dict:
    result = copy.deepcopy(capture)
    result.pop("pid_ephemeral", None)
    return result


def verify_pair(first: dict, second: dict) -> None:
    validate_capture(first)
    validate_capture(second)
    require(first["pid_ephemeral"] != second["pid_ephemeral"],
            "runs are not independent: PID did not change")
    require(reproducible_view(first) == reproducible_view(second),
            "sanitized captures differ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()
    first = json.loads(args.first.read_text(encoding="utf-8"))
    second = json.loads(args.second.read_text(encoding="utf-8"))
    verify_pair(first, second)
    print(json.dumps({
        "verified": True,
        "independent_pids": [first["pid_ephemeral"], second["pid_ephemeral"]],
        "count": first["count"],
        "bank_counts": {b["name"]: b["entries"] for b in first["banks"]},
        "root_sha256": first["root_sha256"],
        "type_table_sha256": first["type_table_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
