#!/usr/bin/env python3
"""Host contracts for the Remote Play lab wrapper."""

from __future__ import annotations

import importlib.util
import stat
import tempfile
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
    assert MODULE.is_chiaki_xprop(
        'WM_CLASS(STRING) = "chiaki", "Chiaki"\n'
        '_NET_WM_NAME(UTF8_STRING) = "Session has quit"\n'
    )
    assert not MODULE.is_chiaki_xprop(
        'WM_CLASS(STRING) = "mutter-x11-frames", "mutter-x11-frames"\n'
    )
    assert MODULE.LINKDEV_COMMIT == "b658657190873f1ae194b732f8dcfdb02543c4aa"
    assert MODULE.DEFAULT_CAPTURE_DIR.parts[-2:] == ("captures", "remoteplay")
    assert not MODULE.is_cli_chiaki_stream_process(999_999_999)
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
        assert "resolution=720p" in isolated
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    print("Remote Play host contracts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
