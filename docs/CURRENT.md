# Current development boundary

Last reconciled: 2026-09-09. Tested console firmware: PS5 12.02.

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

Current port pin: `2caa49e`, merged [PR #30](https://github.com/mpereiraesaa/ps5-xash3d/pull/30).

Current plan revision 48: explicit round-trip validation passes the accepted
10,810-frame multi-map run. Controlled Host_Error recovery is operator/hardware
accepted: 10,825 frames, one expected diagnostic error, zero renderer errors,
nine reclaims and exact teardown. Normal no-grant graphics build restored at
18:58 UTC without relaunch; audio remains off and the timed harness is not a
release package. Next are remaining Studio/effects parity, audio and release
work, including longer transition soaks. See
`XASH3D_CHECKPOINT.md` for current integration identity and proof boundaries.
Older checkpoint descriptions below are historical.

The active engineering target is now Xash3D on PS5. Phases 0, 1 and 2 of
`XASH3D_PS5_PLAN.html` are complete on the canonical public branch, and Phase 3
completed all six hardware gates before merging through
`mpereiraesaa/ps5-agc-gears#9` as commit `cbff264`. The
consolidated resource-foundation implementation was merged through
`mpereiraesaa/ps5-agc-gears#8` as commit `642d348`. Both commits are now
history of `projects/ps5-xash3d`. This laboratory now pins the merged Phase 7
native-menu checkpoint `a975b86`; its preceding live-2D checkpoint is
`0bdcbfb`, and the preceding live-special-surface checkpoint is
`77c742a`, the preceding live-lightmap checkpoint is `4f9d38d`, the preceding
compositor-visible world checkpoint is `cdcce91`, the preceding live-world
submission checkpoint is `bd4b250`, and
the Phase 6 final `ref_agc` checkpoint is `258fbe3`, the
preceding client-PRX checkpoint is `3a30250`, the dedicated title icon entered
at `ea9be4b`, and the dedicated identity began at `c09318f`.

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
Phase 5's engine-bootstrap, filesystem, ScePad, SceAudioOut, direct-memory,
thread/time, GPU/flip timing and project-owned libc-shim checkpoints passed on
2026-09-07 UTC (2026-09-08 local).
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

SceAudioOut then closed as well. A client-independent C core owns a
producer/consumer PCM ring, a continuous 147/160 resampler and a dedicated
worker that alone holds the handle and calls `Output`, the NULL drain and
`Close`, never holding the mutex across the blocking call; `s_ps5.c` binds it to
Xash3D's own DMA ring. The engine keeps mixing at `SOUND_DMA_SPEED` because
`s_main.c`, `s_stream.c` and `s_load.c` read that macro directly, so the
conversion to the port's 48 kHz lives in the PS5 layer instead of in the
submodule. Accepted run `20260907T194413175Z_PPSA99996_xash3d-engine_0xc372db81ccc6` opened the main port for the system user `0xff`
and carried 66,150 source frames as 72,192 in 282 whole 256-frame blocks
(71,999 resampled plus 193 terminal padding), with the consumed PCM hash equal
to the independently generated pattern hash, zero underruns, zero `Output`
errors and exactly one drain/close/join. The operator confirmed the low tone,
the gap and the higher tone by ear, and a repeat run reproduced every counter
bit for bit. Two facts measured here that the FW 6.02 reference does not
document: `sceAudioOutOutput` returns the number of frames it accepted (256 at
this grain), including the NULL drain, so success is non-negative rather than
zero; and the system user `0xff` is accepted for the main port.

The direct-memory gate is closed in merged Xash3D PR #7 (`cb7c2b3`). One
128 MiB fixed-VA root now owns every C/C++ engine allocation. The representative
GPU contract allocated command, buffer, texture and depth resources with four
unique generations and balanced all four retire/reclaim pairs. Accepted run
`20260907T212512180Z_PPSA99996_xash3d-engine_0xc8f58f777975` loaded `c1a0`,
reached a 35,632,245-byte peak across 20,687 allocations and 1,091
reallocations, then reclaimed eight explicitly classified process-lifetime
objects and ended with zero live bytes. Guards, allocation failures, stale
tokens and foreign-owner errors all remained zero; reserve/allocate/map and
unmap/release each occurred exactly once with success.

The thread/time gate is closed in merged Xash3D PR #8 (`ff0fd62`). Accepted
run `20260907T220548886Z_PPSA99996_xash3d-engine_0xcb2ce47a2f65` created two
distinct workers with exact create/join/detach `2/1/1`, completed 32,768
mutex-protected increments, observed 8,191 advances across 8,192 monotonic
reads with no regression, and passed 128 `nanosleep`/`usleep` measurements at
1/2/5/10 ms with zero errors or early wakes. It then loaded `c1a0`, retained
the exact direct-memory teardown and closed with a gap-free BYE.

The GPU/flip timing gate is closed in merged Xash3D PR #9 (`cd57ab8`). Run
`20260907T225446311Z_PPSA99996_ps5-xash3d_0xcdd8ce3a668a` correlated 60,000
CPU submits, raw GPU end-of-pipe writes, ownership-fence observations and
exact VideoOut events with 59,999 strict GPU-clock changes and no regression,
CPU-order error, sequence gap or renderer error. The average submit-to-flip
residence was 32,754,596 ns for the two-frame pipeline; the independently
named observed fence-to-flip average was 15,930,800 ns. The accepted ELF and
fSELF hashes reproduced exactly after the run.

The final Phase 5 gate is closed in merged Xash3D PR #10 (`a2cb856`). Run
`20260907T235551519Z_PPSA99996_xash3d-engine_0xd12e2a9238fb` retained
project-owned `__assert`, `getpwuid` and `dladdr` definitions while importing
none of them dynamically. Its assert formatter/reporter policy, stable `ps5`
identity and zeroed `dladdr`/`argv[0]` fallback all passed before the complete
`c1a0` workload; 30 records ended without gaps or errors in a clean BYE. The
ELF/fSELF hashes reproduced exactly. Phase 5 is complete.

Phase 6 gate 1 is closed in merged Xash3D PR #11 (`af99dcd`). Run
`20260908T054317837Z_PPSA99996_xash3d-engine_0xe423c3826406` exercised the
real Xash `COM_*` API against an application-owned PRX: four mapped segments,
six validated `PRXDESC1` exports, expected missing-symbol behavior, code/data
calls, a kernel import and reverse function naming, followed by exact unload
and zero active handles. FW 12.02 cleared the module-info size word and did not
automatically mutate the probe through its ELF entry, so the loader accepts
the measured zero/`0x160` shape and modules expose explicit idempotent startup.
The same run spawned `c1a0` and closed cleanly; a no-probe production
regression passed afterward.

Phase 6 gate 2 is closed in merged Xash3D PR #12 (`0d1f0e0`). Accepted run
`20260908T071044664Z_PPSA99996_xash3d-engine_0xe8e95e4c0974` loaded
`filesystem_stdio.prx` with four mapped segments and eight validated exports,
explicitly initialized its 4,823-entry index, listed 22 `gfx/*` resources,
resolved mixed-case `GfX/PaLeTtE.LmP` at 768 bytes and read the 2,546,336-byte
`maps/c1a0.bsp`. The static server then spawned `c1a0`; after 15 seconds the
filesystem state remained valid, `module_stop` and unload both returned zero,
no dynamic handles remained and the engine arena closed exactly. The accepted
allocator contract keeps `LoadFileMalloc` on process libc because its buffer
crosses into host `COM_FreeFile`; a rejected private-arena diagnostic made
that boundary observable through `SIGABRT`.

Phase 6 gate 3 is closed in merged Xash3D PR #13 (`cbc5948`). Accepted run
`20260908T082646982Z_PPSA99996_xash3d-engine_0xed0f9a243abc` loaded both
`filesystem_stdio.prx` and `server.prx`. The server descriptor exposed 257
entries, including 251 engine exports; its ABI table mask was 7 and two
non-mutating PRX-to-engine callback smokes passed before the unmodified HLSDK
registration and map flow spawned `c1a0`, loaded the graph and started the
four-player server. An earlier deterministic fault at the first real cvar
registration established that application-owned PRXs cannot assume C++
constructors have run on FW 12.02: the generated lifecycle now executes the
relocated `.init_array` forward and `.fini_array` reverse. After the bounded
15-second run, server stop/unload returned zero while the filesystem remained
active; filesystem stop/unload then returned zero with no modules active and
the engine arena balanced.

Phase 6 gate 4 is closed in merged Xash3D PR #14 (`9f783ec`). Accepted run
`20260908T094038112Z_PPSA99996_xash3d-engine_0xf1174a815840` loaded MainUI as
`menu.prx` on top of the filesystem/server checkpoint. Its 16 base and 12
extended callbacks passed with complete engine masks, explicit C++ lifecycle,
one activation and 5,127 redraws. The software framebuffer presented 5,100
non-black frames; this proves UI execution but not yet AGC presentation on the
TV. Server, menu and filesystem unloaded in order with active counts 2, 1 and
0, zero structured errors and a clean BYE.

Phase 6 gate 5 is closed in merged Xash3D PR #17 (`3a30250`). Accepted run
`20260908T130114060Z_PPSA99996_xash3d-engine_0xfc0996a1effb` loaded the pinned
HLSDK client as `/app0/sce_module/client.prx` on top of the accepted
filesystem/server/menu bundle. Its 48-entry descriptor exposed 42 actual
GoldSrc exports, interface version 7 and both callback masks (63 host, 15
module) passed, and both PRX-to-engine smokes completed. The real `c1a0`
workload performed one video init, 4,916 client frame callbacks, 4,907
successful HUD redraws and 4,800 non-black software presentations. Server,
menu, client and filesystem stopped/unloaded with active counts 3, 2, 1 and 0;
89 structured records and 115 raw lines ended with result zero, no errors,
gaps or oversized records, and a clean BYE. The five-file bundle is now the
rollback point beneath the final renderer conversion.

Phase 6 gate 6 is closed in merged Xash3D PR #18 (`258fbe3`). Correlated runs
`20260908T191327933Z_PPSA99996_xash3d-engine_0x11059870e2628` and
`20260908T191327984Z_PPSA99996_ps5-xash3d_0x110598a25cd2f` began 51 ms apart.
The engine loaded the complete filesystem/server/menu/client/renderer PRX
stack, started `c1a0`, bound RefAPI 18 with engine mask 63 and observed
203,420 balanced begin/end callbacks, 203,411 scene callbacks and one new-map
callback. The native Phase 4 backend presented 600 combined frames with GPU
hashes `a9e62c5188ca6bf5` and `0044418de19349d8`, 807,578 bright pixels,
exact fence/VideoOut tokens, intact guards and zero errors. Native teardown
closed VideoOut, direct memory and AGC; server, menu, client, renderer and
filesystem then unloaded with active counts 4, 3, 2, 1 and 0. Both streams
ended with clean gap-free BYE, and the deterministic rebuild reproduced the
accepted host, renderer and asset hashes. Phase 6 is complete. Phase 7 owns
live engine-entity-to-AGC translation, gameplay, transitions and release.

Phase 7 live-world presentation is active through merged Xash3D PR #20
(`cdcce91`). Exact
no-handoff and post-bundle-handoff captures were both black; moving the bounded
10 ms scheduler handoff after live-camera fallback initialization produced the
textured `c1a0` tram interior. Final correlated runs
`20260909T005027224Z_PPSA99996_xash3d-engine_0x122bd226f4e00` and
`20260909T005027279Z_PPSA99996_ps5-xash3d_0x122bd25b72b53` began 55 ms apart
and matched 1,076 frame serials. They staged 17,245 vertices, 29,565 indices
and 3,695 surface draws, resolved all 164 world texture references, reclaimed
eight parent resources and unloaded the five PRXs exactly with zero renderer
errors. A synchronized 1920x1080 CLI Remote Play capture was taken only after
`PPSA99996` was verified active; its SHA-256 is
`1ee3578b517bee368f72805d3a9ecd339a5f7de65de462bbefd7a6d7a19c1850`.
This closes compositor presentation and base-texture sampling, not the
unobserved firmware-internal cause of the timing boundary.

Merged Xash3D PR #21 (`4f9d38d`) closes the next checkpoint. The engine
combines active lightstyle planes into one owned padded 1024x256 RGBA8 atlas;
the native backend uploads it through the existing direct-memory world arena
and binds the already hardware-proven opaque/alpha-test lightmap pipelines,
without an OpenGL emulation layer. Correlated runs
`20260909T022301539Z_PPSA99996_xash3d-engine_0x127ca54ee550a` and
`20260909T022301592Z_PPSA99996_ps5-xash3d_0x127ca581d165f` began 53 ms apart
and passed 1,075 matched frames, 3,695 lightmapped draws, 186,051 nonzero atlas
texels, nonzero common frame hash `a3219a480a7a1c41`, eight exact reclaims,
zero renderer errors and ordered five-PRX teardown. The launch-verified CLI
Remote Play capture has SHA-256
`2b8bd9ea8dd5345463f7bd9363ee79df36ae77af76cc635c54b8859699cdbfd7`.
At that checkpoint sky/turbulent semantics, entities, viewmodel and 2D/UI
remained open.

Merged Xash3D PR #22 (`77c742a`) closes native live special surfaces. The
producer separates 158 sky draws/1,197 indices and 35 turbulent draws/312
indices from the ordinary world passes, publishes the six engine sky handles,
camera and engine time, and retains raw GoldSrc turbulent coordinates. The
consumer builds six camera-centred cube draws and uses a dedicated classic
time-driven warp pipeline; no OpenGL emulation layer was introduced. Runtime
directory streams and renderer CPU stores now use engine-owned pools, removing
the PRX-local libc heap ceiling that had prevented `gfx/env/xen9*.tga` from
loading.

Correlated FW 12.02 runs
`20260909T044902002Z_PPSA99996_xash3d-engine_0x12fc201d8f826` and
`20260909T044902056Z_PPSA99996_ps5-xash3d_0x12fc2056055d0` began 54 ms apart
and passed 1,616 frames. The renderer retained 14 special-surface samples with
animation time advancing from 0 to 26,942 ms, stable nonzero sky geometry and
texture hashes, 478 GPU texture creates, 3,440 world draws, eight exact
reclaims and zero errors. Engine memory returned to zero and all five PRXs
unloaded in order. At that checkpoint entities, viewmodel and 2D/UI remained
the open translation boundary; the following live-2D gate closes the 2D part.

Merged Xash3D PR #23 (`0bdcbfb`) closes native live 2D composition. The
renderer consumes `R_Set2DMode`, `R_DrawStretchPic` and `FillRGBA` in producer
order after world and special-surface passes, carries `Color4f`/`Color4ub`,
resolves live texture handles and emits orthographic geometry through the
hardware-proven `screen_2d` pipeline. Consecutive commands batch only when
texture and blend identity match; `FillRGBA` uses a transient white texel.
There is no OpenGL emulation layer. A full-capacity host test proves that all
4,096 producer slots, including 4,095 alternating drawable commands/batches,
fit either 1 MiB transient slot.

Correlated FW 12.02 runs
`20260909T060525224Z_PPSA99996_xash3d-engine_0x133ed1bbb4d07` and
`20260909T060525280Z_PPSA99996_ps5-xash3d_0x133ed1efb02b5` began 56 ms apart
and passed 1,044 frames. Across 333 draw-bearing frames, 61,316 quads became
367,896 indices and 610 ordered batches, with peak three batches, 63,395 input
commands, 2,079 mode commands, zero unresolved textures and command hash
`177a07fa2fd9e5b1`. Both framebuffer slots hashed
`49b1297de5cef0a0`; eight resources retired, guards remained intact, all five
PRXs unloaded in order and both streams ended clean and gap-free. The accepted
20-second CLI capture visibly shows the translucent Xash console, text and
localized overlay over the live tram interior; its SHA-256 is
`5bcdd2772f5d3d29baae61a659ca19af9c079061f69b79f58dc479e70dce6aa0`.
This closes live console/HUD/font/fill translation. The following native-menu
gate closes MainUI presentation; entities and viewmodel remain the immediate
translation boundary.

Merged Xash3D PR #24 (`a975b86`) boots the complete five-PRX stack into MainUI
without a boot-time `+map`, presents it through the live native AGC 2D path,
then queues `map c1a0` through the engine command buffer after five seconds.
The renderer records the first menu frame and the first positive map serial,
while the engine records a unique raw transition before the unique
`Spawn Server: c1a0` line. The transactional deploy helper now disables
ftpsrv's connection-local SELF conversion and requires exact remote size plus
SHA-256 for every staged SELF, PRX and asset; size-only and transformed-ELF
fallbacks are gone.

Correlated FW 12.02 runs
`20260909T065237749Z_PPSA99996_xash3d-engine_0x1368098fcc1b8` and
`20260909T065237800Z_PPSA99996_ps5-xash3d_0x136809c13ba99` began 52 ms apart
and passed 1,339 frames. MainUI began at serial 1; 223 pre-map frames carried
94,918 quads and 27,929 native draws before map serial 1 appeared at renderer
serial 224. Both framebuffer slots hashed `49b1297de5cef0a0`, all eight
resources retired and all five PRXs unloaded exactly with zero errors. A fresh
decoded Home preflight preceded the accepted 35-second CLI recording, which
visibly shows MainUI at 23 seconds and `c1a0` at 25 seconds. This closes native
menu presentation and its in-process map transition. Entities, viewmodel,
fixed-camera comparison, gameplay, performance, soaks and release remain.

The package-identity prerequisite is also closed. Xash3D is installed and
hardware-smoke-tested as `PPSA99996`, while the frozen Gears demo remains
available as `PPSA99997`. `night_supervisor.py` has distinct exact-title
launch/close helpers for both. The obsolete historical host `PPSA99998` is not
installed: its homebrew, mount, application and metadata paths are absent and
the live application database contains no matching row.

The engine symbol probe is also complete, but an exported provider is not
treated as a hardware pass. The thread/time gate's ELF declares 171 dynamic
imports with none banned, and its artifact-specific ledger holds 35
hardware-pass entries, 3 hardware-fail/guarded (`dup`, `dup2`, `execv`) and
133 exported-only entries; the global banned set is `strcasestr` plus the six
outside this gate (AudioOut2, Audio3d, NGS2, AJM, AudioIn, Audiodec),
which the link now rejects. The four enabled string helpers (`strcasecmp`,
`strnlen`, `strlcpy`, `strlcat`) passed a focused FW 12.02 smoke run. The
former project-owned gaps `__assert`, `getpwuid` and `dladdr` are now closed by
local definitions plus the accepted hardware probe. Raw lists, the evidence
ledger and reproduction scripts live under
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
  `tools/ps5_remoteplay.py` workflow. Hardware capture requires a decoded,
  non-black `screenshot --require-decoded` preflight; process/window presence
  alone is insufficient. Remote Play complements telemetry and never replaces
  its ownership/completion evidence.

## Canonical tooling

- `projects/logging_server`: structured `ps5log/1` telemetry.
- `tools/ps5_ftp.py`: the single FTP transport contract. Deploy helpers switch
  `ps5-payload-dev/ftpsrv` to raw SELF mode on their own connection and verify
  the stored fSELF/PRX by exact size and SHA-256; an ELF prefix is not proof.
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

Runtime loading of application-owned PRX modules is now validated both by the
original spike and inside Xash's real `COM_*` path on FW 12.02 (see
`FINDINGS.md`, "Módulos PRX propios", and Xash3D PR #11). The public builder
pins the native-foundation fork's `exp/prx-module` tooling and uses
`ps5-native-tool link --module`. Load-time `DT_NEEDED` binding and
`sceKernelDlsym` are not available for these modules; symbol resolution goes
through each module's range-checked `PRXDESC1` export descriptor.

## Phase 7 live NPC checkpoint — 2026-09-09

Pinned Xash3D `3167fc6` (merged PR #25); plan revision 42.

Final resource validation passed 10,997 frames / 180 active-map seconds, nine
exact reclaims, zero errors and five-PRX teardown. The engine root is empty;
post-run status confirms no BigApp. Full run IDs and hashes are in the port's
`docs/PHASE7_BASELINE_REGRESSION.md` and the lab checkpoint below.

Brush transforms and first live Studio NPCs now have direct operator evidence.
The background color pass no longer writes scene depth; opaque Studio textures
use GPU mip/trilinear filtering; STEP origin/angle interpolation restores fluid
walking. Runtime DualSense exploration is active. See XASH3D_CHECKPOINT and the
port's PHASE7_BASELINE_REGRESSION for artifact/run identities and resource proof.
Full Studio fidelity, viewmodel, chapter-title blending and live-client audio
remain open: graphics runs use XASH_AUDIO=0. This does not close Phase 7.

## Phase 7 texture-memory policy — 2026-09-09

Pinned Xash3D `70ebea8` (merged PR #26), memory task accepted.

Plan revision 43 replaces the fixed texture test budget with measured explicit
or automatic startup capacity. The explicit 256-MiB run passes 1,999 frames;
the automatic run passes 10,994 frames and exact resource teardown. Host tests
cover allocation rollback and cache exhaustion. See XASH3D_CHECKPOINT and the
port's PHASE7_TEXTURE_MEMORY_POLICY for full evidence and limitations.
Historical rev 45 order: Studio lighting/viewmodel, then game audio, then optional
valve_hd QA. Texture memory policy and HUD are done. Xash3D PR #27 merged
as `4726bd3`; that was the rev 45 port pin, superseded by rev 46 below.

The operator accepted the corrected chapter title and removal of the white-scene
flash. Corrected paired runs `20260909T134011789Z` / `20260909T134011848Z`
passed 10,992 frames, nine exact reclaims, intact guards, zero errors and clean
BYEs. The final controlled three-font/two-fade exercise was also accepted by
the operator. Paired runs `20260909T140302704Z` / `20260909T140302761Z` pass
10,993 frames, nine exact reclaims, zero errors and clean BYEs. The normal
non-probe build was restored by exact FTP hashes without relaunching.
Studio scope is lighting, chrome, controllers, animation transitions and
viewmodel, preserving accepted smooth NPC walking. Audio remains a separate
fourth task; this focused acceptance does not close Phase 7.

## Phase 7 Studio/input integration — plan rev 46

Xash3D PR #28 merged with green CI as `3cebf56`, the previous lab pin. It integrates
accepted NPC lighting, NPOT texture correction and
ordinary chrome, callback save/restore coverage, separate viewmodel drawing
and the DualSense v5 profile. Operator QA confirms pistol/crowbar use,
immediate weapon cycling and preferred aim at 140/105 degrees/s with radial
deadzone 10% and exponent 1.6. R2 is primary attack, R1 secondary. Use the
port's SCEPAD_PHASE5 guide for the current profile rather than engine defaults.

Lighting/NPOT and chrome normal runs each passed 10,990 frames and exact
teardown. Viewmodel effects/events/reload and remaining Studio coverage,
transition-aware evidence, game audio, valve_hd and release gates remain open.
The normal no-grant build is restored without relaunch; graphics audio remains
disabled. Full evidence and limitations are in XASH3D_CHECKPOINT rev 46.

## Historical renderer boundary

The former Phase 0 and Stages A–I proved the path from direct memory and simple
DCBs through triangle, cube and early Gears rendering. Their source now lives
under `legacy/`; detailed notes and private evidence remain under
`research/gpu/`. They are useful provenance, not current instructions.

Commercial-game dumps, Ghidra databases, runtime captures and proprietary
material remain local research inputs and are never copied into a public repo.
