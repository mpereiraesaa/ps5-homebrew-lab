#!/usr/bin/env python3
"""Classify phase 0R ownership-submit logs; never contacts the console."""
from __future__ import annotations

import argparse
import json
import re
from enum import Enum
from pathlib import Path


class State(str, Enum):
    NOT_STARTED = "not_started"
    PRE_SUBMIT_CLEAN = "pre_submit_clean"
    GPU_COMPLETE = "gpu_complete"
    PARKED = "parked"
    UNKNOWN_RETAIN = "unknown_retain"


START = "phase0R start; BatchMap 0xcf2; 4-byte DMA plus ownership fence; no VideoOut"


def classify(log: str) -> dict[str, object]:
    starts = re.findall(rf"^{re.escape(START)}$", log, re.MULTILINE)
    queue = re.findall(r"^queue pristine and BatchMap accepted state=3$", log, re.MULTILINE)
    submits = re.findall(r"^SubmitDcb returned rc=0x([0-9a-fA-F]{8})$", log, re.MULTILINE)
    completions = re.findall(r"^GPU ownership complete fence=0 target=0$", log, re.MULTILINE)
    exits = re.findall(r"^phase0R exit result=(-?\d+) submitted=(yes-complete|no)$",
                       log, re.MULTILINE)
    parked = "PARKED_PHASE0R" in log or "DO_NOT_CLOSE_FAKE00000" in log

    gpu_complete = (
        len(starts) == len(queue) == len(submits) == len(completions) == len(exits) == 1
        and int(submits[0], 16) == 0 and exits[0] == ("0", "yes-complete")
        and not parked
    )
    pre_submit_clean = (
        len(starts) == len(exits) == 1 and exits[0][1] == "no"
        and int(exits[0][0]) != 0 and not submits and not completions and not parked
    )
    if parked:
        state, reason = State.PARKED, "post-submit or cleanup state explicitly retained"
    elif gpu_complete:
        state, reason = State.GPU_COMPLETE, "fence and target completed before normal cleanup"
    elif pre_submit_clean:
        state, reason = State.PRE_SUBMIT_CLEAN, "normal failure and cleanup completed before submit"
    elif not log.strip():
        state, reason = State.NOT_STARTED, "no phase 0R log"
    else:
        state, reason = State.UNKNOWN_RETAIN, "truncated, stale, duplicate, or contradictory log"
    close = state in (State.PRE_SUBMIT_CLEAN, State.GPU_COMPLETE)
    return {
        "state": state.value,
        "close_allowed": close,
        "completion_proven": state is State.GPU_COMPLETE,
        "submit_started_or_possible": bool(submits or queue),
        "retain_process_driver_mapping": not close,
        "reason": reason,
        "operator_recovery": "none" if close else
            "controlled full console restart; do not close FAKE00000 or use Rest Mode",
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
