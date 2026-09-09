# Xash3D on PS5 checkpoint

Reconciled: 2026-09-09. Hardware boundary: one PS5 on firmware 12.02.

## Current position

| Phase | State | Proof / boundary |
| --- | --- | --- |
| 0 — Close the ledger | Complete | Public renderer, protected `main`, CI, reproducible GFX1013 compiler and evidence rules. |
| 1 — BSP viewer with noclip | Complete | `c1a0`, 3,611 draws, 164 base textures plus lightmap, physical DualSense movement and a clean 60,000-frame textured gate. |
| 2 — Resource foundation | Complete | Fence-retired pool, two-slot transient ring, V#/T#/S#, per-frame constants, two pipeline permutations, cache contract and a clean 60,000-frame gate. |
| 3 — Texture path | Complete, 6 gates closed | Dynamic lightmap, deterministic mips/filtering, alpha test, sky, exact accounting and the final 60,000-frame soak are hardware-proven. |
| 4 — GoldSrc render states | Complete, 8 gates plus final soak | Full state matrix, viewport/scissor, 2D, lighting, transient effects, Studio, brush entities and world visibility are hardware-proven; the integrated scene passed 60,000 frames with zero errors. |
| 5 — Platform layer | Complete | Engine/bootstrap, retail filesystem, ScePad, SceAudioOut, direct memory, threads/time, GPU/flip timing and project-owned libc shims all have accepted FW 12.02 evidence. |
| 6 — Engine integration | Complete, 6 gates closed | Hybrid `COM_*` loader plus dynamic filesystem, server, MainUI, GoldSrc client and RefAPI 18 `ref_agc` are hardware-proven with exact teardown. |
| 7 — Playable and release | Active, native MainUI closed | Live `c1a0` world/special surfaces/2D and MainUI are native AGC output with exact ownership; the menu transitions to `c1a0` in-process. Entities/viewmodel, fixed-camera comparison, gameplay/performance, transition soaks and release remain open. |

The Phase 1/2 implementation was merged through
`mpereiraesaa/ps5-agc-gears#8` as commit `642d348`. The complete Phase 3 texture
path was merged through `mpereiraesaa/ps5-agc-gears#9` as commit `cbff264` after
all host and security checks passed. On 2026-09-06 the port moved to its own
repository, `mpereiraesaa/ps5-xash3d`, forked from `cbff264` with full history;
the laboratory submodule `projects/ps5-xash3d` now pins merged Phase 7
native-menu checkpoint `a975b86`; the preceding live-2D checkpoint is
`0bdcbfb`, and the preceding live-special-surface checkpoint is
`77c742a`, the preceding live-lightmap checkpoint is `4f9d38d`, the preceding
compositor-visible world checkpoint is `cdcce91`, the preceding live-world
submission checkpoint is `bd4b250`, and
the Phase 6 final renderer checkpoint is `258fbe3`, the
preceding client-PRX checkpoint is `3a30250`,
and includes the dedicated title icon from `ea9be4b`.
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
`PPSA99998` absent. Phase 4 is complete; Phase 5 is in progress.

## Parallel work that is now de-risked

The reproducible symbol probes show that libc/C++ is not the port blocker:

- the client has three real SDK gaps: `__assert`, `getpwuid` and `dladdr`;
- `mainui`, client hlsdk and server hlsdk need no additional C++ runtime;
- application PRX load, relocated export descriptors, calls and unload are
  already hardware-proven.

Therefore Phase 5 closes the non-drawing platform contract before Phase 6
starts full client, renderer and modular engine integration.

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
`xash/platform_ps5/`; the engine sources are untouched. Xash PR #3 is merged
as `23899eb99476980806627b28ba5243e3ab2260f3`, which is now the lab submodule
pin.

## Phase 5 filesystem checkpoint: closed (2026-09-07)

The accepted full-tree run
`20260907T155915636Z_PPSA99996_xash3d-engine_0xb72c42a8f42f` transactionally
deployed 4,741 files / 555,437,162 bytes, served a 4,823-entry directory index,
resolved and read the 12,565-byte `delta.lst` twice, executed `c1a0` for 90
seconds and ended with `XASH_EXIT result=0`, gap-free BYE and zero large
allocation failures. This closes indexed directory listing, case-correct
lookup and large/repeated reads over the retail tree. The current `ftpsrv`
completed that dataset deployment; FTP was not the crash source.

The deterministic fault originally attributed to `FS_LoadFile` was outside
the filesystem lifecycle. Instrumentation proved `gfx/palette.lmp` had
`real_length=768`, allocated 769 bytes, read 768 bytes and closed with result
zero. The SDK provider mapping then showed `strcasestr` routed through
`libScePosixForWebKit.sprx`, not `libSceLibcInternal`. Setting
`HAVE_STRCASESTR=0` selects Xash3D's portable `Q_stristr`. Fixed run
`20260907T154452596Z_PPSA99996_xash3d-engine_0xb663524c9f61` booted beyond the
fault; fSELF SHA-256
`b622cec5561f1cfb49731e6cad9b58cad49480afd970ee8fe9e6e858952666dc`, linked
ELF SHA-256
`f4287a6f817ecdab19a1c8a60433cf3c6f33324e767a51b32aa543e8bb311c11`, and
`llvm-readelf --dyn-syms <elf> | grep -i strcasestr` is empty.

The four other `HAVE_*` decisions remain enabled because they passed focused
hardware smoke, not merely because the SDK exports a name. Run
`20260907T162442485Z_PPSA99996_xash3d-engine_0xb88fc0cf77a3` produced
`strcasecmp=0`, `strnlen=4`, `strlcpy=7` with value `palette`, and
`strlcat=11` with value `gfx/palette`, then loaded `c1a0` and exited cleanly
after 20 seconds. ELF/fSELF SHA-256:
`f40d7c2b3cad0f56e96ef974785cbc53b4c6512bf3dd05b871ef985ed4aec7a1` /
`3aa7835949b1dd0f98de9fc8d6a9dec36fc16c68460617304b20eabb7cb5ce9f`.

`xash/tools/audit_dyn_imports.py` and `xash/ps5_import_evidence.json` make that
distinction reproducible. The current pad-gate ELF has 173 dynamic imports: 27
hardware PASS, 3 hardware FAIL/GUARDED (`dup`, `dup2`, `execv`), 143 EXPORTED
ONLY and zero banned imports. The four approved string helpers map to
`libSceLibcInternal`; `strcasestr` maps to `libScePosixForWebKit`.

## Phase 5 ScePad checkpoint: closed (2026-09-07)

Xash3D PR #4, merged as `dfef288`, adds the native C ScePad backend and its
host contracts. It consumes every oldest-first record from batches of up to
64, translates both sticks, triggers and the standard button surface to Xash
events, and neutralizes state on disconnect, interception, read error or
controller-generation change. ShadowMount/LNC uses the foreground user; the
backend closes the pad exactly once and terminates UserService only when it
owned initialization.

Accepted FW 12.02 run
`20260907T181827569Z_PPSA99996_xash3d-engine_0xbec4d1cc932e` processed 24,535
connected records across 4,361 polls, reached a 62-record batch, and recorded
1,286 movement plus 1,258 look samples. Jump, crouch, use and fire each have
complete press/release evidence (1/1, 2/2, 2/2, 1/1), with zero read errors,
`scePadClose=0`, owned `sceUserServiceTerminate=0`, `ownership=exact`,
`pass=1` and a gap-free BYE. ELF/fSELF SHA-256:
`46da56f13a7d17f0b7d2323e2cc5d0fa16cb0d40997c25f9e5c73e527a15500a` /
`6681a8a822edf1114a5e9f32d01286b90442430a35a180295909d3ab8ca15d82`;
transcript SHA-256
`6dd2db62d23b2aa33f0387bacf2c4b534e4e64317562c4489b5bb3a2b21d20da`.

## Phase 5 SceAudioOut checkpoint: closed (2026-09-07)

Xash3D PR #5, merged as `41f4912`, adds the native `libSceAudioOut` PCM
backend. A client-independent C core owns a producer/consumer ring, a
continuous 147/160 resampler and a dedicated worker; the worker alone holds the
handle and calls `Output`, the NULL drain and `Close`, and the mutex is never
held across the blocking `Output`. `s_ps5.c` binds that core to Xash3D's own
DMA ring.

The rate mismatch mattered: Xash3D mixes at `SOUND_DMA_SPEED` (44100) and
AudioOut takes only 48000 or 192000 Hz, but `s_main.c`, `s_stream.c` and
`s_load.c` compute mixahead, stream timing and the default sound rate from that
macro directly, so reassigning `snd.format.speed` would not have been enough.
The upstream submodule stays untouched and the conversion happens in the PS5
layer with phase preserved across block boundaries.

Accepted FW 12.02 run `20260907T194413175Z_PPSA99996_xash3d-engine_0xc372db81ccc6` opened the main port for the system user `0xff`
(type 0, index 0, handle `0x20000000`) and carried 66,150 source frames as
72,192 frames in 282 whole 256-frame blocks: 71,999 resampled plus 193 terminal
padding, the exact 147/160 relation. The consumed PCM hash
`0x9fd6b8c32bb54595` equals the independently generated pattern hash. Zero
underruns, zero `Output` errors, zero discarded frames, ring high-water 8,192
over 8 wraps, exactly one drain/close/join owned by the worker,
`ownership=exact pass=1`, `XASH_EXIT result=0` and a gap-free BYE. The operator
confirmed hearing the low tone, the gap and the higher tone in that order —
external evidence tied to the run id, since the device cannot assert
`audible=true` about itself. ELF/fSELF SHA-256:
`f6db533ac53728e86768c03c0b1b08e033ce3514348f8ea69cf8a9d9b3b9884e` /
`febef3a565810dd18565a3dfc707506a2fbbad0dd1d55e077cf91a5f540b7f74`; transcript
SHA-256 `f949a2d173b82c9415e3adb3f2c458947cf4600c98e254217d7b598c407a10bb`.
Run `20260907T195320217Z_PPSA99996_xash3d-engine_0xc3f2392f8174` repeated every counter and both hashes bit for bit with the
identical artifact.

Two FW 12.02 facts the FW 6.02 reference does not document: `sceAudioOutOutput`
returns the number of frames it accepted (256 at this grain), including the
NULL drain, so success is non-negative rather than zero; and the system user
`0xff` is accepted for the main port, so the foreground variant was never
needed. The handle is also a large positive value, so handle checks must test
for negative.

Scope stayed PCM only. AJM and AAC/MP3/Opus decode, AudioOut2, Audio3d, NGS2,
AudioIn and Chiaki capture remain out, and the link now rejects an artifact
that imports any of them.

## Final Phase 5 closure

### Direct-memory checkpoint: closed (2026-09-07)

Xash3D PR #7, merged as `cb7c2b3`, replaces the interim large-allocation
router with one guarded 128 MiB fixed-VA direct-memory arena for all C and C++
engine allocations. Its GPU ownership contract gives command, buffer, texture
and depth allocations unique generations and moves them through active,
retiring and reclaimed states only after exact completion proof.

Accepted run `20260907T212512180Z_PPSA99996_xash3d-engine_0xc8f58f777975`
loaded `c1a0` for 30 seconds, made 20,687 allocations and 1,091 reallocations,
and reached a 35,632,245-byte peak. All four resource retire/reclaim pairs
balanced; allocation, guard, stale-token and foreign-owner errors stayed zero.
Eight process-lifetime objects totaling 22,565 bytes were explicitly accounted
and reclaimed only after GPU ownership ended. Reserve/allocate/map and
unmap/release each occurred exactly once with rc 0, leaving zero live bytes and
a gap-free clean BYE.

### Threads and monotonic time: closed (2026-09-08 local)

Xash3D PR #8, merged as `ff0fd62`, adds a host-tested core and an exact native
gate. Accepted run
`20260907T220548886Z_PPSA99996_xash3d-engine_0xcb2ce47a2f65` created two
distinct workers: one joined and one detached exactly once. They completed
32,768 mutex-protected increments with zero lifecycle or mutex errors. The
gate recorded 8,192 `CLOCK_MONOTONIC` reads, 8,191 positive advances, an
801 ns minimum step and no errors or regressions.

Both `nanosleep` and the engine's historical `usleep` surface passed sixteen
samples at each of 1, 2, 5 and 10 ms: 128 samples total, with zero errors and
zero wakes earlier than the 50 microsecond tolerance. The same artifact loaded
`c1a0`, completed the 30-second engine window, preserved exact direct-memory
teardown and emitted a gap-free clean BYE. ELF/fSELF SHA-256:
`3e22c9f8d686dee19f94a4780e7494ccc6e0e9312c98662b854ee4c4e7b75bbf` /
`cd691f19664e44cd8cd6cfb9b019f5b6794f7a8410470a77ba86aec11e95bdde`;
transcript SHA-256
`45a5cb16d0f1fd2123db8075626c2007e7a01948609f14a1f31fc7a01146a50b`.

### GPU EOP and VideoOut timing: closed (2026-09-08 local)

Xash3D PR #9, merged as `cd57ab8`, adds an optional selector-3 end-of-pipe
timestamp before `SetFlip` while retaining the existing selector-2 ownership
fence. Accepted run
`20260907T225446311Z_PPSA99996_ps5-xash3d_0xcdd8ce3a668a` completed 60,000
consecutive correlated records and GPU writes, with 59,999 strict raw-clock
changes and zero regression, CPU-order error, sequence gap or renderer error.
Submit-to-fence averaged 16,823,795 ns, submit-to-flip 32,754,596 ns and the
CPU-observed fence-to-flip interval 15,930,800 ns. The raw GPU counter remains
in its own clock domain and is not mislabeled as nanoseconds.

The complete Phase 4 scene, exact fences/tokens and all guards remained valid.
The gate ended with `gpu-flip-timing-soak-complete`; its ELF/fSELF hashes
`bfbbd5fd89404765e0d52992df4abd1a1699d0e4df6398824748522392740ec1` /
`fdb489280c1bac1f2489f0449bbf8f914eaf7b4cb2f8436ea11d59abaa72e798`
were reproduced exactly after the hardware run.

### Project-owned libc shims: closed (2026-09-08 local)

Xash3D PR #10, merged as `a2cb856`, isolates the three narrow compatibility
semantics in `libc_shims_ps5.c`. Its release gate refuses dynamic imports of
`__assert`, `getpwuid` or `dladdr` and requires all three local definitions in
the full symbol table. Host tests pin assertion formatting/truncation, uid
propagation and the zeroed address-info fallback.

Accepted run
`20260907T235551519Z_PPSA99996_xash3d-engine_0xd12e2a9238fb` proved the
project-owned assertion reporter policy, stable `ps5` identity for uid `0xff`
and deterministic `dladdr` zero/`argv[0]` fallback, then indexed the complete
asset tree, loaded `c1a0` for 30 seconds and returned result zero. Its 30
structured records had no gap or error and ended in the normal clean BYE.
ELF/fSELF SHA-256:
`b87e61fc52230d2503290f92942fe2ab4b7d58730929bd30765aaaa926f957d0` /
`14c7c9e13d668ed782a2d98a19ada2e21f2003a8d8e7dccf52085a291096e569`;
both reproduced exactly after the hardware run.

This final incremental pass closes Phase 5. Every platform gate now has host
contracts, immutable FW 12.02 evidence and exact ownership/teardown where it
applies.

Client/menu integration, `ref_null`/`ref_soft`, `ref_agc` and conversion of
engine modules to application-owned PRXs are Phase 6. The early static client
harness remains useful diagnostic evidence, but does not close a Phase 6 gate.

### Application-owned PRX loader: closed (2026-09-08)

Xash3D PR #11, merged as `af99dcd`, replaces the static-only library adapter
with a hybrid backend. Exact static names keep the Phase 5 filesystem/server
path unchanged; other safe names map to `/app0/sce_module/<name>.prx`, load
through `sceKernelLoadStartModule`, resolve a range-checked `PRXDESC1` table
from `sceKernelGetModuleInfo` mappings and unload through
`sceKernelStopUnloadModule`. Bad ranges, unterminated names, duplicate exports
and invalid counts fail closed. A failed unload or rollback retains the handle
for an explicit shutdown retry.

Accepted run
`20260908T054317837Z_PPSA99996_xash3d-engine_0xe423c3826406` loaded four
segments and six exports, rejected one missing symbol, computed 42, observed
two calls including `sceKernelUsleep`, read version `0x10000`, round-tripped a
function name and released the module with active count zero. FW 12.02 returned
module info successfully with its input size word cleared and left
`auto_started=0`; explicit idempotent `module_start` returned zero and set the
probe state to one. The engine then loaded the static modules, spawned `c1a0`
for 15 seconds and emitted a clean BYE with 31 structured records, 40 console
lines, no gaps and no errors.

Gate ELF/fSELF SHA-256:
`1c8fd80e7cbcdadc4a03cb96449d1d49544c7b9741f229ede40255bb43034f6e` /
`c67f1cb7f1bd9e966d9364dec9ad9388afb89ee0bb07ee3091443a0e45f85b8f`;
transcript/manifest SHA-256:
`ebbec4fb52731b11726da8e246c41bf9400c5a13103a16cc4ad7fef1e461bfe1` /
`7d09166be6700f0f6f9076fc824fde63b48170ca5e2b39d0ac08be12d74f7c4c`.
The immutable validator accepted `--prx-gate`.

Normal regression run
`20260908T054524368Z_PPSA99996_xash3d-engine_0xe441394ac877` packaged no
probe (`prx_gate=0`), loaded the complete retail tree and `c1a0` through the
static fallback, and closed cleanly. The probe and all transactional deployment
files were removed afterward.

### Dynamic filesystem PRX: closed (2026-09-08)

Xash3D PR #12, merged as `0d1f0e0`, removes only `filesystem_stdio` from the
static table and packages it behind eight validated `PRXDESC1` exports. The
server remains static. Because FW 12.02 does not invoke the module entry for
this loading path, the `COM_*` owner explicitly calls `module_start` after
validation and `module_stop` before unload; partial initialization and failed
teardown retain ownership for rollback/retry.

Accepted run
`20260908T071044664Z_PPSA99996_xash3d-engine_0xe8e95e4c0974` mounted the
complete 4,823-entry private tree, returned 22 `gfx/*` results, resolved
mixed-case `GfX/PaLeTtE.LmP` to 768 bytes and read `maps/c1a0.bsp` at
2,546,336 bytes with stable non-zero hashes. The static server loaded
Half-Life and spawned `c1a0`. After 15.019 seconds, module state was still
valid, explicit stop and unload returned zero, active module count was zero,
the 128 MiB engine arena balanced and telemetry ended with a clean BYE.

The ABI deliberately leaves `LoadFileMalloc` on shared process libc because
the pointer is released by host `COM_FreeFile`. Rejected diagnostic run
`20260908T065949157Z_PPSA99996_xash3d-engine_0xe850bfc43c41` instead wrapped
the PRX allocator in a private arena: all filesystem reads passed, then libc
raised `SIGABRT` at the cross-module free boundary. The immutable validator
therefore requires `allocator_contract=libc-shared`.

Host ELF/fSELF SHA-256:
`0bdba330bbbe58f940f166fc9b2980fe21457ba8b1d7474b35b6ecda26a1d25d` /
`2e1f31f70403661c4f0e9a7e5f0d408816e5800c5f9c2169d790c831b3260861`;
PRX ELF/fSELF SHA-256:
`4a6f0d34200bad5892f0af3d2d194b31f930834d9178d11f7336391084b3588d` /
`888e0e73e6a228a9277600a009facb26933929752688b36633aa2f5c3f54740c`;
transcript/manifest SHA-256:
`808cc9a79c3892829f38f8865b9405d055a31c7aff37aa3571db14fdcdc09efb` /
`26752b034280ed22d99bc3112d2407e939729b85cc72df90e45f2962f338bf45`.

### Dynamic server PRX: closed (2026-09-08)

Xash3D PR #13, merged as `cbc5948`, removes the HLSDK server from the host and
packages it beside the already dynamic filesystem. Its generated descriptor
contains 257 entries: 251 engine exports, two bounded ABI probes and lifecycle
state/start/stop exports. The host retained no static filesystem or server
fallback for the accepted build.

Rejected run `20260908T081747518Z_PPSA99996_xash3d-engine_0xec9200150ba2`
isolated a real module-lifecycle rule. Six `CVarGetPointer` callbacks worked,
but the first `CVarRegister(&build_commit)` received `name=NULL` because the
two relocated `.init_array` entries had not run. The generated module startup
now invokes constructors forward and shutdown invokes finalizers reverse,
both idempotently. This corrected the fault without changing HLSDK source or
replacing a Prospero library.

Accepted run
`20260908T082646982Z_PPSA99996_xash3d-engine_0xed0f9a243abc` loaded four
server segments and all 257 descriptor entries, reported 251 engine exports,
proved ABI mask 7 and passed two non-mutating callbacks from PRX code into the
engine. The dynamic filesystem retained its 4,823-entry index, mixed-case
768-byte palette lookup and 2,546,336-byte `c1a0.bsp` read. The real HLSDK flow
then emitted `Spawn Server: c1a0`, loaded the graph and started a four-player
server. After 15 seconds, server stop/unload returned zero with the filesystem
still active; filesystem stop/unload then returned zero with no modules active,
exact arena teardown and a gap-free BYE.

Host ELF/fSELF SHA-256:
`10284d275fa5ec6cdbd194b9682d0b7ab5c813ebe69d86aceffc8a3a200478c5` /
`53548f84c50942e49edeeee0ce2d1283db5fa3286a9c76d71f0070bb1b43488a`;
server ELF/fSELF SHA-256:
`26eb2e10b966918692e378166307bb4ac3b52bc76f2a0dccc4cbe26266e889a5` /
`c3aa4956510f9e638cedaa54178f5fb313a76eb7601336cc39180b22bad9295c`;
transcript/manifest SHA-256:
`69cb7dd0f0fb5dacfde1de0486c183da63b6b5a11643dcfbde2860b6a9bb5a3f` /
`fe73667d6a764d5e5e363afcd2cd75b29232e3d2cc4c498e4ce7c1c6a4435428`.
This remains the rollback point beneath the accepted MainUI gate.

### Dynamic MainUI menu PRX: closed (2026-09-08)

Xash3D PR #14, merged as `9f783ec`, packages pinned upstream MainUI as
`menu.prx` while retaining the dynamic filesystem/server pair. Accepted run
`20260908T094038112Z_PPSA99996_xash3d-engine_0xf1174a815840` proved all 16
base and 12 extended callbacks, engine masks 63 and 15, explicit C++ startup,
activation and 5,127 redraws. Its software framebuffer presented 5,100
non-black frames with final hash `b12dbb47c69ddcb2`. This is the first real UI
module gate, but TV-visible presentation remains scoped to `ref_agc`.

The client startup also retained the server ABI probes. Shutdown unloaded
server, menu and filesystem in order with active counts 2, 1 and 0. The run
ended with exact memory teardown, 73 structured records, 77 raw lines, zero
errors/gaps and a clean BYE. Host ELF/fSELF hashes were
`8bb9e1106db5c6394b0a4bd65c9509f9f9a2db0b91d1e2c14ab0f9d5bc8cf9b8` /
`8bcd0033abb3230841467196adec209146c20b7b4ec3b3a3932b18df7c957680`;
menu ELF/fSELF hashes were
`64099d2824a41580d482435a5c567ef30bcecf9e868463c915b5cf3c5697686d` /
`ec496e4c978dbef7f12305134eb2ba441de2983f551c5ef853e7291c8045aa1b`.
This remains the standalone visible-menu proof beneath the accepted client
gate.

### Dynamic GoldSrc client PRX: closed (2026-09-08)

Xash3D PR #17, merged as `3a30250`, packages the pinned HLSDK client as
`client.prx` while preserving the dynamic filesystem/server/menu bundle.
Accepted run
`20260908T130114060Z_PPSA99996_xash3d-engine_0xfc0996a1effb` loaded four
client mappings and a 48-entry descriptor containing 42 actual GoldSrc
exports. Interface version 7, host callback mask 63, module callback mask 15
and two non-mutating PRX-to-engine smokes all passed.

The gate entered the real `c1a0` workload so the client performed one video
init, 4,916 frame callbacks and 4,907 successful HUD redraws. The software
backend presented 4,800 non-black frames with final hash
`3af6afa7ee47ec93`; native TV presentation remains scoped to `ref_agc`.
Server, menu, client and filesystem then stopped/unloaded with active counts
3, 2, 1 and 0. The bounded run ended with result zero, 89 structured records,
115 raw lines, zero errors/gaps/oversized records and a clean BYE.

Host ELF/fSELF hashes were
`d461cdecc461f0b5472b082b2580b2748f1161e65aa66cba0b0b6c8e26a0d736` /
`9d215b914097a007f5f8b6f69ab8f92481c8341e5090bb5ccc64e81adeb854ef`;
client ELF/fSELF hashes were
`70b54c8628eab934d1cef3d3cb0c2baa177a3a2ddde5e2cf01daddb81e045ba4` /
`9600971dcc1dcf4b6e5d1f90b05b54bc3dabd4cfb50eb8a4a5f2b89a3abd321a`;
transcript/manifest hashes were
`95ce0a78d96f4f12a72097553d47329a98d35bd4ebf3b40e252d6964e0bd2524` /
`3e92238bad943b6dc824b6e4d2001ab4a83e8cbf31f8ab43ea4f393ab129a366`.
The five-file bundle was the rollback point beneath the independent
`ref_agc` gate.

### Dynamic `ref_agc` PRX: closed (2026-09-08)

Xash3D PR #18, merged as `258fbe3`, publishes RefAPI version 18 from
`ref_agc.prx` and binds its live lifecycle/frame callbacks to the accepted
Phase 4 native AGC backend. Engine run
`20260908T191327933Z_PPSA99996_xash3d-engine_0x11059870e2628` started `c1a0`,
bound engine mask 63 and observed 203,420 balanced begin/end callbacks,
203,411 scene callbacks and one new-map callback.

The correlated native stream
`20260908T191327984Z_PPSA99996_ps5-xash3d_0x110598a25cd2f` started 51 ms
later and presented 600 combined Phase 4 frames. Its final GPU hashes were
`a9e62c5188ca6bf5` and `0044418de19349d8`, with 807,578 bright pixels, exact
fence/VideoOut tokens, intact guards, six resources reclaimed and zero
errors. Native teardown closed VideoOut, direct memory and AGC; the engine
then unloaded server, menu, client, renderer and filesystem with active counts
4, 3, 2, 1 and 0. Both logs ended with clean gap-free BYE.

The renderer proof deliberately uses the enriched baked `c1a0e` Phase 4
scene while the engine workload uses `c1a0`. Therefore this gate proves the
RefAPI/module boundary and real native presentation, not yet arbitrary live
engine-entity translation. That bridge, playable traversal, saves/transitions
and release soaks are the Phase 7 boundary. Phase 6 is complete.

### Phase 7 compositor-visible live world (2026-09-09)

Xash3D PR #20, merged as `cdcce91`, closes the presentation boundary left by
PR #19. A serial hardware A/B captured the no-handoff and post-bundle-handoff
forms as byte-identical black frames. The same renderer becomes visible when a
bounded 10 ms scheduler handoff occurs after bundle load and live-camera
fallback initialization, before command/pipeline planning. This location is
pinned by a host contract and reported as `live_camera_settle_ns=10000000`;
the internal firmware mechanism remains an inference, not a documented cause.

Final correlated FW 12.02 runs
`20260909T005027224Z_PPSA99996_xash3d-engine_0x122bd226f4e00` and
`20260909T005027279Z_PPSA99996_ps5-xash3d_0x122bd25b72b53` began 55 ms apart
and matched 1,076 serials. They staged 17,245 vertices, 29,565 indices and
3,695 draws, resolved 164/164 world textures, reclaimed all eight parent
resources and unloaded the five PRXs at active counts 4, 3, 2, 1 and 0 with
zero renderer errors. The synchronized 1920×1080 capture, taken after
`PPSA99996` launch verification, visibly shows the textured tram interior and
has SHA-256
`1ee3578b517bee368f72805d3a9ecd339a5f7de65de462bbefd7a6d7a19c1850`.
This closes live base-texture sampling and compositor presentation. At that
checkpoint, lightmaps, native sky/turbulent semantics, entities, viewmodel and
2D/UI were still open.

### Phase 7 live engine lightmaps (2026-09-09)

Xash3D PR #21, merged as `4f9d38d`, closes live lightmap construction,
residency, native pipeline binding and compositor-visible sampling. The
producer combines active GoldSrc lightstyle planes through the engine gamma
table, packs a deterministic owned atlas with duplicated one-texel gutters and
publishes normalized UVs. The consumer stores the RGBA8 atlas in the existing
32 MiB direct-memory world arena and reuses the Phase 2–4 native opaque and
alpha-test lightmap pipelines; no OpenGL emulation layer was introduced.

Final correlated FW 12.02 runs
`20260909T022301539Z_PPSA99996_xash3d-engine_0x127ca54ee550a` and
`20260909T022301592Z_PPSA99996_ps5-xash3d_0x127ca581d165f` began 53 ms apart
and passed 1,075 matched frames. All 3,695 draws were lightmapped. The
1024x256 atlas used 1,048,576 bytes, contained 186,051 nonzero texels and
produced common engine/renderer frame hash `a3219a480a7a1c41`. The run
reclaimed all eight parent allocations, recorded zero renderer errors and
unloaded the five PRXs in order to zero. The launch-verified 1920x1080 CLI
Remote Play capture has SHA-256
`2b8bd9ea8dd5345463f7bd9363ee79df36ae77af76cc635c54b8859699cdbfd7`.

Black images taken before this run were rejected after a PS home screenshot
proved that the CLI Chiaki stream itself was stale; they are not renderer
evidence. A separately verified live-stream no-lightmap control was visibly
unlit. At that checkpoint native sky/turbulent semantics, entities, viewmodel
and 2D/UI remained open.

### Phase 7 live sky and turbulent surfaces (2026-09-09)

Xash3D PR #22, merged as `77c742a`, closes native special-surface extraction,
transport and AGC presentation. The producer classifies sky and turbulent
surfaces separately from ordinary opaque/alpha-test draws, publishes all six
engine sky texture handles plus camera/time state and preserves raw GoldSrc
turbulent coordinates. The consumer builds a camera-centred six-draw skybox
and a dedicated classic sine-warp pipeline; neither path emulates OpenGL.

The first hardware iteration proved that the packaged 4,823-entry index and
all `gfx/env` assets were intact, but a synthetic 8,224-byte directory stream
could not fit in the filesystem PRX's private libc heap. Runtime directory
streams now use the filesystem engine pool with per-allocation ownership flags.
The renderer's CPU texture/world stores likewise use a dedicated engine pool,
lifting the earlier 360-texture ceiling while preserving exact teardown.

Final correlated FW 12.02 runs
`20260909T044902002Z_PPSA99996_xash3d-engine_0x12fc201d8f826` and
`20260909T044902056Z_PPSA99996_ps5-xash3d_0x12fc2056055d0` began 54 ms apart
and passed the strict paired validator across 1,616 frames. Hardware loaded all
six `xen9` faces. The live world contained 14,981 vertices, 24,303 indices and
3,440 draws: 3,282 lightmapped, 158 sky/1,197 source indices and 35
turbulent/312 indices. Fourteen periodic samples retained six skybox draws/36
indices with geometry hash `e7fd75bb4ee4188d`, texture hash
`e97b5c8ba780c902` and engine time advancing from 0 to 26,942 ms. GPU texture
sync completed 478 creates with zero errors; eight parent resources were
reclaimed, engine live bytes returned to zero and the five PRXs unloaded in
exact order. At that checkpoint entities, viewmodel and 2D/UI remained open;
the following gate closes the 2D part of that boundary.

### Phase 7 live 2D composition (2026-09-09)

Xash3D PR #23, merged as `0bdcbfb`, closes native live console/HUD/font/fill
translation. The consumer executes `R_Set2DMode`, `R_DrawStretchPic` and
`FillRGBA` in exact producer order after world and special-surface passes,
copies both color APIs, resolves live texture handles, and emits orthographic
transient vertices, indices, constants and descriptor tables. Only consecutive
commands with equal texture and blend identity batch together. Alpha, additive
and opaque paths use the proven `screen_2d` pipeline; fill uses one transient
white texel. No OpenGL emulation layer is present. A maximum-capacity host test
fits all 4,096 producer slots and 4,095 alternating drawable batches in either
1 MiB transient slot.

Accepted correlated runs
`20260909T060525224Z_PPSA99996_xash3d-engine_0x133ed1bbb4d07` and
`20260909T060525280Z_PPSA99996_ps5-xash3d_0x133ed1efb02b5` began 56 ms apart
and passed 1,044 matched frames. Exactly 333 frames carried live 2D draws:
61,316 quads became 367,896 indices and 610 ordered batches, with peak three
batches per frame. The producer emitted 63,395 commands, including 2,079 mode
commands; all textures resolved and aggregate command hash was
`177a07fa2fd9e5b1`. Both framebuffer slots hashed `49b1297de5cef0a0`, the
aggregate frame hash was `a3219a480a7a1c41`, eight resources retired, guards
remained intact, all five PRXs unloaded exactly and both streams ended clean
and gap-free.

The 20-second 1080p CLI Remote Play recording has SHA-256
`5bcdd2772f5d3d29baae61a659ca19af9c079061f69b79f58dc479e70dce6aa0`;
its accepted frame visibly shows the translucent Xash console, engine text and
localized overlay over the live tram interior. The engine/ref transcript
hashes are respectively
`f637d76cc88698869bd2fa9ba8234a2bcd5a8c6d0ac06c090a836e370423baaf`
and `5eab062c4e38b56208754d7804ab94a9610658b5c79c58ee77bd675b2f3388c6`.
This closes live 2D composition. The following gate closes native MainUI
presentation; entities and viewmodel remain the next translation boundary.

### Phase 7 native MainUI and map transition (2026-09-09)

Xash3D PR #24, merged as `a975b86`, boots the complete client/ref_agc stack
without `+map`, presents MainUI through live native AGC 2D and, after five
seconds, queues `map c1a0` through the engine command buffer. Strict evidence
requires positive pre-map frames/quads/draws, serial order menu-before-map, a
unique raw transition before `Spawn Server`, exact completion/teardown and
independent video of both states. The deploy helper also now disables ftpsrv's
SELF transformation and verifies exact remote SHA-256 for every staged file.

Accepted paired runs
`20260909T065237749Z_PPSA99996_xash3d-engine_0x1368098fcc1b8` and
`20260909T065237800Z_PPSA99996_ps5-xash3d_0x136809c13ba99` began 52 ms apart
and passed 1,339 frames. MainUI started at serial 1. The map first appeared at
serial 224 after 223 menu frames, 94,918 quads and 27,929 draws. The paired
validator retained 3,695 lightmapped world draws, 3,989,406 bright pixels,
both buffers at `49b1297de5cef0a0`, eight exact reclaims, zero errors and exact
five-PRX teardown. The accepted 35-second CLI recording
(`bfff803bbd69d91e067220ff178b3771720125b17f45a151b20a5370662c22c9`)
visibly shows MainUI at 23 seconds and `c1a0` at 25 seconds after a non-black
Home preflight. This closes native menu presentation and the in-process map
transition; entities, viewmodel, camera comparison, gameplay, performance,
soaks and release remain.

## Live NPC and visual corrections checkpoint (2026-09-09)

Xash3D PR #25 is merged as `3167fc60c8c038507f088a8194b25cd8473590e0`;
the lab pins this exact commit. Port host contracts and publication checks pass.

The port's `docs/PHASE7_BASELINE_REGRESSION.md` records the complete sequence of
accepted and failed runs: coherent menu/map deployment, brush transforms,
animated Studio NPCs, runtime ScePad, camera-relative black occlusion corrected
by color-only background depth, Studio mip/trilinear minification and restored
MOVETYPE_STEP movement interpolation. Operator confirms distant visibility,
reduced shimmer and fluid walking. None of this closes all of Phase 7.

The live GPU texture budget is now 80 MiB; measured residency is 67,717,120
bytes. The first 64-MiB mip candidate correctly parked on exhaustion and remains
documented as a failure. Interactive 30-minute runs were externally closed for
iteration. The final three-minute natural-exit run now closes resource teardown:
engine `20260909T113637960Z_PPSA99996_xash3d-engine_0x1460005826042` and renderer
`20260909T113638013Z_PPSA99996_ps5-xash3d_0x14600097ae176` passed 10,997 frames,
nine exact reclaims, zero errors, all five PRX unloads and empty engine memory.
Post-run status confirmed no BigApp and four healthy services. Renderer PRX
SHA-256: `192ec1ffd401720ecc6f108c58f5844b00c146a92c9ddb3ca87f856a4bd4b9d2`.
The paired validator checks live lightmaps/2D/menu/brush/Studio; this scene has
no sky/turbulent draws and does not supersede their earlier dedicated proof.
The port document preserves full artifact/log hashes and rejected iterations.

Known next work: full Studio lighting/chrome/controllers/sequence transitions,
viewmodel, chapter-title blend-state propagation (black rectangle), integrated
game audio (`XASH_AUDIO=0` in these graphics runs), gameplay, performance and
soaks. Dedicated Phase 5 audio proof is not proof of an audible live client.
QA uses direct operator observations; no Remote Play/capture was required.

## Phase 7 texture-memory policy (2026-09-09)

Accepted and merged: Xash3D PR #26, `70ebea8d40e24d6642034abeb3721b251e00df17`.
The lab pins this exact commit; memory acceptance was recorded in revision 43.

The fixed 80-MiB texture test budget is replaced by measured, configurable
capacity. XASH_TEXTURE_MIB selects explicit MiB (zero means automatic),
XASH_TEXTURE_RESERVE_MIB defaults to 512 MiB outside the renderer heap, and
XASH_TEXTURE_AUTO_PERCENT defaults to 10% of eligible capacity. These are
configurable policies, not PS5 hardware limits. A single returned free block
is used conservatively; it is not mislabeled as total free memory.

The explicit 256-MiB run passed 1,999 frames, nine reclaims and exact teardown.
Automatic runs `20260909T122547724Z` / `20260909T122547781Z` pass 10,994 frames,
nine exact reclaims, zero errors, five PRX unloads and clean BYEs. Selected
texture capacity is 1,204,158,464 bytes, with 67,717,120 bytes of texture data
resident inside that physically allocated arena. The independent paired
validator and post-run status pass. This is startup sizing, not sparse
allocation, runtime growth, eviction or performance-budget acceptance.
Host tests and ASan/UBSan cover mapping-failure rollback, retained ownership
when release fails, and create/replacement exhaustion without corruption.
The paired validator independently recomputes budget arithmetic and matches
the actual cache allocation. Full identities and automatic-run evidence live
in the port's docs/PHASE7_TEXTURE_MEMORY_POLICY.md.

Next gates remain ordered: chapter-title/HUD blending, real game audio,
Studio/viewmodel fidelity, then valve_hd mounting and resource validation.
None of these or the rest of Phase 7 is closed by the memory gate.

## Phase 7 HUD/font correction — pending hardware QA (2026-09-09)

Plan revision 44 records draft Xash3D PR #27 at
`f99929d69d345be7028afc10a71087cf870105ff`. Requested render modes now reach
the compositor, with independent alpha test and correct FillRGBA/current-color
side effects. The eight 2D pipelines preserve the 96 existing 3D permutations;
a dedicated screen shader discards only final alpha zero. Full host tests,
ASan/UBSan compositor coverage, gfx1013 shader validation, the native
client/AGC build and both GitHub host-contracts jobs pass.

Renderer ELF SHA-256:
`88ca05fbf445e532fa91e92c5d420b43dc9b90fbb73a0cd07fe0821f669e66b4`.
Renderer PRX SHA-256:
`23672468d2920dc78096a7224744d254be1a82c590038b974252084ba9864ad9`.
Exact compiled pixel shader bytes were located in the ELF, rather than
assuming the source change reached the artifact.

No deployment, launch, operator visual acceptance or paired teardown evidence
exists for this HUD candidate yet. Keep PR #27 in draft and the lab submodule
pinned to accepted `70ebea8`. Required next: confirm operator availability,
canonical transactional deployment and paired console run; verify MainUI,
chapter title without a black rectangle, readable fonts and fades, plus
resource ownership/teardown. An ordinary title run does not automatically
cover every font mode or multiplicative fade. The port's
`docs/PHASE7_HUD_FONT_BLEND.md` contains the QA checklist and build evidence.
Only after acceptance and integration proceed to real game audio, then Studio
fidelity and HD-pack validation. This does not close the remainder of Phase 7.

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
