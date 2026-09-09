#!/usr/bin/env python3
"""Host contracts for the Remote Play lab wrapper."""

from __future__ import annotations

import importlib.util
import stat
import subprocess
import tempfile
from pathlib import Path
from unittest import mock


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
    assert MODULE.is_chiaki_xprop(
        'WM_CLASS(STRING) = "chiaki", "Chiaki"\n'
        '_NET_WM_NAME(UTF8_STRING) = "Session has quit"\n'
    )
    assert not MODULE.is_chiaki_xprop(
        'WM_CLASS(STRING) = "mutter-x11-frames", "mutter-x11-frames"\n'
    )
    assert MODULE.LINKDEV_COMMIT == "b658657190873f1ae194b732f8dcfdb02543c4aa"
    assert MODULE.DEFAULT_CAPTURE_DIR.parts[-2:] == ("captures", "remoteplay")
    assert MODULE.STREAM_RESOLUTION == "1080p"
    with tempfile.TemporaryDirectory() as directory:
        with mock.patch.object(MODULE, "DEFAULT_CAPTURE_DIR", Path(directory)):
            demo = MODULE.demo_output_path(None, "Xash3D: Phase 5!")
            assert demo.parent.name == "demos"
            assert demo.name.endswith("-xash3d-phase-5.mp4")
    with mock.patch.object(MODULE, "require_program", return_value="/usr/bin/ffmpeg"):
        command = MODULE.recording_command(
            Path("/tmp/demo.mp4"), 60, "4242", ":0",
            title="PS5 homebrew demo: Gears",
        )
        assert command[0] == "/usr/bin/ffmpeg"
        assert command[command.index("-window_id") + 1] == "4242"
        assert "-t" not in command
        assert command[command.index("-movflags") + 1] == "+faststart"
        assert command[-1] == "/tmp/demo.mp4"
        bounded = MODULE.recording_command(
            Path("/tmp/demo.mp4"), 30, "4242", ":0", seconds=12.5
        )
        assert bounded[bounded.index("-t") + 1] == "12.5"
    graceful = mock.Mock()
    graceful.poll.return_value = None
    graceful.stdin = mock.Mock()
    MODULE.finalize_recording_process(graceful)
    graceful.stdin.write.assert_called_once_with(b"q\n")
    graceful.send_signal.assert_not_called()
    graceful.kill.assert_not_called()
    graceful.wait.assert_called_once_with(timeout=10.0)
    fallback = mock.Mock()
    fallback.poll.return_value = None
    fallback.stdin = mock.Mock()
    fallback.wait.side_effect = [
        subprocess.TimeoutExpired("ffmpeg", 10.0),
        subprocess.TimeoutExpired("ffmpeg", 2.0),
        0,
    ]
    MODULE.finalize_recording_process(fallback)
    fallback.send_signal.assert_called_once_with(MODULE.signal.SIGINT)
    fallback.kill.assert_called_once_with()
    assert not MODULE.is_cli_chiaki_stream_process(999_999_999)
    with mock.patch.object(
        MODULE, "chiaki_windows", return_value=[]
    ):
        assert MODULE.ended_cli_stream_pid() is None
        assert MODULE.active_cli_stream_window() is None
    with mock.patch.object(
        MODULE, "chiaki_windows", return_value=["4242"]
    ), mock.patch.object(
        MODULE, "window_pid", return_value=31337
    ), mock.patch.object(
        MODULE, "is_cli_chiaki_stream_process", return_value=True
    ):
        assert MODULE.active_cli_stream_window() == "4242"
    with mock.patch.object(
        MODULE, "chiaki_windows", return_value=["4242"]
    ), mock.patch.object(
        MODULE, "window_pid", return_value=31337
    ), mock.patch.object(
        MODULE, "is_cli_chiaki_stream_process", return_value=False
    ):
        try:
            MODULE.active_cli_stream_window()
        except SystemExit as exc:
            assert "not launched by the isolated" in str(exc)
        else:
            raise AssertionError("non-CLI active stream was not rejected")
    with mock.patch.object(
        MODULE, "chiaki_windows", return_value=["4242", "4343"]
    ):
        try:
            MODULE.active_cli_stream_window()
        except SystemExit as exc:
            assert "multiple active" in str(exc)
        else:
            raise AssertionError("ambiguous active streams were not rejected")
    with mock.patch.object(
        MODULE, "chiaki_windows", return_value=["4242"]
    ), mock.patch.object(
        MODULE, "window_pid", return_value=31337
    ), mock.patch.object(
        MODULE, "is_cli_chiaki_stream_process", return_value=True
    ):
        assert MODULE.ended_cli_stream_pid() == 31337
    with mock.patch.object(
        MODULE, "chiaki_windows", return_value=["4242"]
    ), mock.patch.object(
        MODULE, "window_pid", return_value=31337
    ), mock.patch.object(
        MODULE, "is_cli_chiaki_stream_process", return_value=False
    ):
        try:
            MODULE.ended_cli_stream_pid()
        except SystemExit as exc:
            assert "not launched by the isolated" in str(exc)
        else:
            raise AssertionError("non-CLI ended stream was not rejected")
    with mock.patch.object(
        MODULE, "ended_cli_stream_pid", return_value=31337
    ), mock.patch.object(
        MODULE, "terminate_cli_stream_process"
    ) as terminate, mock.patch.object(
        MODULE, "chiaki_windows", return_value=[]
    ), mock.patch.object(
        MODULE, "acknowledge_quit_dialog",
        side_effect=AssertionError("UI acknowledgement must not be used"),
    ):
        assert MODULE.stop_ended_cli_stream(2.0)
        terminate.assert_called_once_with(31337, 2.0)
    stream_args = mock.Mock(cleanup_wait=2.0)
    with mock.patch.object(
        MODULE, "require_program", return_value="/usr/bin/xdotool"
    ), mock.patch.object(
        MODULE, "stop_ended_cli_stream", return_value=False
    ), mock.patch.object(
        MODULE, "active_cli_stream_window", return_value="4242"
    ), mock.patch.object(
        MODULE, "isolated_chiaki_stream_process",
        side_effect=AssertionError("must reuse the verified active stream"),
    ), mock.patch("builtins.print") as printed:
        MODULE.start_stream(stream_args)
        printed.assert_called_once_with("4242")
    sample = """[General]\nversion=2\n\n[registered_hosts]\n1\\rp_key=@ByteArray(first)\n1\\rp_regist_key=@ByteArray(first-reg)\n1\\server_nickname=PS5-816\n1\\target=1000100\n2\\rp_key=@ByteArray(second)\n2\\rp_regist_key=@ByteArray(second-reg)\n2\\server_nickname=PS5-054\n2\\target=1000100\nsize=2\n\n[settings]\nresolution=720p\n"""
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.conf"
        destination = Path(directory) / "config" / "Chiaki" / "Chiaki.conf"
        source.write_text(sample, encoding="utf-8")
        MODULE.isolate_registered_host_config(
            source, "PS5-054", destination
        )
        isolated = destination.read_text(encoding="utf-8")
        assert "1\\server_nickname=PS5-054" in isolated
        assert "1\\rp_key=@ByteArray(second)" in isolated
        assert "first" not in isolated
        assert "2\\" not in isolated
        assert "size=1" in isolated
        assert "resolution=720p" not in isolated
        assert isolated.count("resolution=1080p") == 1
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    no_settings = sample.replace("\n[settings]\nresolution=720p\n", "\n")
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.conf"
        destination = Path(directory) / "config" / "Chiaki" / "Chiaki.conf"
        source.write_text(no_settings, encoding="utf-8")
        MODULE.isolate_registered_host_config(
            source, "PS5-054", destination
        )
        isolated = destination.read_text(encoding="utf-8")
        assert "[settings]\nresolution=1080p\n" in isolated
    print("Remote Play host contracts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
