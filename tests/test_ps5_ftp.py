#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))

from ps5_ftp import verify_remote_file  # noqa: E402


class FakeFTP:
    def __init__(self, stored: bytes, conversion_enabled: bool = True):
        self.stored = stored
        self.conversion_enabled = conversion_enabled
        self.commands: list[str] = []

    def sendcmd(self, command: str) -> str:
        assert command == "SELF"
        self.commands.append(command)
        self.conversion_enabled = not self.conversion_enabled
        state = "enabled" if self.conversion_enabled else "disabled"
        return f"226 SELF transfer mode {state}"

    def size(self, _remote: str) -> int:
        return len(self.stored)

    def retrbinary(self, command: str, callback) -> None:
        assert command == "RETR /remote"
        callback(self.stored[:3])
        callback(self.stored[3:])


def main() -> int:
    payload = b"signed-fself-bytes"
    digest = hashlib.sha256(payload).hexdigest()

    enabled = FakeFTP(payload, conversion_enabled=True)
    assert verify_remote_file(enabled, "/remote", len(payload), digest, True) == len(payload)
    assert enabled.commands == ["SELF"]
    assert not enabled.conversion_enabled

    disabled = FakeFTP(payload, conversion_enabled=False)
    verify_remote_file(disabled, "/remote", len(payload), digest, True)
    assert disabled.commands == ["SELF", "SELF"]
    assert not disabled.conversion_enabled

    ordinary = FakeFTP(payload)
    verify_remote_file(ordinary, "/remote", len(payload), digest, False)
    assert ordinary.commands == []

    try:
        verify_remote_file(FakeFTP(payload), "/remote", len(payload), "0" * 64, True)
    except RuntimeError as error:
        assert "digest mismatch" in str(error)
    else:
        raise AssertionError("digest mismatch was accepted")

    print("PS5 FTP exact verification tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
