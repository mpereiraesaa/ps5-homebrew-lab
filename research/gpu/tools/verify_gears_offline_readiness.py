#!/usr/bin/env python3
"""Run every host-only gate required before Cube/Gears implementation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "research/gpu/tools"
GATES = (
    "verify_gears_shader_contracts.py",
    "verify_gears_runtime_contracts.py",
    "verify_agc_optional_exports.py",
    "verify_agc_indexed_draw_contract.py",
    "verify_depth_register_map.py",
    "verify_gfx1013_addrlib_contract.py",
    "verify_gears_depth_bootstrap.py",
    "verify_gears_predraw_clear_contract.py",
    "verify_gears_multidraw_contract.py",
)


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "sdk/agc/tests/verify_api.py")],
                   cwd=ROOT, check=True)
    for gate in GATES:
        subprocess.run([sys.executable, str(TOOLS / gate)], cwd=ROOT, check=True)
    # Re-run the ownership state machine itself: GPU fence must precede the
    # exact VideoOut flip token, and failure paths retain every resource.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ps5-gears-ownership-") as directory:
        test = Path(directory) / "completion-test"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            str(ROOT / "research/gpu/tools/test_stage_b_completion.c"),
            str(ROOT / "legacy/probes/ps5-agc-phase0/stage_b_completion.c"),
            "-o", str(test),
        ], cwd=ROOT, check=True)
        subprocess.run([str(test)], cwd=ROOT, check=True)
    print("gears offline readiness passed: shader/user-data, vertex SRD, optional "
          "indexed ABI, GFX1013 D32 layout/state, first-use clear, synchronization, "
          "three-draw budget and ownership contracts are host-gated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
