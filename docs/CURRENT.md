# Current development boundary

Last reconciled: 2026-09-07. Tested console firmware: PS5 12.02.

## Canonical implementation

`projects/ps5-xash3d` (`mpereiraesaa/ps5-xash3d`, public) is the only active
AGC renderer and the home of the Xash3D port.
It was forked from `ps5-agc-gears` at `cbff264` with full history on
2026-09-06, so it carries the Gears renderer foundation plus the Phase 1-3 BSP
viewer, resource foundation and texture path. Its `make all` is the root host
gate through `make xash3d-check`.

`projects/ps5-agc-gears` is frozen as the standalone public Gears demo:
three lit gears, two frames in flight, exact GPU/VideoOut ownership and the
60,000-frame reference soak documented in
`projects/ps5-agc-gears/docs/HARDWARE_VALIDATION.md`. Only demo fixes land
there. Merged PR `mpereiraesaa/ps5-agc-gears#10` reverted the Phase 2/3 merges
(#8, #9), tagged the demo as `gears-demo-freeze`, and the laboratory now pins
the frozen tree at `8f035b7`.

## Xash3D checkpoint

The active engineering target is now Xash3D on PS5. Phases 0, 1 and 2 of
`XASH3D_PS5_PLAN.html` are complete on the canonical public branch, and Phase 3
completed all six hardware gates before merging through
`mpereiraesaa/ps5-agc-gears#9` as commit `cbff264`. The
consolidated resource-foundation implementation was merged through
`mpereiraesaa/ps5-agc-gears#8` as commit `642d348`. Both commits are now
history of `projects/ps5-xash3d`, which this laboratory now pins at merged
Phase 4 commit `38c6a38` (the dedicated identity began at `c09318f`).

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
The `ps5-xash3d` submodule now carries Phase 4's complete 99-state native
catalog, real BSP binding, viewport/scissor restoration and the hardware-proven
blend/depth/cull/fog/lightmap matrix. Its orthographic blended 2D path and real
BSP lighting path are hardware-proven too: HUD/console/menu/font geometry
streams through the fence-retired ring, while original lightstyle planes and a
face-local dynamic light update a bounded lightmap-atlas patch through the
Phase 3 uploader. Camera-facing sprites and alpha/additive particles stream
through that same per-slot ring. Animated Studio models use CPU skinning,
per-model textures, chrome and additive modes; real brush entities retain
independent transforms and source render modes; and world-tree PVS plus
draw-AABB frustum culling reduces submitted world work. Every ordered gate
passed independently. The complete water/glass/effects/Studio/HUD composition
then passed a 60,000-frame FW 12.02 soak with two retired slots, exact
ownership, intact guards, a gap-free BYE and zero errors. Phase 4 is complete.
Phase 5's engine-bootstrap, filesystem and ScePad checkpoints passed on 2026-09-07.
The Xash3D FWGS engine boots on FW 12.02, spawns `c1a0` with every entity class
and quits cleanly. The accepted full-tree run deployed 4,741 files
(555,437,162 bytes), served a 4,823-entry index, read the 12,565-byte
`delta.lst` twice and completed a bounded 90-second run. The earlier
`gfx/palette.lmp` fault was not an fd or filesystem failure: its measured
length/read/close lifecycle was correct (768/768/0). The SDK had routed
`strcasestr` through `libScePosixForWebKit`; `HAVE_STRCASESTR=0` now selects
portable `Q_stristr`, and the linked ELF has no dynamic `strcasestr`. The
native ScePad backend then processed 24,535 connected records in chronological
batches of up to 62, proved movement/look and both edges of jump, crouch, use
and fire, reported zero read errors and closed Pad/UserService exactly in run
`20260907T181827569Z_PPSA99996_xash3d-engine_0xbec4d1cc932e`.

The remaining Phase 5 gates are, in order: SceAudioOut with a ring buffer and
underrun accounting; the engine allocator and every GPU resource on direct
memory; pthreads,
monotonic time and measured sleep; GPU timestamps plus VideoOut flip latency;
and project-owned shims for `__assert`, identity without `getpwuid`, and
logging without `dladdr`. Every gate requires host tests, an incremental FW
12.02 run, structured telemetry, exact ownership/teardown, zero errors and
visual/audio/input evidence where applicable. Client/menu integration,
`ref_null`/`ref_soft`, `ref_agc` and application-owned PRX conversion remain
Phase 6 work.

The package-identity prerequisite is also closed. Xash3D is installed and
hardware-smoke-tested as `PPSA99996`, while the frozen Gears demo remains
available as `PPSA99997`. `night_supervisor.py` has distinct exact-title
launch/close helpers for both. The obsolete historical host `PPSA99998` is not
installed: its homebrew, mount, application and metadata paths are absent and
the live application database contains no matching row.

The engine symbol probe is also complete, but an exported provider is not
treated as a hardware pass. The current dynamic-import ledger contains 173
symbols: 27 hardware-pass, 3 hardware-fail/guarded (`dup`, `dup2`, `execv`)
and 143 exported-only. The four enabled string helpers (`strcasecmp`,
`strnlen`, `strlcpy`, `strlcat`) passed a focused FW 12.02 smoke run. The
remaining project-owned gaps are `__assert`, `getpwuid` and `dladdr`. Raw
lists, the evidence ledger and reproduction scripts live under
`research/xash3d/` and the pinned `ps5-xash3d` submodule.

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
