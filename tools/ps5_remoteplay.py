#!/usr/bin/env python3
"""Build/pair Headless LinkDev and capture an active Chiaki X11 stream."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINKDEV = ROOT / "third_party" / "headless-linkdev"
LINKDEV_COMMIT = "b658657190873f1ae194b732f8dcfdb02543c4aa"
DEFAULT_CAPTURE_DIR = ROOT / "research" / "gpu" / "captures" / "remoteplay"
READY_RE = re.compile(
    r"READY \| PIN: (?P<pin>[0-9]{8}) \| "
    r"Account ID: (?P<account>[A-Za-z0-9+/]+=*) \| Timeout: (?P<timeout>[0-9]+)s"
)


def require_program(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"required program not found: {name}")
    return path


def parse_ready(line: str) -> tuple[str, str, int] | None:
    match = READY_RE.search(line)
    if match is None:
        return None
    return match["pin"], match["account"], int(match["timeout"])


def sdk_path(explicit: str | None) -> Path:
    candidates = [
        Path(explicit).expanduser() if explicit else None,
        Path(os.environ["PS5_PAYLOAD_SDK"]).expanduser()
        if os.environ.get("PS5_PAYLOAD_SDK") else None,
        ROOT.parent / "ps5debug-NG" / "ps5-payload-sdk" / "install",
        ROOT / "third_party" / "ps5-native-app-boilerplate" / ".deps"
        / "native" / "ps5-payload-sdk",
    ]
    for candidate in candidates:
        if candidate and (candidate / "toolchain" / "prospero.mk").is_file() \
                and (candidate / "target" / "lib" / "crt1.o").is_file():
            return candidate.resolve()
    raise SystemExit("no complete PS5 Payload SDK found; pass --sdk")


def verify_linkdev_source() -> None:
    if not LINKDEV.is_dir():
        raise SystemExit(
            "missing third_party/headless-linkdev; clone the pinned upstream first"
        )
    head = subprocess.check_output(
        ["git", "-C", str(LINKDEV), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != LINKDEV_COMMIT:
        raise SystemExit(f"unexpected headless-linkdev revision: {head}")


def build(args: argparse.Namespace) -> None:
    verify_linkdev_source()
    env = os.environ.copy()
    env["PS5_PAYLOAD_SDK"] = str(sdk_path(args.sdk))
    subprocess.run(["make", "test"], cwd=LINKDEV, env=env, check=True)
    subprocess.run(["make"], cwd=LINKDEV, env=env, check=True)
    print(LINKDEV / "headless-linkdev.elf")


def pair(args: argparse.Namespace) -> None:
    verify_linkdev_source()
    payload = LINKDEV / "headless-linkdev.elf"
    if not payload.is_file():
        raise SystemExit("payload is not built; run the build command first")
    deadline = time.monotonic() + args.wait
    with socket.create_connection((args.host, args.port), timeout=5) as conn:
        conn.sendall(payload.read_bytes())
        conn.shutdown(socket.SHUT_WR)
        conn.settimeout(args.wait)
        stream = conn.makefile("r", encoding="utf-8", errors="replace")
        for line in stream:
            line = line.rstrip()
            print(line, flush=True)
            if parse_ready(line):
                print(
                    "Enter the PIN and Account ID in Chiaki now; "
                    "this command does not persist them.",
                    file=sys.stderr,
                )
            if "Pairing completed successfully" in line:
                return
            if "ERROR:" in line:
                raise SystemExit("headless pairing failed")
            if time.monotonic() >= deadline:
                raise SystemExit("headless pairing timed out")
    raise SystemExit("elfldr connection closed before pairing completed")


def stream_window() -> str:
    require_program("xdotool")
    result = subprocess.run(
        ["xdotool", "search", "--name", r"^Chiaki \| Stream$"],
        text=True, capture_output=True, check=False,
    )
    ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not ids:
        raise SystemExit("no active 'Chiaki | Stream' X11 window")
    return ids[-1]


def start_stream(args: argparse.Namespace) -> None:
    chiaki = require_program("chiaki")
    subprocess.Popen(
        [chiaki, "stream", args.nickname, args.host],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        try:
            print(stream_window())
            return
        except SystemExit:
            time.sleep(0.25)
    raise SystemExit("Chiaki stream window did not appear")


def output_path(value: str | None, suffix: str) -> Path:
    if value:
        path = Path(value).expanduser()
    else:
        timestamp = time.strftime("%Y%m%dT%H%M%S")
        path = DEFAULT_CAPTURE_DIR / f"ps5-{timestamp}.{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def screenshot(args: argparse.Namespace) -> None:
    path = output_path(args.output, "png")
    subprocess.run(
        [require_program("import"), "-window", stream_window(), str(path)],
        check=True,
    )
    print(path)


def record(args: argparse.Namespace) -> None:
    path = output_path(args.output, "mp4")
    display = os.environ.get("DISPLAY")
    if not display:
        raise SystemExit("DISPLAY is not set; X11 capture is unavailable")
    subprocess.run(
        [
            require_program("ffmpeg"), "-hide_banner", "-loglevel", "warning",
            "-y", "-f", "x11grab", "-framerate", str(args.fps),
            "-window_id", stream_window(), "-i", display,
            "-t", str(args.seconds), "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "18", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )
    print(path)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    commands = result.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build")
    build_cmd.add_argument("--sdk")
    build_cmd.set_defaults(func=build)
    pair_cmd = commands.add_parser("pair")
    pair_cmd.add_argument("--host", required=True)
    pair_cmd.add_argument("--port", type=int, default=9021)
    pair_cmd.add_argument("--wait", type=int, default=330)
    pair_cmd.set_defaults(func=pair)
    stream_cmd = commands.add_parser("stream")
    stream_cmd.add_argument("--host", required=True)
    stream_cmd.add_argument("--nickname", required=True)
    stream_cmd.add_argument("--wait", type=int, default=20)
    stream_cmd.set_defaults(func=start_stream)
    shot_cmd = commands.add_parser("screenshot")
    shot_cmd.add_argument("--output")
    shot_cmd.set_defaults(func=screenshot)
    record_cmd = commands.add_parser("record")
    record_cmd.add_argument("--output")
    record_cmd.add_argument("--seconds", type=float, default=10)
    record_cmd.add_argument("--fps", type=int, default=60)
    record_cmd.set_defaults(func=record)
    return result


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
