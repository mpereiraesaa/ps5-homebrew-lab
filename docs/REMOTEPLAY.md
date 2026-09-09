# Remote Play observability

The active lab workflow reuses Chiaki's existing registered `PS5-054` entry;
it did not require pairing or re-registration. As an optional recovery tool,
the lab retains
[`blackbearreloaded/headless-linkdev`](https://github.com/blackbearreloaded/headless-linkdev)
at commit `b658657190873f1ae194b732f8dcfdb02543c4aa`. Its build and parser are
host-tested, but it is not part of normal stream startup. Never invoke the
pairing path merely to restart an existing stream.

Remote Play complements `ps5log/1`: telemetry remains the source of truth for
machine-readable renderer state, while the video stream provides direct visual
observation, screenshots and bounded recordings.

## Optional pairing recovery

Clone the pinned public dependency into the ignored third-party tree:

```sh
git clone https://github.com/blackbearreloaded/headless-linkdev.git \
  third_party/headless-linkdev
git -C third_party/headless-linkdev checkout \
  b658657190873f1ae194b732f8dcfdb02543c4aa
python3 tools/ps5_remoteplay.py build
```

Generate a one-time pairing PIN and Account ID:

```sh
python3 tools/ps5_remoteplay.py pair --host "$PS5_HOST"
```

Enter both values in Chiaki before the five-minute timeout. They are printed
only to the invoking terminal and are never written by the wrapper. Do not
redirect this command, attach it to telemetry or commit Chiaki's credential
store.

## Stream and capture

After the console has been registered:

```sh
python3 tools/ps5_remoteplay.py stream \
  --host "$PS5_HOST" --nickname PS5-054
python3 tools/ps5_remoteplay.py screenshot
python3 tools/ps5_remoteplay.py record --seconds 30
python3 tools/ps5_remoteplay.py record-demo --name "Xash3D Phase 5"
python3 tools/ps5_remoteplay.py stop-stream
```

`stream` invokes Chiaki's console mode directly and opens only
`Chiaki | Stream`; the discovery/client window is not required. Chiaki 2.1.1
incorrectly stops after the first non-matching registered nickname and its
explicit-key fallback defaults to the PS4 target. The helper works around both
upstream limitations with a mode-0600 temporary configuration containing only
the requested, already registered PS5 entry. The real configuration is never
modified, no credential is printed or placed on the command line, and the
temporary copy is removed when the confined stream process exits.

The temporary profile always sets `resolution=1080p`. Chiaki's independent
defaults remain in effect for 60 FPS and automatic bitrate selection, so the
normal command needs no quality arguments and the real Chiaki configuration is
still untouched. Video capture records the negotiated stream window directly;
it does not upscale a 720p source after the fact.

The normal workflow never handles Chiaki's client UI. If Remote Play ends—for
example, because the operator takes the physical DualSense—the CLI-owned stream
process may remain behind a `Session has quit` dialog. Clean that exact process
from the terminal with:

```sh
python3 tools/ps5_remoteplay.py stop-stream
```

`stop-stream` resolves the dialog's owning PID, proves that it belongs to the
isolated CLI stream, terminates only that confined process and verifies that
its windows disappear. It never activates the dialog, clicks `OK`, moves the
pointer or depends on focus. `stream` performs the same stale-process cleanup
automatically before reusing the registered console entry. If one healthy
isolated CLI stream is already active, `stream` returns that existing window
instead of launching a duplicate. It fails closed if several stream windows
exist or if the sole window belongs to a process outside the helper's exact
CLI contract. Neither action pairs or re-registers the console.

`acknowledge-quit` remains available only as an explicit compatibility tool for
an operator who deliberately wants the Qt dialog's normal `OK` action. It is
not part of the automated capture or restart path.

`stop-stream` closes only a stream process started through this isolated CLI
path. It first requests a normal window close and verifies the process exit;
Chiaki 2.1.1 can hang after destroying its last X11 window, so the helper sends
signals from the same Snap confinement and escalates to `SIGKILL` only if a
bounded `SIGTERM` also fails. It refuses to signal the ordinary Chiaki client
or any process whose exact executable and `stream` argument do not match.

Capture commands target the active X11 window named `Chiaki | Stream`.
Outputs default to the ignored
`research/gpu/captures/remoteplay/` directory. `record` captures video;
audio capture is intentionally not enabled yet. Explicit `--output` paths are
available when a particular evidence directory is required.

For a community presentation, start the CLI stream, arrange the PS5 screen and
run:

```sh
python3 tools/ps5_remoteplay.py record-demo --name "AGC Gears"
```

The command records the exact Remote Play window until Enter or `Ctrl+C`, then
finalizes an H.264/yuv420p MP4 with fast-start metadata for broad player and web
compatibility. The raw video is named and timestamped under the ignored
`research/gpu/captures/remoteplay/demos/` directory. Use `--seconds N` for an
automatic endpoint or `--output PATH` for an explicit destination. Review each
recording before sharing it; the wrapper captures only the Chiaki stream, but
the visible console UI may still contain account or notification information.
Audio is not captured yet, so narration can be added during editing without
mixing desktop sounds or notifications into the raw recording.

The `stream` command restores focus to the launch-time developer window only
when the new stream still owns focus. If the operator changed focus while the
stream opened, the helper preserves that newer choice instead of assuming the
old window is still intended. This prevents Chiaki's keyboard/controller grab
from capturing the whole interactive development session. Click the stream
only when direct PS5 input is intended; close the stream window to release an
explicit grab without closing the PS5 application.

Remote Play images are supporting visual evidence, not substitutes for the
artifact hash, GPU fence, VideoOut token, guards or structured telemetry.
