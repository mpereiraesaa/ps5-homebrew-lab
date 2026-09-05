#!/usr/bin/env python3
"""Classify phase 0S fence-only logs; never contacts the console."""
from __future__ import annotations

import re
from enum import Enum


class State(str, Enum):
    PRE_SUBMIT_CLEAN = "pre_submit_clean"
    GPU_COMPLETE = "gpu_complete"
    PARKED = "parked"
    UNKNOWN_RETAIN = "unknown_retain"


START = "phase0S start; BatchMap 0xcf2; ownership RELEASE_MEM only; no VideoOut"


def classify(log: str) -> dict[str, object]:
    starts = re.findall(rf"^{re.escape(START)}$", log, re.MULTILINE)
    queue = re.findall(r"^queue pristine and BatchMap accepted state=3$", log, re.MULTILINE)
    submits = re.findall(r"^SubmitDcb returned rc=0x([0-9a-fA-F]{8})$", log, re.MULTILINE)
    complete = re.findall(r"^GPU ownership complete fence=0$", log, re.MULTILINE)
    exits = re.findall(r"^phase0S exit result=(-?\d+) submitted=(yes-complete|no)$", log, re.MULTILINE)
    parked = "PARKED_PHASE0S" in log or "DO_NOT_CLOSE_FAKE00000" in log
    gpu = (len(starts) == len(queue) == len(submits) == len(complete) == len(exits) == 1
           and int(submits[0], 16) == 0 and exits[0] == ("0", "yes-complete")
           and not parked)
    pre = (len(starts) == len(exits) == 1 and exits[0][1] == "no"
           and int(exits[0][0]) != 0 and not submits and not complete and not parked)
    if parked:
        state, reason = State.PARKED, "post-submit or cleanup state explicitly retained"
    elif gpu:
        state, reason = State.GPU_COMPLETE, "ownership fence completed before cleanup"
    elif pre:
        state, reason = State.PRE_SUBMIT_CLEAN, "normal failure and cleanup completed before submit"
    else:
        state, reason = State.UNKNOWN_RETAIN, "empty, truncated, stale, duplicate, or contradictory log"
    close = state in (State.PRE_SUBMIT_CLEAN, State.GPU_COMPLETE)
    return {"state": state.value, "close_allowed": close,
            "completion_proven": state is State.GPU_COMPLETE,
            "retain_process_driver_mapping": not close, "reason": reason}
