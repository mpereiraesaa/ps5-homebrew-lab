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

Taking control with the physical DualSense ends the Remote Play session but
does not close the Chiaki client. The stream window remains behind a
`Session has quit` dialog until its selected `OK` action is acknowledged; only
then do the dialog and ended stream window close. Handle that transition with:

```sh
python3 tools/ps5_remoteplay.py acknowledge-quit
```

The command targets the exact Chiaki client dialog (not Mutter's decoration),
activates it only long enough to send the normal selected `OK` action, and
verifies that both the dialog and ended stream disappear. It restores the
previous workspace only while Chiaki still owns focus; a newer non-Chiaki
operator focus is preserved. Qt versions that reject the synthetic `Return`
receive a fallback click derived from the dialog's own client geometry; the
pointer is restored afterwards. The command is idempotent.
`stream` performs the same acknowledgement automatically before reusing the
already registered console entry. Neither action pairs or re-registers the
console.

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

The `stream` command restores focus to the launch-time developer window only
when the new stream still owns focus. If the operator changed focus while the
stream opened, the helper preserves that newer choice instead of assuming the
old window is still intended. This prevents Chiaki's keyboard/controller grab
from capturing the whole interactive development session. Click the stream
only when direct PS5 input is intended; close the stream window to release an
explicit grab without closing the PS5 application.

Remote Play images are supporting visual evidence, not substitutes for the
artifact hash, GPU fence, VideoOut token, guards or structured telemetry.
