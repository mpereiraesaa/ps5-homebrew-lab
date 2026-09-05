#!/usr/bin/env python3
"""Emit a reproducible proof of the phase 0M recovery decision matrix."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase0m_guard import classify


CASES = {
    "empty_expected_run": "",
    "pre_submit_exit": "AGC phase 0M exit result=11\n",
    "complete": ("SubmitDcb returned rc=0x00000000\n"
                 "GPU completion verified target=0 fence=0\n"
                 "AGC phase 0M exit result=0\n"),
    "submit_truncated": "SubmitDcb returned rc=0x00000000\n",
    "completion_without_exit": "GPU completion verified target=0 fence=0\n",
    "watchdog_park": "PARKED_AFTER_SUBMIT\n",
    "submit_error_park": "PARKED_SUBMIT_ERROR\n",
    "fence_timeout_park": "PARKED_FENCE_TIMEOUT\n",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    decisions = {name: classify(log) for name, log in CASES.items()}
    allowed = {name for name, value in decisions.items() if value["close_allowed"]}
    if allowed != {"pre_submit_exit", "complete"}:
        raise SystemExit(f"unexpected close-authorized cases: {sorted(allowed)}")
    for name, value in decisions.items():
        if not value["close_allowed"]:
            if "close_fake00000" not in value["automated_actions_forbidden"]:
                raise SystemExit(f"{name}: close is not explicitly forbidden")
            if "stop_automation" not in value["automated_actions_allowed"]:
                raise SystemExit(f"{name}: automation stop is not required")
    result = {
        "schema": 1,
        "console_contacted": False,
        "phase0m_deployed": False,
        "phase0m_executed": False,
        "cases": decisions,
        "only_close_authorized_cases": sorted(allowed),
        "ambiguous_state_policy": "retain resources and stop automation",
        "remote_recovery_authorized": False,
        "operator_recovery": "controlled full console restart",
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
