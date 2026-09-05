#!/usr/bin/env python3
"""Verify the complete prerequisite-gated Stage C hardware progression."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CAPTURES = ROOT / "research/gpu/captures"
SIZES = (256, 4096, 65536)


def load(name: str) -> dict:
    return json.loads((CAPTURES / name).read_text())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Stage C progression verification failed: {message}")


def main() -> int:
    steps = []
    previous = 4
    for size in SIZES:
        local = load(f"agc-stage-c-{size}-local-proof.json")
        runtime = load(f"agc-stage-c-{size}-runtime.json")
        require(size > previous, "sizes are not strictly increasing")
        require(local["fill_bytes"] == runtime["fill_bytes"] == size,
                f"size mismatch at {size}")
        require(local["fself_sha256"] == runtime["artifact_sha256"],
                f"artifact mismatch at {size}")
        require(local["approved_for_supervised_execution"] is True,
                f"local gate not approved at {size}")
        for field in (
            "gpu_fence_zero", "target_matches", "prefix_canary_intact",
            "suffix_canary_intact", "outside_untouched", "arenas_scrubbed",
            "cleanup_complete", "process_close_verified", "no_bigapp_after_close",
        ):
            require(runtime[field] is True, f"{field} not proven at {size}")
        require(runtime["submit_result"] == 0, f"submit failed at {size}")
        require(runtime["videoout_shader_draw"] is False,
                f"forbidden graphics path present at {size}")
        require(runtime["commercial_process_access"] is False,
                f"commercial process access present at {size}")
        require(all(runtime["services_after_close"].values()),
                f"service unhealthy after {size}")
        steps.append({
            "fill_bytes": size,
            "artifact_sha256": runtime["artifact_sha256"],
            "log_sha256": runtime["log_sha256"],
            "complete": True,
        })
        previous = size
    supervisor = (ROOT / "tools/night_supervisor.py").read_text()
    for size in SIZES:
        require(f'"run-stage-c-{size}"' in supervisor,
                f"supervisor action missing for {size}")
    require("previous Stage C runtime step is not proven complete" in supervisor,
            "prerequisite gate absent")
    result = {
        "schema": 1,
        "firmware": "12.02",
        "stage": "C",
        "hardware_proven": True,
        "progression_bytes": list(SIZES),
        "maximum_proven_bytes": SIZES[-1],
        "pattern": "0x6b5aa5c3",
        "separate_command_and_data_mappings": True,
        "full_outside_range_scan_each_step": True,
        "videoout_shader_draw": False,
        "commercial_process_access": False,
        "steps": steps,
    }
    output = CAPTURES / "agc-stage-c-progression.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
