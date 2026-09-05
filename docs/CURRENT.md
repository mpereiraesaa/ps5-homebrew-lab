# Current development boundary

Last reconciled: 2026-09-05. Tested console firmware: PS5 12.02.

## Canonical implementation

`projects/ps5-agc-gears` is the only active AGC renderer. It is standalone,
public, source-reproducible and hardware-validated. Its continuous production
runtime draws the classic three-gear scene with independently authored
`gfx1013` shaders, depth testing, double buffering, two frames in flight and
exact GPU/VideoOut ownership.

The strict reference soak completed 60,000/60,000 frames with zero renderer
errors and intact guards. Exact evidence and its limitations are documented in
`projects/ps5-agc-gears/docs/HARDWARE_VALIDATION.md`.

## Development policy

- `main` is protected and receives changes only through pull requests.
- Each experiment uses a sibling worktree and an `exp/<topic>` or
  `feature/<topic>` branch.
- Shared behavior is added to tested project interfaces, never copied into a
  numbered stage.
- `make check` is the root host gate.
- Native changes require a fresh artifact hash and matching TCP telemetry;
  synchronization, memory or command changes additionally require a soak.
- Visual checks, screenshots and bounded video recordings use the canonical
  `tools/ps5_remoteplay.py` workflow. Remote Play complements telemetry and
  never replaces its ownership/completion evidence.

## Canonical tooling

- `projects/logging_server`: structured `ps5log/1` telemetry.
- `tools/ps5_remoteplay.py`: pinned Headless LinkDev build/pairing plus
  Chiaki stream, screenshot and MP4 capture.
- `tools/night_supervisor.py`: exact launch/close and guarded operational
  workflows.

Remote Play pairing and capture were validated on FW 12.02. Details and
credential-handling rules are in `docs/REMOTEPLAY.md`.

## Historical boundary

The former Phase 0 and Stages A–I proved the path from direct memory and simple
DCBs through triangle, cube and early Gears rendering. Their source now lives
under `legacy/`; detailed notes and private evidence remain under
`research/gpu/`. They are useful provenance, not current instructions.

Commercial-game dumps, Ghidra databases, runtime captures and proprietary
material remain local research inputs and are never copied into a public repo.
