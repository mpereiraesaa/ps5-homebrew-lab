# Legacy laboratory archive

This directory preserves the experiments that established the PS5 native and
AGC contracts before the standalone demo existed.

- `apps/` contains the old Phase 0 and numbered-stage native applications.
- `probes/` contains capability and clean-room contract probes.

Nothing here is an input to `projects/ps5-agc-gears`, and no new feature should
be implemented by copying or extending a numbered stage. Historical builds are
opt-in through `make legacy-probes`; the root `make check` deliberately ignores
them. Private runtime evidence remains under `research/gpu/`.

Future experiments start from the public repository in an `exp/<topic>` Git
worktree and reuse its tested `src/`, `include/` and `native/` interfaces.
