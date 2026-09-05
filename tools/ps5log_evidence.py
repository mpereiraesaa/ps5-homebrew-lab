#!/usr/bin/env python3
"""Validation helpers for ps5logd evidence produced on the development PC."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


class EvidenceError(RuntimeError):
    pass


BOOT_LINE = re.compile(
    rb"(?:^|\t)LOG_BOOT_MONOTONIC_NS=(0x[0-9a-fA-F]+)(?:\r?\n|$)",
    re.MULTILINE,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _same_token(left: str, right: str) -> bool:
    try:
        return int(left, 16) == int(right, 16)
    except (TypeError, ValueError):
        return False


def validate_manifest(
    manifest_path: Path,
    *,
    expected_title: str = "PPSA99998",
    expected_app: str = "agc-native-sce",
    expected_boot: str = "",
) -> dict[str, object]:
    """Verify identity, continuity, BYE and bytes before trusting a run."""
    manifest_path = manifest_path.resolve()
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid ps5log manifest: {exc}") from exc
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        raise EvidenceError("manifest identity missing")
    if identity.get("title") != expected_title or identity.get("app") != expected_app:
        raise EvidenceError("manifest title/app identity mismatch")
    boot = str(identity.get("boot", ""))
    if not boot or (expected_boot and not _same_token(boot, expected_boot)):
        raise EvidenceError("manifest boot token mismatch")
    if manifest.get("protocol") != "ps5log/1" or manifest.get("transport") != "tcp":
        raise EvidenceError("manifest protocol/transport mismatch")
    if not manifest.get("hello") or not manifest.get("clean") or not manifest.get("bye"):
        raise EvidenceError("run lacks HELLO/BYE clean completion")
    if manifest.get("gaps") != [] or manifest.get("oversized_lines") != 0:
        raise EvidenceError("run has sequence gaps or oversized records")
    if not isinstance(manifest.get("records"), int) or manifest["records"] <= 0:
        raise EvidenceError("run has no structured records")
    if manifest.get("raw_lines") != 0:
        raise EvidenceError("AGC run unexpectedly contains unsequenced RAW lines")
    log_name = manifest.get("log_path")
    if not isinstance(log_name, str) or Path(log_name).name != log_name:
        raise EvidenceError("unsafe manifest log path")
    log_path = (manifest_path.parent / log_name).resolve()
    if log_path.parent != manifest_path.parent:
        raise EvidenceError("log escaped the runs directory")
    try:
        data = log_path.read_bytes()
    except OSError as exc:
        raise EvidenceError(f"missing ps5log transcript: {exc}") from exc
    actual_hash = sha256(data)
    if actual_hash != manifest.get("sha256") or len(data) != manifest.get("bytes"):
        raise EvidenceError("transcript size/hash does not match manifest")
    match = BOOT_LINE.search(data)
    if not match or not _same_token(match.group(1).decode(), boot):
        raise EvidenceError("HELLO boot and LOG_BOOT_MONOTONIC_NS differ")
    bye_fields = manifest.get("bye_fields")
    if not isinstance(bye_fields, dict) or str(bye_fields.get("seq")) != str(
        manifest.get("last_seq")
    ):
        raise EvidenceError("BYE sequence does not match the final record")
    return {
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "log_path": str(log_path),
        "log_bytes": data,
        "log_sha256": actual_hash,
        "boot": boot,
    }
