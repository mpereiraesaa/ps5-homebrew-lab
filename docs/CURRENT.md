# Current development boundary

Last reconciled: 2026-09-06. Tested console firmware: PS5 12.02.

## Canonical implementation

`projects/ps5-xash3d` (`mpereiraesaa/ps5-xash3d`, private until the owner
publishes it) is the only active AGC renderer and the home of the Xash3D port.
It was forked from `ps5-agc-gears` at `cbff264` with full history on
2026-09-06, so it carries the Gears renderer foundation plus the Phase 1-3 BSP
viewer, resource foundation and texture path. Its `make all` is the root host
gate through `make xash3d-check`.

`projects/ps5-agc-gears` is frozen as the standalone public Gears demo:
three lit gears, two frames in flight, exact GPU/VideoOut ownership and the
60,000-frame reference soak documented in
`projects/ps5-agc-gears/docs/HARDWARE_VALIDATION.md`. Only demo fixes land
there. `mpereiraesaa/ps5-agc-gears#10` reverts the Phase 2/3 merges (#8, #9)
from that repository and tags the demo as `gears-demo-freeze`; the laboratory
moves its Gears pin once it merges.

## Xash3D checkpoint

The active engineering target is now Xash3D on PS5. Phases 0, 1 and 2 of
`XASH3D_PS5_PLAN.html` are complete on the canonical public branch, and Phase 3
completed all six hardware gates before merging through
`mpereiraesaa/ps5-agc-gears#9` as commit `cbff264`. The
consolidated resource-foundation implementation was merged through
`mpereiraesaa/ps5-agc-gears#8` as commit `642d348`. Both commits are now
history of `projects/ps5-xash3d`, which this laboratory pins at its first own
commit `8865b3f` on top of `cbff264`.

Phase 1 renders the private `c1a0` BSP with base textures and lightmaps, proves
physical DualSense noclip movement and passes a 60,000-frame textured gate.
Phase 2 replaces fixed resource placement with a fence-retired direct-memory
pool, two-slot transient ring, named GFX10.3 V#/T#/S# builders, per-frame
constant buffers, generated pipeline permutations and a tested cache contract.
Its 60,000-frame FW 12.02 run completed with zero errors, exact fence/VideoOut
retirement, both transient slots reusable and all four persistent allocations
reclaimed. The operator confirmed the transient overlay pulse live.

Phase 3 adds a bounded dynamic-lightmap path, deterministic mip chains,
trilinear/anisotropic sampling, separate opaque/alpha-test/sky passes and exact
resident/upload accounting. Its final FW 12.02 run completed 60,000 frames with
zero errors, exact fence/VideoOut ownership, intact guards and a gap-free BYE.
The `ps5-xash3d` submodule pins that complete Phase 3 tree. The next
implementation phase is Phase 4, GoldSrc render states, and it lands in
`ps5-xash3d`. See
`XASH3D_CHECKPOINT.md` for the evidence boundary and executable order.

The engine symbol probe is also complete. The client has only three genuine
SDK gaps (`__assert`, `getpwuid`, `dladdr`), and `mainui` plus both hlsdk
modules have no missing C++ runtime provider. Raw lists and reproduction scripts
live under `research/xash3d/`.

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

The already registered Chiaki entry must be reused; pairing is not part of
normal capture. The helper launches it directly from the terminal without the
discovery client window. After a Remote Play disconnect, `stop-stream` cleans
the exact CLI-owned process by PID and `stream` does the same automatically
before restart. The normal workflow does not focus, acknowledge or click the
`Session has quit` dialog. Automation must not infer focus or synthesize input.

## Application-owned modules

Runtime loading of application-owned PRX modules is validated on FW 12.02
(see `FINDINGS.md`, "Módulos PRX propios"). The tooling lives in the
native-foundation fork, branch `exp/prx-module`: `ps5-native-tool link
--module`, `tools/build-module.sh` and `modules/prx_loader.h`. The hardware
gate lives in the Gears repository branch `exp/prx-gate`. Load-time
`DT_NEEDED` binding and `sceKernelDlsym` are not available for these modules;
symbol resolution goes through the module's export descriptor.

## Historical boundary

The former Phase 0 and Stages A–I proved the path from direct memory and simple
DCBs through triangle, cube and early Gears rendering. Their source now lives
under `legacy/`; detailed notes and private evidence remain under
`research/gpu/`. They are useful provenance, not current instructions.

Commercial-game dumps, Ghidra databases, runtime captures and proprietary
material remain local research inputs and are never copied into a public repo.
