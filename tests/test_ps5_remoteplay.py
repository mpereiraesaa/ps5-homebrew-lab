#!/usr/bin/env python3
"""Host contracts for the Remote Play lab wrapper."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ps5_remoteplay", ROOT / "tools" / "ps5_remoteplay.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> int:
    ready = MODULE.parse_ready(
        "[RemotePlayPair] READY | PIN: 12345678 | "
        "Account ID: eGlaSzwtHo8= | Timeout: 300s"
    )
    assert ready == ("12345678", "eGlaSzwtHo8=", 300)
    assert MODULE.parse_ready("[RemotePlayPair] Initializing Remote Play...") is None
    assert MODULE.LINKDEV_COMMIT == "b658657190873f1ae194b732f8dcfdb02543c4aa"
    assert MODULE.DEFAULT_CAPTURE_DIR.parts[-2:] == ("captures", "remoteplay")
    print("Remote Play host contracts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
