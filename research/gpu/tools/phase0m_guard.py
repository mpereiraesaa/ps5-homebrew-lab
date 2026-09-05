#!/usr/bin/env python3
"""Classify phase 0M logs conservatively; never contacts or controls a PS5."""
from __future__ import annotations

import argparse
import json
from enum import Enum
from pathlib import Path


class State(str, Enum):
    NOT_STARTED = "not_started"
    PRE_SUBMIT_EXIT = "pre_submit_exit"
    GPU_COMPLETE = "gpu_complete"
    PARKED = "parked"
    UNKNOWN_RETAIN = "unknown_retain"


PARK_MARKERS = (
    "PARKED_AFTER_SUBMIT",
    "PARKED_SUBMIT_ERROR",
    "PARKED_FENCE_TIMEOUT",
)


def classify(log: str) -> dict[str, object]:
    markers = [marker for marker in PARK_MARKERS if marker in log]
    submit_started = "SubmitDcb returned" in log or bool(markers)
    completion = "GPU completion verified target=0 fence=0" in log
    exited = "AGC phase 0M exit result=" in log

    if markers:
        state = State.PARKED
        reason = "post-submit state uncertain; resources must remain alive"
    elif completion and exited:
        state = State.GPU_COMPLETE
        reason = "fence and target completed before normal cleanup"
    elif exited and not submit_started:
        state = State.PRE_SUBMIT_EXIT
        reason = "probe exited before evidence of entering submit"
    elif not log.strip():
        state = State.NOT_STARTED
        reason = "no phase 0M log"
    else:
        state = State.UNKNOWN_RETAIN
        reason = "truncated or active log cannot prove GPU completion"

    # This classifier is used only once a phase 0M run is expected. An empty
    # log may mean that the write was lost or truncated, so it cannot authorize
    # cleanup.
    close_allowed = state in (State.PRE_SUBMIT_EXIT, State.GPU_COMPLETE)
    unsafe_actions = [
        "close_fake00000",
        "launch_title",
        "launch_payload",
        "unmap_direct_memory",
        "release_direct_memory",
        "unload_agc_driver",
    ]
    return {
        "state": state.value,
        "close_allowed": close_allowed,
        "retain_process_module_mapping": not close_allowed,
        "park_markers": markers,
        "submit_started_or_possible": submit_started,
        "completion_proven": state is State.GPU_COMPLETE,
        "reason": reason,
        "automated_actions_allowed": (
            ["read_only_health", "record_state", "stop_automation"]
            if not close_allowed else
            ["record_state", "verified_cleanup", "verified_close"]
        ),
        "automated_actions_forbidden": unsafe_actions if not close_allowed else [],
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
