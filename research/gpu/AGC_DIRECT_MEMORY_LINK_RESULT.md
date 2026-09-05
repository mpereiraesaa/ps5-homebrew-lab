# AGC CreateShader + LinkShaders in direct memory — FW 12.02

On 2026-09-04 `PPSA99998` reproduced the complete CPU-side shader transform
inside a single 64 KiB direct-memory arena. Allocation and mapping used the
same class as the authorized ProsperoTV shader arena: alignment `0x4000`, type
`0x0c`, protection `0x33`, mapping flags zero.

Both constructors and LinkShaders returned zero. CX and UC hashes were exactly
equal across the isolated host oracle, the prior static-storage console run,
and this direct-memory run. External canaries remained intact; constructed
headers and code were unchanged by LinkShaders.

Before teardown the complete arena was overwritten with zero and verified.
AGC unload, direct-memory unmap and physical release all returned zero. The app
reached its safe marker, was closed by exact title, left no BigApp, and all four
services passed two post-close health observations.

This establishes CPU accessibility and the platform direct-memory allocation
contract. It deliberately does not claim that the GPU fetched these bytes:
proving actual GPU visibility requires a later bounded submit/fence experiment.

## Arena contract

| Region | Offset | Size/alignment |
|---|---:|---:|
| Pre-raster header | `0x0000` | 376 / 8 |
| Pixel header | `0x1000` | 384 / 8 |
| Pixel code | `0x2000` | 2304 / `0x100` |
| Pre-raster code | `0x3700` | 736 / `0x100` |
| Guarded CX payload | `0x5000` | `0x110` / 8 |
| Guarded UC payload | `0x6000` | `0x18` / 8 |
| Header snapshots | `0x7000`, `0x8000` | 376, 384 / 8 |

`test_agc_direct_arena.py` covers the selected layout plus rejection of
overlap, out-of-bounds regions, code misalignment and invalid arena
granularity. The existing LinkShaders gate adds 18 contract tests and 17
negative planner cases.

## Postmortem

The first local build correctly stopped in `verify.py` because its required
strings still described the previous static probe. No console contact or
deployment occurred. The verifier was updated to require the direct-memory
lifecycle markers and memory contract. The subsequent build and only console
run completed cleanly; there was no runtime failure.

No shader bytes, register values, dumps or proprietary fragments are present
in the captured evidence.
