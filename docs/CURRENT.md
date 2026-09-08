# Current development boundary

Last reconciled: 2026-09-08. Tested console firmware: PS5 12.02.

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
history of `projects/ps5-xash3d`. This laboratory now pins the merged Phase 6
client-PRX commit `3a30250`, which includes the dedicated title icon from
`ea9be4b`; the preceding MainUI-PRX implementation is `9f783ec` and the
dedicated identity began at `c09318f`.

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
rollback point; `ref_agc` is the only remaining Phase 6 conversion.

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

## Win32 compatibility layer

prospero-win (PPSA99995) targets original Windows binaries. AMD64 execution
requires Win64 ABI bridges; x86 requires software execution because the tested
LDT compatibility-mode route is refused on FW 12.02. Neither application
execution path is complete. The first game target is original Space Cadet
Pinball, without recompilation; DRM and anti-cheat are out of scope.

Phase 0.1 synthetic mapping passed. The original Pinball PE32 also passed
mapping on PS5 in run
`20260908T145242477Z_PPSA99995_prospero-win_0x1021ed623a4eb`: exact base
0x01000000, 311296 reserved bytes, three verified sections, zero mismatches,
one image released and clean BYE. Eight host DLL bindings remain unimplemented.
The validator accepted --allow-i386 and --allow-wx; one 16 KiB page merges
write/execute permissions. That mapping run executed no guest instructions or graphics.

Subsequent bounded host translation executed 317 instructions (4096-event limit) from the original
Pinball entry plus GetModuleHandleA(NULL), returning the mapped base 0x01000000,
and the CRT state setter __set_app_type, both mode-pointer getters, _controlfp, _initterm and __getmainargs.
It now binds 207 imports (205 function tokens, two CRT data words) and stops
after GetStartupInfoA and the original initializer callback with its enclosing _initterm.
Thirteen distinct APIs completed (fifteen calls). Six clock/ID handlers have host
unit tests, with PS5 clock wiring pending. Nested callback evidence remains synthetic.
Guest FP control state and CRT mode-pointer getters also
have host unit coverage. Other handlers remain pending; binding is not implementation.
This is not PS5 guest execution or completed Win32 startup.
See `projects/prospero-win/docs/X86_EXECUTION.md`.

The next API work is inventory-first, not incremental runtime discovery.
`inventory_imports.py` confirms 207 imports across eight DLLs, all with Wine
spec declarations at commit 490f6d5dcbb2a5047345b8af88d114bbcaad69a8.
Two are data exports and three are variadic; none are implemented by merely
finding a declaration. The private report is under the main lab's ignored
`research/gpu/captures/prospero-win/20260908-import-inventory/pinball.json`.
See `projects/prospero-win/docs/IMPORT_PLAN.md` for subsystem and license review.
The follow-up Wine audit covers export routing and source-reference leads
for all 207 imports; its private report is `wine-audit-v2.json` in the same
capture directory. Reviewed CRT requirements include x87 helpers, guest
initializer callbacks and x86 SEH. No Wine implementation has been extracted
yet. See `projects/prospero-win/docs/WINE_REUSE_AUDIT.md` for boundaries and
known limitations of lexical source indexing.
Shared integer cdecl/stdcall call frames and callback services now pass host
tests, including a translated synthetic callback returning through the
adapter. This does not implement a Win32 API or validate PS5 callbacks.
Scope: `projects/prospero-win/docs/GUEST_ABI.md`.
The shared PE32 import binder passes synthetic function/data, ordinal and
failure-atomicity tests and is integrated in the original Pinball host trace.
The catalog and narrow first API case are in `src/pw_win32.c`; full subsystem
implementations and console integration remain pending.

Single-mapping mprotect RW-to-RX works on the tested firmware. Low allocation
does not eliminate x86 address/stack rewriting or establish a large guest
working-set budget. Next: extend the bounded x86 translator, validate it on
hardware and implement the Pinball Win32 surface. Reuse Xash3D audio/input contracts
with WinMM and Win32 adapters; resolve component licensing before extraction.

Canonical status, artifact hashes and acceptance command:
`projects/prospero-win/docs/PINBALL_TARGET.md`. Scope and sequence:
`projects/prospero-win/docs/ROADMAP.md`. Project licence: LGPL-2.1-or-later.


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

## Historical boundary

The former Phase 0 and Stages A–I proved the path from direct memory and simple
DCBs through triangle, cube and early Gears rendering. Their source now lives
under `legacy/`; detailed notes and private evidence remain under
`research/gpu/`. They are useful provenance, not current instructions.

Commercial-game dumps, Ghidra databases, runtime captures and proprietary
material remain local research inputs and are never copied into a public repo.
