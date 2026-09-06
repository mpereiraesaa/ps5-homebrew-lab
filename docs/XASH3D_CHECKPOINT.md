# Xash3D on PS5 checkpoint

Reconciled: 2026-09-06. Hardware boundary: one PS5 on firmware 12.02.

## Current position

| Phase | State | Proof / boundary |
| --- | --- | --- |
| 0 — Close the ledger | Complete | Public renderer, protected `main`, CI, reproducible GFX1013 compiler and evidence rules. |
| 1 — BSP viewer with noclip | Complete | `c1a0`, 3,611 draws, 164 base textures plus lightmap, physical DualSense movement and a clean 60,000-frame textured gate. |
| 2 — Resource foundation | Complete | Fence-retired pool, two-slot transient ring, V#/T#/S#, per-frame constants, two pipeline permutations, cache contract and a clean 60,000-frame gate. |
| 3 — Texture path | Active, 4 gates closed | Dynamic lightmap, deterministic mips/filtering, alpha test and a separate sky pass are hardware-proven; consolidated texture-budget telemetry is next. |
| 4 — GoldSrc render states | Later | Blend/additive/alpha-test permutations, 2D, sprites, particles, studio/brush entities and culling. |
| 5 — Platform layer | Sized, later/parallel | ScePad, AudioOut, filesystem, direct-memory engine allocator, time/threads and three measured libc shims. |
| 6 — Engine integration | Later | Modular Xash3D boot with `ref_agc`, menu, client, server and filesystem PRX modules. |
| 7 — Playable and release | Later | Gameplay/performance and level-transition soaks, clean reproducible release. |

The Phase 1/2 implementation was merged through
`mpereiraesaa/ps5-agc-gears#8` as commit `642d348` after all host and security
checks passed. The laboratory submodule pins that commit. Phase 3 can now branch
from the protected public `main` without a cross-PR dependency.

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
   telemetry — next.
4. Finish with a 60,000-frame Phase 3 soak before declaring the phase complete.

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
normal test. When the owner takes the physical DualSense, the Remote Play
session disconnects but the stream window remains black behind a
`Session has quit` dialog. Clicking `OK` closes only that stream window; the
main Chiaki client remains available to restart streaming from the existing
entry. The helper also supports direct console-mode startup, so the discovery
client window is not required. It works around Chiaki 2.1.1's second-entry CLI
bug with a private temporary copy of the existing PS5 registration; no pairing,
re-registration or credential logging occurs. Automation must not assume focus
or synthesize movement.
