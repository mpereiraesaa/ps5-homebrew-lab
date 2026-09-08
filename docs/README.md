# Documentation index

This directory documents the shared `homebrew_ps5` laboratory. Public projects
under `projects/` maintain their own self-contained documentation and must not
link to private captures or firmware-derived material.

## Start here

- `CURRENT.md` — canonical implementation and current development policy.
- `STATUS.md` — chronological Stage A–I record; historical where it references
  the retired `PPSA99998` host.
- `ROADMAP.md` — milestone order and remaining hardware gates.
- `PROJECTS.md` — active projects, reusable components and deferred work.
- `PORTING_PLAYBOOK.md` — cross-project rules for porting third-party code
  to native PS5; read it before starting a new port.
- `OPERATIONS.md` — build, validation, deployment and safe cleanup procedures.
- `OBSERVABILITY.md` — contrato TCP `ps5log/1` y evidencia histórica del host
  retirado, con manifiestos y clasificación.
- `REMOTEPLAY.md` — pairing, streaming, screenshots and video capture through
  Headless LinkDev and Chiaki.
- `XASH3D_PS5_PLAN.html` — visual phase plan from the proven AGC renderer to a
  playable native GoldSrc engine.
- `XASH3D_CHECKPOINT.md` — current completed/active boundary, evidence and the
  next isolated hardware gates.
- `../research/xash3d/PS5_SYMBOL_GAP.md` — reproducible PS5-target compile and
  unresolved-symbol sizing for Xash3D, mainui and hlsdk-portable.
- `../research/gpu/LEGACY_FILESYSTEM_TELEMETRY.md` — frontera explícita entre
  evidencia histórica y el flujo de red objetivo.

## Technical record

- `FINDINGS.md` — confirmed results, measured limits and corrected assertions.
- `GPU_RESEARCH.md` — AGC/GFX1013 investigation and evidence progression.
- `RELEASE_STATE.md` — reproducible artifacts and release-readiness boundary.
- `PROJECT_CHARTER.md` — scope, clean-room rules and evidence standards.
- `UPSTREAMING.md` — publication boundaries and patch/fork workflow.

Detailed experimental notes, private evidence and host regression gates live in
`research/gpu/`; they are not the public API. The reusable sanitized interface
is documented in `sdk/agc/README.md` and validated with:

```sh
make agc-sdk-check
```

The public-facing demo has its independent documentation under
`projects/ps5-agc-gears/docs/`. The Win32 compatibility layer documents
itself under `projects/prospero-win/docs/`; its phase boundary is
`PE_MAPPING_PHASE0.md` and its scope limits are in `EXECUTION_MODEL.md`.

The Xash3D Phase 1/2 implementation was merged through public Gears PR #8 as
commit `642d348`; the checked-in Gears submodule pins that exact canonical
boundary.

`STATUS.md`, `ROADMAP.md`, `FINDINGS.md`, `GPU_RESEARCH.md` and
`RELEASE_STATE.md` retain the chronological Stage A–I record. Where their
language says “current” or “next”, interpret it at the dated reconciliation;
`CURRENT.md` supersedes those statements operationally.

- [`PORTING_PLAYBOOK.md`](PORTING_PLAYBOOK.md): cross-project PS5/Prospero porting method, runtime contract and blocker post-mortems. Read before porting anything new under `projects/`.
