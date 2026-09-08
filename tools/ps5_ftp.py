#!/usr/bin/env python3
"""Exact upload verification for ps5-payload-dev/ftpsrv."""

from __future__ import annotations

import hashlib
from ftplib import FTP

SELF_MAGICS = (b"\x4f\x15\x3d\x1d", b"\x54\x14\xf5\xee")
_RAW_SELF_MARKER = "_ps5_raw_self_transfer_enabled"


def is_self_container(data: bytes) -> bool:
    """Return whether data begins with a PS4 or PS5 SELF container magic."""
    return data.startswith(SELF_MAGICS)


def disable_self_decryption(ftp: FTP) -> str:
    """Leave on-the-fly SELF-to-ELF conversion disabled for this connection."""
    if getattr(ftp, _RAW_SELF_MARKER, False):
        return "SELF transfer mode already disabled"
    for _ in range(2):
        response = ftp.sendcmd("SELF")
        lowered = response.lower()
        if "disabled" in lowered:
            setattr(ftp, _RAW_SELF_MARKER, True)
            return response
        if "enabled" not in lowered:
            raise RuntimeError(f"ftpsrv returned an unknown SELF mode: {response}")
    raise RuntimeError("ftpsrv did not disable SELF transfer conversion")


def verify_remote_file(ftp: FTP, remote: str, expected_size: int,
                       expected_sha256: str, self_container: bool) -> int:
    """Verify the exact stored bytes, disabling transparent SELF decoding."""
    if self_container:
        disable_self_decryption(ftp)

    remote_size = ftp.size(remote)
    if remote_size != expected_size:
        raise RuntimeError(
            f"remote size mismatch: {remote}: {remote_size} != {expected_size}")

    digest = hashlib.sha256()
    received = 0

    def consume(chunk: bytes) -> None:
        nonlocal received
        received += len(chunk)
        digest.update(chunk)

    ftp.retrbinary(f"RETR {remote}", consume)
    if received != expected_size or digest.hexdigest() != expected_sha256:
        raise RuntimeError(f"remote digest mismatch: {remote}")
    return received
