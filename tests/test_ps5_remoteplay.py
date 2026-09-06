#!/usr/bin/env python3
"""Host contracts for the Remote Play lab wrapper."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
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
    assert MODULE.LINKDEV_COMMIT == "b658657190873f1ae194b732f8dcfdb02543c4aa"
    assert MODULE.DEFAULT_CAPTURE_DIR.parts[-2:] == ("captures", "remoteplay")

    candidates = [
        ("100", ("mutter-x11-frames", "mutter-x11-frames")),
        ("200", ("chiaki", "Chiaki")),
    ]
    assert MODULE.select_stream_window(candidates) == "200"
    assert MODULE.chiaki_client_ids(candidates) == ["200"]
    assert MODULE.select_quit_dialog(candidates) == "200"
    try:
        MODULE.select_stream_window([
            ("200", ("chiaki", "Chiaki")),
            ("201", ("chiaki", "Chiaki")),
        ])
    except SystemExit as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("ambiguous Chiaki surfaces must fail closed")

    try:
        MODULE.select_quit_dialog([
            ("200", ("chiaki", "Chiaki")),
            ("201", ("chiaki", "Chiaki")),
        ])
    except SystemExit as exc:
        assert "ambiguous acknowledgement" in str(exc)
    else:
        raise AssertionError("ambiguous quit dialogs must fail closed")

    with mock.patch.object(MODULE, "xdotool_shell_values", return_value={
        "WIDTH": 500, "HEIGHT": 315,
    }):
        assert MODULE.window_size("400") == (500, 315)

    with mock.patch.object(MODULE, "window_size", return_value=(500, 315)), \
            mock.patch.object(MODULE, "pointer_position", return_value=(9, 10)), \
            mock.patch.object(MODULE, "require_program", return_value="xdotool"), \
            mock.patch.object(MODULE.subprocess, "run") as run:
        MODULE.click_quit_ok("400")
        assert run.call_args_list == [
            mock.call([
                "xdotool", "mousemove", "--sync", "--window", "400", "430",
                "277", "click", "1",
            ], check=True),
            mock.call(
                ["xdotool", "mousemove", "--sync", "9", "10"], check=True
            ),
        ]

    with mock.patch.object(MODULE, "active_window", return_value="300"), \
            mock.patch.object(MODULE, "window_exists", return_value=True), \
            mock.patch.object(MODULE.subprocess, "run") as run:
        assert not MODULE.restore_focus_if_chiaki_stole_it("100", ["200"])
        run.assert_not_called()

    with mock.patch.object(MODULE, "active_window", return_value="200"), \
            mock.patch.object(MODULE, "window_exists", return_value=True), \
            mock.patch.object(MODULE, "require_program", return_value="xdotool"), \
            mock.patch.object(MODULE.subprocess, "run") as run:
        assert MODULE.restore_focus_if_chiaki_stole_it("100", ["200"])
        run.assert_called_once_with(
            ["xdotool", "windowactivate", "--sync", "100"], check=True
        )

    with mock.patch.object(MODULE, "require_program", return_value="chiaki"), \
            mock.patch.object(MODULE, "quit_dialog_candidates", return_value=[
                ("400", ("chiaki", "Chiaki")),
            ]):
        try:
            MODULE.start_stream(mock.Mock())
        except SystemExit as exc:
            assert "acknowledge-quit" in str(exc)
        else:
            raise AssertionError(
                "a pending quit dialog must block stream restart"
            )

    args = mock.Mock(wait=5)
    output = io.StringIO()
    with mock.patch.object(MODULE, "quit_dialog_candidates", return_value=[
            ("400", ("chiaki", "Chiaki")),
            ]), \
            mock.patch.object(MODULE, "stream_window_ids", return_value=["200"]), \
            mock.patch.object(
                MODULE, "window_classes", return_value=("chiaki", "Chiaki")
            ), \
            mock.patch.object(MODULE, "active_window", return_value="300"), \
            mock.patch.object(MODULE, "click_quit_ok") as click, \
            mock.patch.object(
                MODULE, "wait_for_windows_to_close", return_value=True
            ) as wait, \
            mock.patch.object(
                MODULE, "restore_focus_after_acknowledgement", return_value=True
            ), redirect_stdout(output):
        MODULE.acknowledge_quit(args)
    click.assert_called_once_with("400")
    wait.assert_called_once_with(["400", "200"], 5)
    assert '"stream_closed": true' in output.getvalue()
    assert '"focus": "restored"' in output.getvalue()
    print("Remote Play host contracts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
