# Remote Play observability

The lab uses
[`blackbearreloaded/headless-linkdev`](https://github.com/blackbearreloaded/headless-linkdev)
at commit `b658657190873f1ae194b732f8dcfdb02543c4aa` to pair the owned PS5
with Chiaki through `elfldr`. The payload was built, host-tested and used to
complete a real pairing on FW 12.02 on 2026-09-05. Upstream currently documents
FW 12.70, so this is a lab validation rather than an upstream compatibility
claim.

Remote Play complements `ps5log/1`: telemetry remains the source of truth for
machine-readable renderer state, while the video stream provides direct visual
observation, screenshots and bounded recordings.

## Setup

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
python3 tools/ps5_remoteplay.py status
python3 tools/ps5_remoteplay.py screenshot
python3 tools/ps5_remoteplay.py record --seconds 30
python3 tools/ps5_remoteplay.py focus
```

`status`, `screenshot` and `record` inspect X11 afresh on every invocation.
They require a visible window named exactly `Chiaki | Stream` whose `WM_CLASS`
identifies the real Chiaki client surface. This prevents the identically named
Mutter frame from being selected by search order. Multiple real client surfaces
are treated as ambiguous and the command fails closed.

Capture commands address the selected window directly by ID and never activate
it, so keyboard focus may remain wherever the owner puts it. `focus` is the only
command that explicitly activates an existing stream, and it verifies the
active window immediately afterward.

Outputs default to the ignored
`research/gpu/captures/remoteplay/` directory. `record` captures video;
audio capture is intentionally not enabled yet. Explicit `--output` paths are
available when a particular evidence directory is required.

If a stream already exists, `stream` reports its freshly resolved ID and does
not launch a duplicate. When launching a new stream, it snapshots the active
window immediately before launch. It restores that window only when Chiaki
still owns focus at the decision point. If the owner has focused any other
window in the meantime, the helper leaves that choice untouched.

Do not use raw `xdotool`, `wmctrl` or ImageMagick window searches for routine
automation. Use this helper so every operation gets a fresh, validated target
and follows the conditional focus policy.

## Physical DualSense handoff

The console is already registered in the main Chiaki client. Normal capture
work does not require another Headless LinkDev run, pairing PIN, Account ID or
registration step.

While `Chiaki | Stream` is open, Chiaki owns the Remote Play session and a
focused stream can send keyboard input to the PS5. When the owner takes the
physical DualSense and begins playing directly on the PS5, the Remote Play
stream session/window closes. The main Chiaki client remains open with its
registered console entry; Chiaki itself has not died and the stream can be
started again from that entry without pairing.

For runs that require physical controller movement and visual evidence, capture
the initial view first, let the owner take the DualSense, and keep structured
telemetry running after the stream window closes. Once the run completes,
restart only the stream from the existing entry and capture the final view.
This makes Remote Play capture and physical input sequential rather than
concurrent.

Remote Play images are supporting visual evidence, not substitutes for the
artifact hash, GPU fence, VideoOut token, guards or structured telemetry.
