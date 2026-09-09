#!/usr/bin/env python3
"""Build/pair Headless LinkDev and control an existing Chiaki X11 stream."""

from __future__ import annotations

import argparse
import os
import re
import signal
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINKDEV = ROOT / "third_party" / "headless-linkdev"
LINKDEV_COMMIT = "b658657190873f1ae194b732f8dcfdb02543c4aa"
DEFAULT_CAPTURE_DIR = ROOT / "research" / "gpu" / "captures" / "remoteplay"
DEFAULT_CHIAKI_CONFIG = (
    Path.home() / "snap" / "chiaki" / "common" / ".config"
    / "Chiaki" / "Chiaki.conf"
)
CHIAKI_ARRAY_LINE_RE = re.compile(
    r"^(?P<index>[0-9]+)\\(?P<key>[^=]+)=(?P<value>.*)$"
)
READY_RE = re.compile(
    r"READY \| PIN: (?P<pin>[0-9]{8}) \| "
    r"Account ID: (?P<account>[A-Za-z0-9+/]+=*) \| Timeout: (?P<timeout>[0-9]+)s"
)
STREAM_RESOLUTION = "1080p"


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


def is_chiaki_xprop(value: str) -> bool:
    """Accept the Chiaki client window, never its Mutter decoration frame."""
    return bool(re.search(r'^WM_CLASS\(STRING\) = "chiaki", "Chiaki"$',
                          value, re.MULTILINE))


def xprop_text(window: str) -> str:
    result = subprocess.run(
        [require_program("xprop"), "-id", window, "WM_CLASS",
         "_NET_WM_NAME"],
        text=True, capture_output=True, check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def is_chiaki_window(window: str) -> bool:
    return window.isdecimal() and is_chiaki_xprop(xprop_text(window))


def window_geometry(window: str) -> tuple[int, int]:
    result = subprocess.run(
        [require_program("xdotool"), "getwindowgeometry", "--shell", window],
        text=True, capture_output=True, check=False,
    )
    fields = dict(re.findall(r"^(WIDTH|HEIGHT)=([0-9]+)$",
                             result.stdout, re.MULTILINE))
    if result.returncode != 0 or set(fields) != {"WIDTH", "HEIGHT"}:
        raise SystemExit("could not read Chiaki dialog geometry")
    return int(fields["WIDTH"]), int(fields["HEIGHT"])


def window_pid(window: str) -> int:
    result = subprocess.run(
        [require_program("xprop"), "-id", window, "_NET_WM_PID"],
        text=True, capture_output=True, check=False,
    )
    match = re.search(r"_NET_WM_PID\(CARDINAL\) = ([0-9]+)", result.stdout)
    if result.returncode != 0 or match is None:
        raise SystemExit("could not identify Chiaki stream process")
    return int(match.group(1))


def is_cli_chiaki_stream_process(pid: int) -> bool:
    try:
        argv = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    if len(argv) < 2:
        return False
    return argv[0].startswith(b"/snap/chiaki/") and \
        argv[0].endswith(b"/usr/local/bin/chiaki") and argv[1] == b"stream"


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


def chiaki_windows(title: str) -> list[str]:
    require_program("xdotool")
    result = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--name",
         rf"^{re.escape(title)}$"],
        text=True, capture_output=True, check=False,
    )
    ids = []
    for line in result.stdout.splitlines():
        window = line.strip()
        if not window.isdecimal():
            continue
        if is_chiaki_window(window):
            ids.append(window)
    return ids


def stream_window() -> str:
    ids = chiaki_windows("Chiaki | Stream")
    if not ids:
        raise SystemExit("no active 'Chiaki | Stream' X11 window")
    if len(ids) != 1:
        raise SystemExit("multiple active 'Chiaki | Stream' client windows")
    return ids[-1]


def active_cli_stream_window() -> str | None:
    """Return one verified isolated CLI stream, refusing ambiguous state."""
    ids = chiaki_windows("Chiaki | Stream")
    if not ids:
        return None
    if len(ids) != 1:
        raise SystemExit("multiple active 'Chiaki | Stream' client windows")
    window = ids[0]
    pid = window_pid(window)
    if not is_cli_chiaki_stream_process(pid):
        raise SystemExit(
            "active stream was not launched by the isolated Chiaki CLI helper"
        )
    return window


def acknowledge_quit_dialog(wait: float) -> bool:
    """Acknowledge Chiaki's expected handoff dialog with focus restoration."""
    dialogs = chiaki_windows("Session has quit")
    if not dialogs:
        print("no Chiaki 'Session has quit' dialog")
        return False
    if len(dialogs) != 1:
        raise SystemExit("multiple Chiaki 'Session has quit' client dialogs")
    dialog = dialogs[0]
    xdotool = require_program("xdotool")
    previous = subprocess.check_output(
        [xdotool, "getactivewindow"], text=True
    ).strip()
    pointer = subprocess.check_output(
        [xdotool, "getmouselocation", "--shell"], text=True
    )
    pointer_fields = dict(re.findall(r"^(X|Y)=(-?[0-9]+)$",
                                     pointer, re.MULTILINE))
    try:
        subprocess.run(
            [xdotool, "windowactivate", "--sync", dialog], check=True
        )
        subprocess.run(
            [xdotool, "key", "--clearmodifiers", "Return"], check=True
        )
        # Qt 5 may ignore synthetic Return even after activation. If the
        # dialog remains, click the stable bottom-right QMessageBox action
        # relative to the client geometry (never absolute screen geometry).
        time.sleep(0.15)
        if chiaki_windows("Session has quit"):
            width, height = window_geometry(dialog)
            subprocess.run(
                [xdotool, "mousemove", "--sync", "--window", dialog,
                 str(width - 68), str(height - 45), "click", "1"],
                check=True,
            )
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if not chiaki_windows("Session has quit") and \
                    not chiaki_windows("Chiaki | Stream"):
                print(f"acknowledged Chiaki handoff dialog window={dialog}")
                return True
            time.sleep(0.1)
        raise SystemExit("Chiaki handoff dialog or ended stream did not close")
    finally:
        if set(pointer_fields) == {"X", "Y"}:
            subprocess.run(
                [xdotool, "mousemove", "--sync", pointer_fields["X"],
                 pointer_fields["Y"]],
                check=False,
            )
        active = subprocess.run(
            [xdotool, "getactivewindow"], text=True,
            capture_output=True, check=False,
        ).stdout.strip()
        # Restore only from a Chiaki-owned focus. A newer non-Chiaki focus is
        # an operator decision and must never be replaced by stale state.
        if previous != dialog and is_chiaki_window(active) and \
                xprop_text(previous):
            subprocess.run(
                [xdotool, "windowactivate", "--sync", previous],
                check=False,
            )


def acknowledge(args: argparse.Namespace) -> None:
    acknowledge_quit_dialog(args.wait)


def ended_cli_stream_pid() -> int | None:
    """Return the exact isolated CLI process behind an ended stream dialog."""
    dialogs = chiaki_windows("Session has quit")
    if not dialogs:
        return None
    if len(dialogs) != 1:
        raise SystemExit("multiple Chiaki 'Session has quit' client dialogs")
    pid = window_pid(dialogs[0])
    if not is_cli_chiaki_stream_process(pid):
        raise SystemExit(
            "ended stream was not launched by the isolated Chiaki CLI helper"
        )
    return pid


def set_ini_value(
    lines: list[str], section_name: str, key: str, value: str
) -> list[str]:
    """Set one QSettings INI value without disturbing unrelated settings."""
    output: list[str] = []
    in_section = False
    saw_section = False
    wrote_value = False
    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    for line in lines:
        stripped = line.rstrip("\r\n")
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not wrote_value:
                output.append(f"{key}={value}{newline}")
                wrote_value = True
            in_section = stripped[1:-1] == section_name
            saw_section = saw_section or in_section
            output.append(line)
            continue
        if in_section and stripped.partition("=")[0] == key:
            if not wrote_value:
                output.append(f"{key}={value}{newline}")
                wrote_value = True
        else:
            output.append(line)
    if in_section and not wrote_value:
        output.append(f"{key}={value}{newline}")
    elif not saw_section:
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += newline
        output.extend([
            newline if output else "",
            f"[{section_name}]{newline}",
            f"{key}={value}{newline}",
        ])
    return output


def isolate_registered_host_config(
    source: Path, nickname: str, destination: Path
) -> None:
    """Write a private QSettings copy with nickname as registered host 1.

    Chiaki 2.1.1's stream CLI returns after the first non-matching host, so a
    later registered host is otherwise unreachable. Keeping only the selected
    array element also preserves its PS5 target, unlike the explicit-key CLI
    path, which defaults to PS4.
    """
    try:
        lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as exc:
        raise SystemExit(f"could not read Chiaki configuration: {source}") from exc

    section = ""
    registered: dict[int, dict[str, str]] = {}
    for line in lines:
        stripped = line.rstrip("\r\n")
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        if section != "registered_hosts":
            continue
        match = CHIAKI_ARRAY_LINE_RE.match(stripped)
        if match:
            registered.setdefault(int(match["index"]), {})[
                match["key"]
            ] = match["value"]

    matches = [
        index for index, values in registered.items()
        if values.get("server_nickname") == nickname
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"expected one registered Chiaki host named {nickname!r}; "
            f"found {len(matches)}"
        )
    selected = matches[0]
    selected_values = registered[selected]
    required = {"rp_key", "rp_regist_key", "server_nickname", "target"}
    if not required.issubset(selected_values):
        raise SystemExit("selected Chiaki registration is incomplete")
    try:
        target = int(selected_values["target"])
    except ValueError as exc:
        raise SystemExit("selected Chiaki target is invalid") from exc
    if target < 1_000_000:
        raise SystemExit("selected Chiaki registration is not a PS5 target")

    output: list[str] = []
    section = ""
    saw_size = False
    for line in lines:
        stripped = line.rstrip("\r\n")
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            output.append(line)
            continue
        if section != "registered_hosts":
            output.append(line)
            continue
        match = CHIAKI_ARRAY_LINE_RE.match(stripped)
        if match:
            if int(match["index"]) == selected:
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                output.append(
                    f"1\\{match['key']}={match['value']}{newline}"
                )
            continue
        if stripped.startswith("size="):
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            output.append(f"size=1{newline}")
            saw_size = True
            continue
        output.append(line)
    if not saw_size:
        raise SystemExit("Chiaki registered_hosts array has no size entry")

    output = set_ini_value(output, "settings", "resolution", STREAM_RESOLUTION)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.write_text("".join(output), encoding="utf-8")
    destination.chmod(0o600)


def isolated_chiaki_stream_process(
    nickname: str, host: str, source: Path
) -> subprocess.Popen[bytes]:
    """Launch only Chiaki's stream window with an isolated registered host."""
    require_program("snap")
    common = source.parents[2]
    temporary = Path(tempfile.mkdtemp(prefix=".chiaki-cli-", dir=common))
    config_home = temporary / "config"
    isolated = config_home / "Chiaki" / "Chiaki.conf"
    try:
        isolate_registered_host_config(source, nickname, isolated)
        quoted = [
            shlex.quote(str(config_home)),
            shlex.quote(nickname),
            shlex.quote(host),
            shlex.quote(str(isolated)),
            shlex.quote(str(isolated.parent)),
            shlex.quote(str(config_home)),
            shlex.quote(str(temporary)),
        ]
        command = (
            f'XDG_CONFIG_HOME={quoted[0]} "$SNAP/usr/local/bin/chiaki" '
            f"stream {quoted[1]} {quoted[2]}; status=$?; "
            f"rm -f {quoted[3]} {quoted[5]}/pulse/cookie; "
            f"rmdir {quoted[4]} {quoted[5]}/pulse {quoted[5]} {quoted[6]}; "
            "exit $status"
        )
        return subprocess.Popen(
            ["snap", "run", "--shell", "chiaki", "-c", command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def start_stream(args: argparse.Namespace) -> None:
    xdotool = require_program("xdotool")
    stop_ended_cli_stream(args.cleanup_wait)
    existing = active_cli_stream_window()
    if existing is not None:
        print(existing)
        return
    previous_window = subprocess.check_output(
        [xdotool, "getactivewindow"], text=True
    ).strip()
    process = isolated_chiaki_stream_process(
        args.nickname, args.host, Path(args.chiaki_config).expanduser()
    )
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        returncode = process.poll()
        if returncode is not None:
            raise SystemExit(
                f"Chiaki stream command exited before opening a window "
                f"(status {returncode})"
            )
        try:
            window = stream_window()
            # Restore the launch-time workspace only if Chiaki still owns the
            # focus. If the operator changed focus meanwhile, preserve that
            # newer choice instead of activating a stale assumed window.
            active = subprocess.check_output(
                [xdotool, "getactivewindow"], text=True
            ).strip()
            if active == window and previous_window != window:
                restored = subprocess.run(
                    [xdotool, "windowactivate", "--sync", previous_window],
                    check=False,
                )
                if restored.returncode != 0:
                    raise SystemExit("could not restore workspace focus")
            print(window)
            return
        except SystemExit:
            time.sleep(0.25)
    raise SystemExit("Chiaki stream window did not appear")


def snap_signal(pid: int, signal_name: str) -> None:
    if signal_name not in {"TERM", "KILL"}:
        raise ValueError("unsupported signal")
    if not is_cli_chiaki_stream_process(pid):
        raise SystemExit("refusing to signal a non-CLI Chiaki stream process")
    result = subprocess.run(
        [require_program("snap"), "run", "--shell", "chiaki", "-c",
         f"kill -{signal_name} {pid}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"could not send SIG{signal_name} to Chiaki stream")


def terminate_cli_stream_process(pid: int, wait: float) -> None:
    """Terminate one verified isolated CLI stream without UI interaction."""
    if not is_cli_chiaki_stream_process(pid):
        raise SystemExit("refusing to terminate a non-CLI Chiaki process")
    snap_signal(pid, "TERM")
    term_deadline = time.monotonic() + max(wait, 0.1)
    while time.monotonic() < term_deadline and \
            is_cli_chiaki_stream_process(pid):
        time.sleep(0.1)
    if is_cli_chiaki_stream_process(pid):
        snap_signal(pid, "KILL")
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not is_cli_chiaki_stream_process(pid):
            return
        time.sleep(0.1)
    raise SystemExit("Chiaki CLI stream process did not exit")


def stop_ended_cli_stream(wait: float) -> bool:
    """Clean an ended isolated stream by PID, never by dialog interaction."""
    pid = ended_cli_stream_pid()
    if pid is None:
        return False
    terminate_cli_stream_process(pid, wait)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not chiaki_windows("Session has quit") and \
                not chiaki_windows("Chiaki | Stream"):
            print(f"closed ended Chiaki CLI stream pid={pid}")
            return True
        time.sleep(0.1)
    raise SystemExit("ended Chiaki CLI stream windows did not disappear")


def stop_stream(args: argparse.Namespace) -> None:
    """Close the exact CLI stream and verify its confined process exits."""
    if stop_ended_cli_stream(args.wait):
        return
    window = stream_window()
    pid = window_pid(window)
    if not is_cli_chiaki_stream_process(pid):
        raise SystemExit(
            "active stream was not launched by the isolated Chiaki CLI helper"
        )
    subprocess.run(
        [require_program("xdotool"), "windowclose", window], check=True
    )
    normal_deadline = time.monotonic() + args.wait
    while time.monotonic() < normal_deadline and \
            is_cli_chiaki_stream_process(pid):
        time.sleep(0.1)
    if is_cli_chiaki_stream_process(pid):
        terminate_cli_stream_process(pid, 1.0)
    print(f"closed Chiaki CLI stream window={window} pid={pid}")


def output_path(value: str | None, suffix: str) -> Path:
    if value:
        path = Path(value).expanduser()
    else:
        timestamp = time.strftime("%Y%m%dT%H%M%S")
        path = DEFAULT_CAPTURE_DIR / f"ps5-{timestamp}.{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def demo_output_path(value: str | None, name: str) -> Path:
    if value:
        return output_path(value, "mp4")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise SystemExit("demo name must contain a letter or number")
    timestamp = time.strftime("%Y%m%dT%H%M%S")
    path = DEFAULT_CAPTURE_DIR / "demos" / f"{timestamp}-{slug}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def recording_command(
    path: Path, fps: int, window: str, display: str,
    seconds: float | None = None, title: str | None = None,
) -> list[str]:
    if fps <= 0:
        raise SystemExit("fps must be greater than zero")
    if seconds is not None and seconds <= 0:
        raise SystemExit("seconds must be greater than zero")
    command = [
        require_program("ffmpeg"), "-hide_banner", "-loglevel", "warning",
        "-y", "-f", "x11grab", "-framerate", str(fps),
        "-window_id", window, "-i", display,
    ]
    if seconds is not None:
        command.extend(["-t", str(seconds)])
    command.extend([
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    ])
    if title:
        command.extend(["-metadata", f"title={title}"])
    command.append(str(path))
    return command


def capture_window(window: str, path: Path) -> None:
    subprocess.run(
        [require_program("import"), "-window", window, str(path)],
        check=True,
    )


def image_signal(path: Path) -> float:
    """Return normalized RGB mean in [0, 1] for a captured frame."""
    result = subprocess.run(
        [require_program("convert"), str(path), "-colorspace", "RGB",
         "-format", "%[fx:mean]", "info:"],
        text=True, capture_output=True, check=True,
    )
    try:
        value = float(result.stdout.strip())
    except ValueError as exc:
        raise SystemExit("could not measure Remote Play frame signal") from exc
    if not 0.0 <= value <= 1.0:
        raise SystemExit("Remote Play frame signal is outside [0, 1]")
    return value


def wait_for_decoded_frame(
    window: str, path: Path, wait: float, minimum_signal: float,
) -> float:
    """Capture until Chiaki has decoded a non-black frame, or fail closed."""
    if wait < 0.0:
        raise SystemExit("decode wait must be non-negative")
    if not 0.0 <= minimum_signal <= 1.0:
        raise SystemExit("minimum signal must be within [0, 1]")
    deadline = time.monotonic() + wait
    while True:
        capture_window(window, path)
        signal_value = image_signal(path)
        if signal_value > minimum_signal:
            return signal_value
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"Remote Play stayed black for {wait:g}s "
                f"(signal={signal_value:.6f}, capture={path})"
            )
        time.sleep(0.25)


def screenshot(args: argparse.Namespace) -> None:
    path = output_path(args.output, "png")
    window = stream_window()
    if args.require_decoded:
        signal_value = wait_for_decoded_frame(
            window, path, args.wait, args.minimum_signal,
        )
        print(f"decoded_signal={signal_value:.6f}")
    else:
        capture_window(window, path)
    print(path)


def record(args: argparse.Namespace) -> None:
    path = output_path(args.output, "mp4")
    display = os.environ.get("DISPLAY")
    if not display:
        raise SystemExit("DISPLAY is not set; X11 capture is unavailable")
    subprocess.run(recording_command(
        path, args.fps, stream_window(), display, seconds=args.seconds,
    ), check=True)
    print(path)


def finalize_recording_process(
    process: subprocess.Popen[bytes], graceful_wait: float = 10.0,
) -> None:
    """Finalize ffmpeg through its native command, with bounded fallbacks."""
    if process.poll() is not None:
        return
    try:
        if process.stdin is not None:
            process.stdin.write(b"q\n")
            process.stdin.flush()
            process.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    try:
        process.wait(timeout=graceful_wait)
        return
    except subprocess.TimeoutExpired:
        pass
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=2.0)
        return
    except subprocess.TimeoutExpired:
        pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=2.0)


def record_demo(args: argparse.Namespace) -> None:
    """Record a shareable presentation until Enter, Ctrl+C or a time limit."""
    path = demo_output_path(args.output, args.name)
    display = os.environ.get("DISPLAY")
    if not display:
        raise SystemExit("DISPLAY is not set; X11 capture is unavailable")
    command = recording_command(
        path, args.fps, stream_window(), display,
        seconds=args.seconds, title=f"PS5 homebrew demo: {args.name}",
    )
    # Keep ffmpeg's stdin private so both Enter and Ctrl+C can send its
    # graceful ``q`` command.  Delivering SIGINT directly can interrupt the
    # MP4 muxer before it writes the moov atom, leaving an unplayable file.
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    print(f"Recording PS5 demo to {path}", flush=True)

    try:
        if args.seconds is None:
            try:
                input("Press Enter to stop and finalize the video... ")
            except EOFError:
                print("stdin closed; finalizing the video", file=sys.stderr)
            finalize_recording_process(process)
        process.wait()
    except KeyboardInterrupt:
        finalize_recording_process(process)
    if process.returncode not in {0, 255}:
        raise SystemExit(f"ffmpeg recording failed with status {process.returncode}")
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit("ffmpeg did not produce a video")
    print(f"Finalized shareable video: {path}")


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
    stream_cmd.add_argument("--cleanup-wait", type=float, default=2.0)
    stream_cmd.add_argument(
        "--chiaki-config", default=str(DEFAULT_CHIAKI_CONFIG),
        help=argparse.SUPPRESS,
    )
    stream_cmd.set_defaults(func=start_stream)
    acknowledge_cmd = commands.add_parser("acknowledge-quit")
    acknowledge_cmd.add_argument("--wait", type=float, default=5.0)
    acknowledge_cmd.set_defaults(func=acknowledge)
    stop_cmd = commands.add_parser("stop-stream")
    stop_cmd.add_argument("--wait", type=float, default=2.0)
    stop_cmd.set_defaults(func=stop_stream)
    shot_cmd = commands.add_parser("screenshot")
    shot_cmd.add_argument("--output")
    shot_cmd.add_argument("--require-decoded", action="store_true")
    shot_cmd.add_argument("--wait", type=float, default=10.0)
    shot_cmd.add_argument("--minimum-signal", type=float, default=0.002)
    shot_cmd.set_defaults(func=screenshot)
    record_cmd = commands.add_parser("record")
    record_cmd.add_argument("--output")
    record_cmd.add_argument("--seconds", type=float, default=10)
    record_cmd.add_argument("--fps", type=int, default=60)
    record_cmd.set_defaults(func=record)
    demo_cmd = commands.add_parser("record-demo")
    demo_cmd.add_argument("--name", required=True)
    demo_cmd.add_argument("--output")
    demo_cmd.add_argument(
        "--seconds", type=float,
        help="optional fixed duration; otherwise stop with Enter or Ctrl+C",
    )
    demo_cmd.add_argument("--fps", type=int, default=60)
    demo_cmd.set_defaults(func=record_demo)
    return result


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
