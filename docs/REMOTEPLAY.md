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
python3 tools/ps5_remoteplay.py screenshot
python3 tools/ps5_remoteplay.py record --seconds 30
```

Capture commands target the active X11 window named `Chiaki | Stream`.
Outputs default to the ignored
`research/gpu/captures/remoteplay/` directory. `record` captures video;
audio capture is intentionally not enabled yet. Explicit `--output` paths are
available when a particular evidence directory is required.

Remote Play images are supporting visual evidence, not substitutes for the
artifact hash, GPU fence, VideoOut token, guards or structured telemetry.
