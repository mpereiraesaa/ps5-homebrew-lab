# PS5 Homebrew Lab

A reproducible engineering laboratory for native PlayStation 5 homebrew on
firmware 12.02. The repository records reusable platform contracts, host-side
tests and hardware evidence for graphics, input, audio, memory, telemetry and
runtime compatibility work.

This is an independent community project. It is not affiliated with or
endorsed by Sony, Microsoft, Valve or the owners of the referenced games and
engines.

## Projects

### [ps5-xash3d](projects/ps5-xash3d/README.md)

The active native Xash3D/GoldSrc port and canonical AGC renderer. It boots the
engine, loads the original game modules and renders playable Half-Life 1
through native PS5 graphics, input and audio backends. The first playable
release covers live world geometry, lightmaps, special surfaces, 2D, Studio
models, effects, game audio, save/load and an optional HD-content mount.
Release polish and broader gameplay coverage remain.

The laboratory pins the public repository as a submodule. Its own README and
roadmap are authoritative for current port status.

### [ps5-agc-gears](projects/ps5-agc-gears/README.md)

The frozen standalone GPU demonstration: three lit, depth-tested gears,
double buffering, two frames in flight and a validated 60,000-frame hardware
soak. It is the small reference project for confirming native PS5 GPU output.

### [prospero-win](projects/prospero-win/README.md)

An experimental Windows compatibility runtime for PS5. It maps PE images,
translates 32-bit x86 into x86-64, supplies reviewed Win32/CRT services and
connects guest presentation, audio and input to native PS5 backends.

It has reached its first playable title: the owner's original Windows XP Space
Cadet Pinball executable runs without recompilation and has passed physical
gameplay checks for launch, both flippers, scoring, ball loss, pause/resume and
new-game restart. Pinball is the first compatibility target, not the scope of
the runtime; pacing and presentation polish remain. No Windows executable or
game asset is included.

### [logging_server](projects/logging_server/README.md)

The `ps5log/1` telemetry service used for structured, correlated runtime
evidence. Filesystem and USB logs are deprecated for active development.

## Repository layout

- `projects/` — active or independently publishable applications and tooling.
- `docs/CURRENT.md` — canonical laboratory boundary and current project pins.
- `docs/PROJECTS.md` — concise project-level status and deferred work.
- `docs/PORTING_PLAYBOOK.md` — reusable native-porting practices.
- `tools/ps5_remoteplay.py` — isolated Chiaki streaming, screenshots and video.
- `sdk/agc/` — sanitized AGC interface notes retained by the laboratory.
- `legacy/` — historical probes and retired staged applications.
- `research/` — reproducible analysis; private captures and dumps are ignored.

## Build and test

Clone with submodules, then run the complete host gate:

```sh
git clone --recurse-submodules git@github.com:mpereiraesaa/ps5-homebrew-lab.git
cd ps5-homebrew-lab
make check
```

The gate tests the canonical renderer, Gears, `prospero-win`, telemetry and
Remote Play contracts and runs publication audits. Console deployment needs
an owned PS5 with a compatible homebrew environment; host tests do not.

Project-specific build and hardware-validation instructions live in each
project README. Generated artifacts, vendor SDK material, game data, firmware
content, memory dumps, decompiler output, credentials and private captures must
never be committed.

## Contributing

Issues and focused pull requests are welcome. Start with the target project's
README and tests, keep changes reusable rather than title-name-specific, and
include a regression for behavioral fixes. Hardware claims need an exact
artifact identity plus structured `ps5log/1` evidence; screenshots alone prove
only visual output.

All changes enter through topic branches and pull requests. Direct pushes to
`main` are intentionally disallowed, and CI must pass before merge. Please
keep PRs small enough to review without proprietary context.

See [the documentation index](docs/README.md),
[current status](docs/CURRENT.md), [operations](docs/OPERATIONS.md) and
[publication boundaries](docs/UPSTREAMING.md) for details.

Individual projects carry their own licenses and notices. Check the relevant
project before redistributing or combining code.
