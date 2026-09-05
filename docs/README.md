# Documentation index

This directory documents the shared `homebrew_ps5` laboratory. Public projects
under `projects/` maintain their own self-contained documentation and must not
link to private captures or firmware-derived material.

## Start here

- `CURRENT.md` — canonical implementation and current development policy.
- `STATUS.md` — confirmed current state and active technical boundary.
- `ROADMAP.md` — milestone order and remaining hardware gates.
- `PROJECTS.md` — active projects, reusable components and deferred work.
- `OPERATIONS.md` — build, validation, deployment and safe cleanup procedures.
- `OBSERVABILITY.md` — contrato TCP `ps5log/1`, estado del bloqueo nativo,
  manifiestos y clasificación.
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
`projects/ps5-agc-gears/docs/`.

`STATUS.md`, `ROADMAP.md`, `FINDINGS.md`, `GPU_RESEARCH.md` and
`RELEASE_STATE.md` retain the chronological Stage A–I record. Where their
language says “current” or “next”, interpret it at the dated reconciliation;
`CURRENT.md` supersedes those statements operationally.
