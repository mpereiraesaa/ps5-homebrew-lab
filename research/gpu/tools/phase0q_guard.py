#!/usr/bin/env python3
"""Classify mapping-only phase 0Q logs; never contacts or controls a PS5."""
from __future__ import annotations

import argparse
import json
import re
from enum import Enum
from pathlib import Path


class State(str, Enum):
    NOT_STARTED = "not_started"
    MAP_ACCEPTED_CLEAN = "map_accepted_clean"
    MAP_REJECTED_CLEAN = "map_rejected_clean"
    PARKED = "parked"
    UNKNOWN_RETAIN = "unknown_retain"


PARK_MARKER = "PARKED_PHASE0Q"


def classify(log: str) -> dict[str, object]:
    parked = PARK_MARKER in log
    start_matches = re.findall(
        r"^phase0Q start; type=0x0c BatchMap prot=0xcf2; no AGC, queue or submit$",
        log, re.MULTILINE,
    )
    open_matches = re.findall(r"^open rc=(-?\d+) state=(\d+) va=", log, re.MULTILINE)
    close_matches = re.findall(r"^close rc=(-?\d+) state=(\d+)$", log, re.MULTILINE)
    rejected_cleanups = re.findall(
        r"^definite map failure cleanup rc=0 state=0$", log, re.MULTILINE
    )
    exit_matches = re.findall(
        r"^phase0Q exit result=(-?\d+) submitted=no$", log, re.MULTILINE
    )
    canary_matches = re.findall(r"^cpu_canaries=(yes|no)$", log, re.MULTILINE)

    accepted_clean = bool(
        len(start_matches) == 1
        and open_matches == [("0", "3")]
        and close_matches == [("0", "0")]
        and len(canary_matches) == 1 and len(exit_matches) == 1
        and ((canary_matches[0] == "yes" and exit_matches[0] == "0")
             or (canary_matches[0] == "no" and exit_matches[0] == "20"))
        and not rejected_cleanups
    )
    rejected_clean = bool(
        len(start_matches) == 1
        and len(open_matches) == 1 and int(open_matches[0][0]) != 0
        and open_matches[0][1] in ("0", "1", "2")
        and len(rejected_cleanups) == 1 and len(exit_matches) == 1
        and int(exit_matches[0]) == int(open_matches[0][0])
        and not canary_matches and not close_matches
    )

    if parked:
        state = State.PARKED
        reason = "mapping state ambiguous; retain process and resources"
    elif accepted_clean:
        state = State.MAP_ACCEPTED_CLEAN
        reason = "BatchMap acceptance and complete ordered cleanup recorded"
    elif rejected_clean:
        state = State.MAP_REJECTED_CLEAN
        reason = "BatchMap rejected definitively and allocations were cleaned"
    elif not log.strip():
        state = State.NOT_STARTED
        reason = "no phase 0Q log"
    else:
        state = State.UNKNOWN_RETAIN
        reason = "active, truncated, stale or contradictory mapping log"

    close_allowed = state in (State.MAP_ACCEPTED_CLEAN, State.MAP_REJECTED_CLEAN)
    return {
        "state": state.value,
        "close_allowed": close_allowed,
        "cleanup_proven": close_allowed,
        "mapping_accepted": state is State.MAP_ACCEPTED_CLEAN,
        "cpu_canaries_passed": canary_matches == ["yes"],
        "retain_process_and_mapping_state": not close_allowed,
        "park_markers": [PARK_MARKER] if parked else [],
        "reason": reason,
        "automated_actions_allowed": (
            ["record_state", "verified_close"] if close_allowed else
            ["read_only_health", "record_state", "stop_automation"]
        ),
        "automated_actions_forbidden": (
            [] if close_allowed else
            ["close_fake00000", "launch_title", "launch_payload",
             "batch_unmap", "release_direct_memory"]
        ),
        "operator_recovery": (
            "controlled full console restart; do not use Close Game or Rest Mode"
            if not close_allowed else "none"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    result = classify(args.log.read_text(errors="replace") if args.log.exists() else "")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["close_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
