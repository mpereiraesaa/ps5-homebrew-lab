# Xash3D on PS5 checkpoint

Reconciled: 2026-09-07. Hardware boundary: one PS5 on firmware 12.02.

## Current position

| Phase | State | Proof / boundary |
| --- | --- | --- |
| 0 — Close the ledger | Complete | Public renderer, protected `main`, CI, reproducible GFX1013 compiler and evidence rules. |
| 1 — BSP viewer with noclip | Complete | `c1a0`, 3,611 draws, 164 base textures plus lightmap, physical DualSense movement and a clean 60,000-frame textured gate. |
| 2 — Resource foundation | Complete | Fence-retired pool, two-slot transient ring, V#/T#/S#, per-frame constants, two pipeline permutations, cache contract and a clean 60,000-frame gate. |
| 3 — Texture path | Complete, 6 gates closed | Dynamic lightmap, deterministic mips/filtering, alpha test, sky, exact accounting and the final 60,000-frame soak are hardware-proven. |
| 4 — GoldSrc render states | Complete, 8 gates plus final soak | Full state matrix, viewport/scissor, 2D, lighting, transient effects, Studio, brush entities and world visibility are hardware-proven; the integrated scene passed 60,000 frames with zero errors. |
| 5 — Platform layer | Gate 1 passed | The Xash3D FWGS engine boots on the console in dedicated mode with static `filesystem_stdio` and hlsdk server, spawns `c1a0` with all 251 entity classes, simulates 90 s and quits cleanly; ScePad, AudioOut and the direct-memory allocator follow. |
| 6 — Engine integration | Later | Modular Xash3D boot with `ref_agc`, menu, client, server and filesystem PRX modules. |
| 7 — Playable and release | Later | Gameplay/performance and level-transition soaks, clean reproducible release. |

The Phase 1/2 implementation was merged through
`mpereiraesaa/ps5-agc-gears#8` as commit `642d348`. The complete Phase 3 texture
path was merged through `mpereiraesaa/ps5-agc-gears#9` as commit `cbff264` after
all host and security checks passed. On 2026-09-06 the port moved to its own
repository, `mpereiraesaa/ps5-xash3d`, forked from `cbff264` with full history;
the laboratory submodule `projects/ps5-xash3d` now pins merged Phase 4 commit
`38c6a38`.
`ps5-agc-gears` is frozen as the Gears demo (`ps5-agc-gears#10` reverts #8/#9).

## Evidence closing Phase 2

- Run:
  `20260906T130036578Z_PPSA99997_ps5-agc-gears_0x5ed84765862b`.
- Requested/completed/connected: 60,000/60,000/60,000; renderer, pad-read and
  present-budget errors: 0/0/0.
- Exact fence plus VideoOut-token retirement; two transient slots reusable;
  four persistent pool allocations reclaimed; guards intact.
- 164 BSP textures, 3,936 descriptor DWORDs and two resource pipelines.
- Transcript SHA-256:
  `8a7b8ce9aa03552f92c1717ff7bb4d836b616a8b399cf938951ac21f21e4c66e`.
- Rebuilt ELF/fSELF hashes exactly reproduce the deployed artifact:
  `1a1f33e840d919f090accce6d4a5593044058c0f32386a2986cd2715e64b050c` /
  `695a5db926fc36e4d246c866e2d47cb0de8bd55904d495c1bf646f16c211e756`.
- The map region is identical across the pulse capture pair; the overlay green
  mean changes by approximately 30.2 levels, and the operator confirmed the
  pulse live.

Private BSP data, binaries, full logs and Remote Play captures remain outside
the repository. Public documentation records only sanitized identities,
cardinality and hashes.

## Phase 3 execution order

### 3.1 Dynamic lightmap patch

Change only one new capability: write a bounded lightmap rectangle every frame
and sample it in the existing BSP pipeline.

1. Allocate the update/staging bytes through the Phase 2 ownership model.
2. Flush the aligned CPU-written range and emit the hardware-observed
   AcquireMem tuple (engine `1`, GCR `0x00009000`, poll `0x190`).
3. Alternate two unmistakable values and prove that the GPU-visible/readback
   region changes while surrounding pixels and guards remain stable.
4. Require exact slot retirement, zero errors and a clean 10,000-frame soak.

No new sampler mode, mip chain, shader branch or sky pass belongs in this first
gate. Physical DualSense movement is already proven and does not need repeating;
connected/read-error continuity is sufficient unless input code changes.

### 3.2 Sampling completeness

1. Extend the baker with deterministic mip chains.
2. Encode mip-aware T# descriptors and trilinear/anisotropic S# variants.
3. Keep linear layout as the reference; investigate swizzle only after measured
   frame timing justifies it.
4. Gate descriptor words and mip offsets on the host, then prove visual/readback
   differences on hardware.

### 3.3 GoldSrc texture semantics

1. Alpha test for `{` textures as its own pipeline permutation — complete.
2. Sky as a separate pass — complete in run
   `20260906T165427904Z_PPSA99997_ps5-agc-gears_0x6b9b27deac05` with 158 sky
   draws, distinct skip/pass GPU readbacks and 10,000 clean frames.
3. Emit consolidated resident bytes and per-frame upload bytes in structured
   telemetry — complete in the 10,000-frame accounting gate.
4. Finish with a 60,000-frame Phase 3 soak before declaring the phase complete
   — complete in run
   `20260906T182418688Z_PPSA99997_ps5-agc-gears_0x70824724af5d`.

The final run completed 60,000/60,000 frames with zero renderer errors, no
presentation intervals over 17 ms, exact fence/VideoOut ownership and intact
guards. It proved 122 mip chains; 2,915 opaque, 137 alpha-tested and 158 sky
draws; 68,731,904 pool-resident bytes; 781,471,872 total uploaded bytes; and a
gap-free accounting digest `b4f0d5a0fa607141`. Its transcript/manifest hashes
are
`b69d5a9cd514d4ef94d3b706fc9005340f054add33c1e4ff8f941649ff4e39f4`
and
`b977861bf0d6ebe08883176c0843ef52674a5a25cd2da40eab5d49e049c87c0d`.
The exact title was closed after validation and all four console services
remained stable. Phase 3 is complete; Phase 4 render states are next.

The pre-Phase 4 identity gate is complete. `ps5-xash3d` now owns the dedicated
local development identity `PPSA99996`; the frozen Gears demo remains installed
as `PPSA99997`. Separate exact-title launch/close helpers are wired through
`tools/night_supervisor.py`. Run
`20260906T205728904Z_PPSA99996_ps5-xash3d_0x78de031d5d51` presented 1,440
frames at 59.94 fps with zero renderer errors, reproduced the accepted Phase 3
122-chain and 2,915/137/158 draw shape, and was then removed by the exact
`PPSA99996` helper. Independent status observed no BigApp and all four console
services remained healthy. This was an identity smoke gate, so its external
close intentionally produced a gap-free EOF without BYE rather than repeating
the already accepted 60,000-frame completion gate.

The historical native host `PPSA99998` was uninstalled from the console: its
four possible installation/mount paths are absent and the live `app.db` has no
matching cells. Its source remains archived under `legacy/` and its exact
pre-removal files have a private recoverable laboratory backup; it is not an
installed application or an active workflow.

Phase 4 gates 1–3 are closed in `ps5-xash3d`. The native catalog contains
99 semantic states and nine `gfx1013` shader variants; real opaque/masked draws
and mid-frame viewport/scissor restoration first passed 10,000 frames. Run
`20260906T223113472Z_PPSA99996_ps5-xash3d_0x7dfb90d3b053` then exercised nine
actual BSP render cases covering opaque, alpha, additive, alpha test,
depth-write on/off, cull front/back/none, fog on/off and lightmap on/off. It
completed 10,000/10,000 frames with 18 post-retirement framebuffer readbacks,
distinct feature/control images in both slots, exact fence/VideoOut ownership,
intact guards, six reclaimed allocations, a gap-free BYE and zero renderer
errors. Its ELF/fSELF/transcript hashes are
`d914bcf26b5aa3e0ca17eb3c99a10cdb3abb929bf89f9817e96f7640f9baf2e6`,
`31de1cf508c26f36217bb04aaa87140e191a71880a95e124a504d29c62441b9a` and
`d875d6793d92407e297daef313c7ad24ab84d5ada3abc0b15fd04f2381805ef3`.

Run `20260906T225115588Z_PPSA99996_ps5-xash3d_0x7f137394ac44` then closed
the orthographic 2D gate. It bound `screen_2d` alpha/additive keys 129/130 and
drew 522 indices per frame from a deterministic procedural atlas plus
per-frame transient constants, descriptors and geometry. The visible result
combined the BSP world with a translucent console, menu, HUD, 78 bitmap glyphs
and an additive crosshair. It completed 10,000/10,000 frames with exact
fence/VideoOut ownership, intact guards, six reclaimed allocations, a
gap-free BYE and zero renderer errors. Its ELF/fSELF/transcript/capture hashes
are `b7b2ef1e9cf4679bbe5edea37a8511aecdac3352252c7d48ffea0d6e70ac3dde`,
`f391dbbae2f90a34f64a3593418be137a4efd5099651254724144bf1665404b2`,
`12c94237d1aa4fb5e762372549e7e803f2df7781468b862af5a70a513237ac39`
and `7102eadff45ee1b3c8598d02e5480fba1bc736494a0f80dfd7dbe46b936ee383`.
The exact CLI stream and title were closed, independent status found no
BigApp, and all four services remained healthy.

Run `20260906T233103794Z_PPSA99996_ps5-xash3d_0x813f7d9b54cf` then closed
Phase 4's fourth gate. The compatible version-3 bundle preserved every source
lightstyle plane from privately owned `c1a0e.bsp`: 3,052 lightmapped faces,
734,229 source-sample bytes, 528 styled faces and 1,084 style layers. The
runtime selected wall face 203 (draw 379, styles 0/33/35) and alternated base,
animated lightstyle, a face-local radial dynamic light and their combined
result every 600 frames. After each slot's initial full upload, the existing
Phase 3 path uploaded only the 704-byte 11×16 atlas patch.

The 10,000-frame FW 12.02 run produced exactly eight post-retirement
framebuffer readbacks, covered all four modes on both slots and kept every
same-slot result distinct. Fence and VideoOut ownership were exact, guards were
intact, six allocations were reclaimed, all 266 records were gap-free and
renderer errors stayed at zero. Its ELF/fSELF/bundle/transcript/manifest hashes
are `7cf6d6b7c0e4ace01781de5f8c63f18b8a7be09b2b5113cdd0c1bf215f0f62dd`,
`dd66e6c4659b8bc4453720c003c549683c884d40d9906c3b7e9859f6fff14506`,
`0e6396cf2dbec287c4e2bc28f90a90e8f5cb26b98f43ebcd539dba7d9c171105`,
`f1c69e8d1825275da6716aeff6f0620c516f8fb4e708a45b18f8e19cd00e620b`
and `197c0086ac8e72e91ff01465c513a029d95c39e690e2d611231a35c12cd10060`.
Chiaki reused the registered entry through the isolated CLI helper; no pairing,
client window or focus assumption was involved. Exact PID/title closure left
no BigApp, all services healthy and `PPSA99998` absent. The next ordered gate
was transient sprites plus particles.

Run `20260906T235831459Z_PPSA99996_ps5-xash3d_0x82bf1cd8fb89` closed that
fifth Phase 4 gate. A procedural 64×32 RGBA8 atlas, one camera-facing sprite,
24 alpha smoke particles and 48 additive sparks were rebuilt from the current
framebuffer slot of the existing transient ring. Four 600-frame modes issued
0/1/2/3 draws and 0/6/432/438 indices, respectively. The 10,000-frame FW 12.02
run captured all four modes on both slots after fence zero and exact VideoOut
retirement; every feature/control and combined/isolated comparison was
distinct. It kept guards intact, reclaimed six allocations and ended with zero
renderer errors plus a 284-record gap-free BYE.

Its ELF/fSELF/bundle/transcript/manifest hashes are
`b88df7b004495d828db7a594d1579a56fe4925578d384bef01b95b8ae5d63778`,
`33e804f669a7acdddaf8a38a6a3f51ee6b0ae2d946bd0fc97a347596d33dcf2a`,
`0e6396cf2dbec287c4e2bc28f90a90e8f5cb26b98f43ebcd539dba7d9c171105`,
`e6d77a34f5276f59c12ac987f67a7720394b88c2788ee06e72f9f6ec8b9d4a05`
and `6df527c58ea91bd060f3c570eda910d383b40a2018b5cb17751d128256a35899`.
Three accepted CLI-stream captures visibly isolate sprite, particles and their
combined result. Chiaki and the title were closed by exact PID/identity; no
BigApp remained, all services were healthy and `PPSA99998` stayed absent. The
next ordered gate is animated studio models with CPU skinning, per-model
textures, chrome and additive modes.

Run `20260907T003611716Z_PPSA99996_ps5-xash3d_0x84cd5cd0ac8a` closed the
sixth Phase 4 gate. A host-only Studio v10 baker converted the privately owned
source model into a 93,952-byte checked bundle containing eight bones, a
seven-frame 33 fps sequence, 134 expanded vertices, 282 indices, four draws
and four embedded textures. The PS5 runtime keeps its texture data in the
existing BSP allocation and performs interpolation, bone-hierarchy composition
and CPU skinning into the current transient-ring slot. Five modes isolate
control, textured, generated chrome, additive and the combined three-instance
result.

The FW 12.02 gate completed 10,000/10,000 frames, ten post-retirement
readbacks, changing pose hashes, six reclaimed allocations, intact guards,
zero renderer errors and a 286-record gap-free BYE. Its
ELF/fSELF/BSP/Studio/transcript/manifest hashes are
`a78675524a21b2a7b2264e3b271a4b80954333b01cd82456ee4fda3da7af1e52`,
`0e0614f13bef7a0121ac6bde5cde0480f4e1162e8c6c6e8bfd008df71cd4dace`,
`0e6396cf2dbec287c4e2bc28f90a90e8f5cb26b98f43ebcd539dba7d9c171105`,
`d5b3a1f9b5c9035b02e678079b3586a5fe35987d55167dab27868050969b3e31`,
`2cf010f8b95529265e9095efe2a4882e31965b3afaa459c02f829333d7acf03d`
and `fe93f51167b551f47e82831d272513a7886a25564947f82e3b6c7d68791f6290`.
The accepted combined CLI-stream capture visibly contains all three model
modes. Chiaki and Xash3D closed by exact PID/title, all services remained
healthy and `PPSA99998` stayed absent. The next ordered gate is independently
transformed brush entities with their own render modes.

Run `20260907T010315223Z_PPSA99996_ps5-xash3d_0x86475c3277bb` closed the
seventh gate with three real BSP brush entities using independent animated
transforms and source opaque/alpha/additive modes. Run
`20260907T013429215Z_PPSA99996_ps5-xash3d_0x87fbad4e6ed0` then closed gate
eight: real world-tree PVS plus draw-AABB frustum tests reduced 1,952 world
draws to 646/414/362 while stable retired readbacks remained within their
declared tolerance. Inline brush submodels retain their independent transformed
path rather than sharing world-tree visibility numbering.

The complete Phase 4 soak is
`20260907T020656141Z_PPSA99996_ps5-xash3d_0x89c0f978ef68`. Its final
600-frame window simultaneously composed 362 world draws, five brush entities
(69 draws, including real `func_water` and `glass_med` source content), three
animated Studio instances (12 draws), one sprite plus 72 particles (3 draws)
and the HUD/console/menu/font overlay (2 draws). It completed 60,000/60,000
frames in one process with 86,810 transient bytes per 131,072-byte slot, two
post-retirement readbacks, exact fences and VideoOut tokens, intact guards, six
reclaimed allocations, 2,613 gap-free records, dedicated BYE and zero errors.

The final ELF/fSELF/BSP/Studio/transcript/manifest hashes are
`d5499ae773f72e99a2eb7082206a04cb7deb00e43d6bbd463d7ecceb6c685dee`,
`8af678d50024aa09caeae82abc97101d9f4fd859a7f7ac11420e783461054de0`,
`d66be922584d7537e2dca7233293195d6ae383b22fc7959853537a75815c5cfa`,
`d5b3a1f9b5c9035b02e678079b3586a5fe35987d55167dab27868050969b3e31`,
`0bbccaee2e59eb8f516a29296300fb4f061fa2151aa22ceadf3c511a2b298f9f`
and `a08dd9d7b851f75e8f22d875358cac76f933246a50821c38759fb2c9c16feebe`.
The fail-closed validator accepted the immutable manifest, and a visible
registered-entry CLI-stream capture has SHA-256
`751d0fee9d54bb815acf3a5edc1ded8981cce0aca3f07b83ae4ff2344a8800a1`.
Exact PID/title closure left no BigApp, all four services healthy and
`PPSA99998` absent. Phase 4 is complete; Phase 5 is next.

## Parallel work that is now de-risked

The reproducible symbol probes show that libc/C++ is not the port blocker:

- the client has three real SDK gaps: `__assert`, `getpwuid` and `dladdr`;
- `mainui`, client hlsdk and server hlsdk need no additional C++ runtime;
- application PRX load, relocated export descriptors, calls and unload are
  already hardware-proven.

Therefore Phase 5 can prototype the three tiny C shims and a minimal
`platform/ps5` while Phase 3/4 mature, but it must not bypass the renderer gates
or start full engine integration prematurely.

## Phase 5 gate 1: engine boot (2026-09-07)

Run `20260907T074705479Z_PPSA99996_xash3d-engine_0x9c50d46dcc2a` on FW 12.02,
archived under `research/gpu/captures/runtime/`, validated by
`ps5-xash3d/tools/validate_engine_boot_evidence.py`: engine `9aa39ad` and
hlsdk `e277ffa` built without waf (`ps5-xash3d` PR #3, branch
`exp/engine-boot`), `filesystem_stdio` and `server` resolved from the static
tables, `valve` mounted from `/app0/xash3d` with `/download0/xash3d` as the
writable root, `Spawn Server: c1a0`, `0 entities inhibited`, `4 player server
started`, 90 s of simulation, `PS5_XASH_GATE_TIMEOUT ... action=quit`,
`XASH_EXIT result=0`, 20 structured records, 38 console lines, no gaps.
Transcript SHA-256
`3c3d176c9f22d61db4c2c4911c676e81db3a5b16f8139be00cc3ce9ff5f06965`; ELF/fSELF
`fa8df6b95c328123016243322bf4f51950252d0a1ed1f743974ec8b1769fe453` /
`7d6747d276acd57411ab5e282f6f1672c0f796d7de336e7f5090141f910ce67b`.

What the sandbox actually allows is recorded in `FINDINGS.md`, "Xash3D engine
boot: contrato real del sandbox": closed stdio descriptors, `chdir`/`access`
refused, a faulting `getcwd`, an unlistable image, an 8 MiB libc heap and
non-blocking sockets refused on UDP. Each has a shim or a build step in
`xash/platform_ps5/`; the engine sources are untouched. Remaining Phase 5
gates: `filesystem_stdio` as an application-owned PRX, ScePad, AudioOut, the
direct-memory allocator and frametime instrumentation.

## Remote Play operating contract

Chiaki already has a valid console entry. Never pair or re-register it during a
normal test. The helper starts that entry directly in console mode, so the
discovery/client window is not part of the workflow. If physical DualSense
takeover ends Remote Play, `stop-stream` identifies and terminates only the
exact isolated CLI process; `stream` performs the same stale-process cleanup
before restarting. Neither path activates or acknowledges the Qt dialog,
assumes focus, moves the pointer or synthesizes movement. The helper works
around Chiaki 2.1.1's second-entry CLI bug with a private temporary copy of the
existing PS5 registration; no pairing, re-registration or credential logging
occurs.
