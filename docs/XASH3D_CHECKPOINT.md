# Xash3D on PS5 checkpoint

Reconciled: 2026-09-06. Hardware boundary: one PS5 on firmware 12.02.

## Current position

| Phase | State | Proof / boundary |
| --- | --- | --- |
| 0 — Close the ledger | Complete | Public renderer, protected `main`, CI, reproducible GFX1013 compiler and evidence rules. |
| 1 — BSP viewer with noclip | Complete | `c1a0`, 3,611 draws, 164 base textures plus lightmap, physical DualSense movement and a clean 60,000-frame textured gate. |
| 2 — Resource foundation | Complete | Fence-retired pool, two-slot transient ring, V#/T#/S#, per-frame constants, two pipeline permutations, cache contract and a clean 60,000-frame gate. |
| 3 — Texture path | Complete, 6 gates closed | Dynamic lightmap, deterministic mips/filtering, alpha test, sky, exact accounting and the final 60,000-frame soak are hardware-proven. |
| 4 — GoldSrc render states | Next | Blend/additive permutations, 2D, sprites, particles, studio/brush entities and culling. |
| 5 — Platform layer | Sized, later/parallel | ScePad, AudioOut, filesystem, direct-memory engine allocator, time/threads and three measured libc shims. |
| 6 — Engine integration | Later | Modular Xash3D boot with `ref_agc`, menu, client, server and filesystem PRX modules. |
| 7 — Playable and release | Later | Gameplay/performance and level-transition soaks, clean reproducible release. |

The Phase 1/2 implementation was merged through
`mpereiraesaa/ps5-agc-gears#8` as commit `642d348`. The complete Phase 3 texture
path was merged through `mpereiraesaa/ps5-agc-gears#9` as commit `cbff264` after
all host and security checks passed. On 2026-09-06 the port moved to its own
repository, `mpereiraesaa/ps5-xash3d`, forked from `cbff264` with full history;
the laboratory submodule `projects/ps5-xash3d` pins it and Phase 4 lands there.
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

## Parallel work that is now de-risked

The reproducible symbol probes show that libc/C++ is not the port blocker:

- the client has three real SDK gaps: `__assert`, `getpwuid` and `dladdr`;
- `mainui`, client hlsdk and server hlsdk need no additional C++ runtime;
- application PRX load, relocated export descriptors, calls and unload are
  already hardware-proven.

Therefore Phase 5 can prototype the three tiny C shims and a minimal
`platform/ps5` while Phase 3/4 mature, but it must not bypass the renderer gates
or start full engine integration prematurely.

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
