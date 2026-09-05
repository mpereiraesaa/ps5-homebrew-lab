#!/usr/bin/env python3
"""Launch/observe PPSA99998 through ps5logd; no console filesystem access."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "projects/logging_server/runs"
CAPTURES = ROOT / "research/gpu/captures/runtime"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "research/gpu/tools"))
from stage_b_guard import classify  # noqa: E402
from ps5log_evidence import EvidenceError, validate_manifest  # noqa: E402


def iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def server_ready(host: str = "127.0.0.1", port: int = 9300) -> bool:
    try:
        with socket.create_connection((host, port), 0.25):
            return True
    except OSError:
        return False


def run_helper(host: str, helper: Path, timeout: float = 5.0) -> str:
    output = bytearray()
    with socket.create_connection((host, 9021), timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(helper.read_bytes())
        sock.shutdown(socket.SHUT_WR)
        try:
            while chunk := sock.recv(65536):
                output.extend(chunk)
        except socket.timeout:
            pass
    return output.decode("utf-8", "replace")


def candidates(baseline: set[Path]) -> list[Path]:
    return sorted(
        (path for path in RUNS.glob("*_PPSA99998_agc-native-sce_*.log")
         if path.resolve() not in baseline),
        key=lambda path: path.stat().st_mtime_ns,
    )


def atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True, help="PS5 IPv4 address")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--close-on-safe", action="store_true")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--artifact", type=Path, default=
                        ROOT / "legacy/apps/agc-native-sce/dist-stage-g/PPSA99998/eboot.bin")
    args = parser.parse_args()
    if not server_ready():
        print("ps5logd is not listening on localhost:9300", file=sys.stderr)
        return 6
    RUNS.mkdir(parents=True, exist_ok=True)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    baseline = {path.resolve() for path in RUNS.glob("*.log")}
    started = time.monotonic()
    launch_output = ""
    artifact_hash = (hashlib.sha256(args.artifact.read_bytes()).hexdigest()
                     if args.artifact.is_file() else None)
    if args.launch:
        try:
            launch_output = run_helper(
                args.host, ROOT / "tools/bigapp-control/launch-agc-native-sce.elf")
            print(launch_output, end="" if launch_output.endswith("\n") else "\n")
            match = re.search(r"launch rc=0x([0-9a-fA-F]{8})", launch_output)
            if (not match or int(match.group(1), 16) >= 0x80000000 or
                    "launch refused" in launch_output):
                raise RuntimeError(
                    "exact-title launch helper returned a failing launch rc")
        except (OSError, RuntimeError) as exc:
            print(f"launch failed: {exc}", file=sys.stderr)
            return 5

    active: Path | None = None
    seen = 0
    manifest_path: Path | None = None
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        fresh = candidates(baseline)
        if fresh:
            active = fresh[-1]
            data = active.read_bytes()
            if len(data) > seen:
                sys.stdout.write(data[seen:].decode("utf-8", "replace"))
                sys.stdout.flush()
                seen = len(data)
            candidate_manifest = active.with_suffix(".json")
            if candidate_manifest.is_file():
                manifest_path = candidate_manifest
                break
        time.sleep(0.05)
    if not active or not manifest_path:
        print("no finalized fresh ps5logd run", file=sys.stderr)
        return 4
    try:
        evidence = validate_manifest(manifest_path)
    except EvidenceError as exc:
        print(f"invalid network evidence: {exc}", file=sys.stderr)
        return 3
    log = bytes(evidence["log_bytes"]).decode("utf-8", "replace")
    decision = classify(log)
    run_id = str(evidence["manifest"]["run_id"])
    copied_log = CAPTURES / f"{run_id}.log"
    copied_manifest = CAPTURES / f"{run_id}.ps5log.json"
    shutil.copyfile(evidence["log_path"], copied_log)
    shutil.copyfile(evidence["manifest_path"], copied_manifest)
    capture = {
        "schema": 3, "transport": "ps5log/1", "run_id": run_id,
        "captured_utc": iso_utc(), "artifact": str(args.artifact),
        "artifact_sha256": artifact_hash, "ps5log_manifest": str(copied_manifest),
        "ps5log_transcript": str(copied_log), "boot": evidence["boot"],
        "log_sha256": evidence["log_sha256"], "decision": decision,
        "launch_output": launch_output,
        "duration_seconds": time.monotonic() - started,
    }
    capture_path = CAPTURES / f"{run_id}.capture.json"
    atomic_json(capture_path, capture)
    print(json.dumps({"event": "agc_network_observability_result",
                      "run_id": run_id, "state": decision["state"],
                      "close_allowed": decision["close_allowed"],
                      "manifest": str(capture_path.relative_to(ROOT))},
                     sort_keys=True))
    if args.close_on_safe and decision["close_allowed"]:
        close = subprocess.run([
            sys.executable, str(ROOT / "tools/night_supervisor.py"),
            "--host", args.host, "--expected-boot-token", str(evidence["boot"]),
            "--expected-log-sha256", str(evidence["log_sha256"]),
            "--expected-ps5log-manifest", str(manifest_path),
            "close-agc-native-sce",
        ], check=False)
        # The title normally exits immediately after its verified BYE.  A
        # close helper return of 2 means the exact title was already absent,
        # which is the desired terminal state rather than a failed cleanup.
        if close.returncode not in (0, 2):
            return close.returncode
    return 0 if decision["completion_proven"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
