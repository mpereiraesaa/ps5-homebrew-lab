# Offline research for PS5 AGC Gears

Scope: clean-room/public evidence only; no console contact. Updated 2026-09-05.

## Confirmed import boundary

The proven Stage E import set is already sufficient for an animated triangle
and Plasma. Its AGC core is init/defaults, shader create/link, native CX/UC/SH
indirect builders, `DrawIndexAuto`, wait-for-rendering, SetFlip and SubmitDcb.
Memory, VideoOut and equeue lifecycle are already complete.

No new import is required merely to change a direct shader user register every
frame. `sceAgcCbSetShRegisterRangeDirect` remains a convenience candidate for
resource descriptors, not a Plasma prerequisite. An indexed-draw builder is an
optimization for compact meshes, not a Gears prerequisite because indices can
be expanded before upload.

## Compiler-derived user-data contracts

Two independently authored fixtures compile successfully with the patched
public LLPC toolchain using `-gfxip=10.1.3`. Both ELFs carry AMDGPU flags `0x42`,
contain non-empty GS/PS symbols and have no relocations.

### Plasma

`plasma_push_constant.pipe` declares four pixel-stage floats: time, inverse
width, inverse height and phase. PAL metadata maps them directly:

```text
PS user_data_reg_map[0..4] = InternalTablePtr, 0, 1, 2, 3
PS user_sgprs = 5
```

Therefore Plasma requires four dynamic SH user-register values but no constant
buffer descriptor, descriptor table or new NID.

### Cube vertex path

`cube_vertex_input.pipe` declares a 4×4 MVP push constant plus interleaved
position and normal attributes (24-byte stride). PAL metadata maps:

```text
GS user_data_reg_map[1..16] = 0..15          # direct MVP words
GS user_data_reg_map[17] = VertexBufferTable # internal mapping 0x1000000f
GS user_sgprs = 20
```

The public compiler also closes the runtime side more tightly than the mapping
alone suggests. Disassembly contains one 16-byte scalar SRD load from binding
zero, followed by typed vertex fetches covering position and normal. The two
attributes do not require two buffers: they share one interleaved buffer and one
SRD with a 24-byte stride.

Public PAL source defines that GFX10 SRD completely as four DWORDs:

```text
DW0 = GPU address low 32 bits
DW1 = GPU address bits 47:32 | (stride << 16)
DW2 = byte range / stride                  # structured vertex count
DW3 = 0x11014fac                           # XYZW, 32_UINT, resource-level, OOB
```

The typed formats used by the two fetch instructions are encoded in ISA, so the
generic SRD format is not the declaration of `vec3`; for this public PAL path it
is `BUF_FMT_32_UINT`. The table must be 16-byte aligned. For our current fixture
only table entry zero is consumed, even though two attributes are declared.

The pointer represented by `VertexBufferTable` is a 32-bit GPU VA according to
the compiler ABI. Its exact SH user-register slot is already supplied by the
compiler metadata (`GS user_data_reg_map[17]`), so the existing SH-indirect
builder can bind it without adding a new import.

### Lit Gears path

The Cube fixture proved vertex fetch but left normals in object space. A third
clean-room fixture now covers the actual presentation demo: 16 MVP words, a
four-word unit quaternion and a four-word material color are all direct
pre-raster user data. The quaternion rotates each normal without requiring a
second matrix or uniform buffer. The compiler reports 28 user SGPRs (below its
reported limit of 106), retains the same one-SRD interleaved vertex path, and
produces 384-byte GS plus 160-byte PS entry points with no relocations.

Consequently three animated gears require only three draws with new direct
MVP/quaternion/material words per draw. They do not require a general constant
buffer system, a texture/sampler path or another import. CPU mesh generation
can expand indices initially and upload one immutable position/normal stream.

The exact update range is compact SH offset `0x8d`: user-data slot zero remains
the compiler's internal-table pointer, slots 1–24 contain the parameters, and
slot 25 contains the 32-bit vertex-buffer-table pointer. The firmware direct
range builder copies those 25 values inline into 27 command DWORDs; followed by
the three-DWORD `DrawIndexAuto`, three gears cost 90 DWORDs. This deliberately
avoids a mutable indirect-table hazard: all three per-object states are frozen
inside the DCB before submit and remain valid until the terminal fence.

## Optional imports and NIDs

The SDK's deterministic NID generator and two public compatibility projects
agree on the following optional names:

| Function | NID | Need for first Gears |
|---|---|---|
| `sceAgcCbSetShRegisterRangeDirect` | `n2fD4A+pb+g` | convenience only |
| `sceAgcDcbDrawIndex` | `q88lQ+GP5Yk` | optional compact index path |
| `sceAgcDcbSetIndexBuffer` | `l4fM9K-Lyks` | optional bound-index path |
| `sceAgcDcbSetIndexCount` | `8N2tmT3jmC8` | optional bound-index path |
| `sceAgcDcbDrawIndexOffset` | `B+aG9DUnTKA` | optional bound-index path |
| `sceAgcDcbAcquireMem` | `57labkp+rSQ` | candidate scoped cache/DB barrier |
| `sceAgcCbReleaseMem` | `wr23dPKyWc0` | terminal/cache release and label write |
| `sceAgcDcbEventWrite` | `aJf+j5yntiU` | partial-flush/event primitive |
| `sceAgcDcbWriteData` | `i1jyy49AjXU` | command-side initialization/update |
| `sceAgcDcbWaitRegMem` | `VmW0Tdpy420` | GPU-side label/register wait |
| `sceAgcSuspendPoint` | `h9z6+0hEydk` | not needed by proven fence path |
| `sceVideoOutGetFlipStatus` | `SbU3dwp80lQ` | optional pacing telemetry |
| `sceVideoOutWaitVblank` | `j6RaAUlaLv0` | optional blocking pacer |

The shortest clean-room route remains expanded non-indexed geometry with the
already proven `DrawIndexAuto`. The optional indexed ABI is recorded for a
later memory optimization, not put on the critical path.

The firmware-12.02 implementation closes that optional ABI as
`(writer, index_count, GPU_index_address, modifier)`. It reserves exactly six
DWORDs, advances the writer by 24 bytes, stores the 64-bit index address and
both the normalized and original count fields, and returns the packet start;
allocation failure returns null. Only selected modifier bits are folded into
the final control word, so callers must use a known compiler/SDK-produced
modifier rather than inventing flags. Kyty exposes only `DrawIndexAuto` for
Gen5 and therefore corroborates the export family but not this packet ABI.
`verify_agc_indexed_draw_contract.py` locks these sanitized facts to the
authorized local image without copying function bytes into documentation.

The authorized local `libSceAgc` image independently resolves the draw/direct
SH exports and the five synchronization primitives listed above. Ghidra
confirms the
direct range ABI as `(writer, offset, values, count)`, reserves `count + 2`
DWORDs, emits one `SET_SH_REG` packet, copies `count` values when non-null, and
returns the packet start. This firmware implementation does **not** prepend the
extra inert marker modeled by some compatibility projects. That difference is
irrelevant to our caller but is important when estimating command capacity.

`verify_agc_optional_exports.py` anchors the private module's dynamic-symbol
map without exporting module bytes. The public project receives only the
function names/NIDs and behavioral summary.

## Reproducible gate

Run:

```sh
python3 research/gpu/tools/verify_gears_offline_readiness.py
```

That aggregate gate runs the individual checks below:

```sh
python3 research/gpu/tools/verify_gears_shader_contracts.py
python3 research/gpu/tools/verify_gears_runtime_contracts.py
python3 research/gpu/tools/verify_agc_optional_exports.py
python3 research/gpu/tools/verify_agc_indexed_draw_contract.py
python3 research/gpu/tools/verify_depth_register_map.py
python3 research/gpu/tools/verify_gfx1013_addrlib_contract.py
python3 research/gpu/tools/verify_gears_depth_bootstrap.py
python3 research/gpu/tools/verify_gears_predraw_clear_contract.py
python3 research/gpu/tools/verify_gears_multidraw_contract.py
```

The gates recompile both fixtures in temporary directories and assert target,
relocations, symbols, user-data mappings, one-SRD ISA shape, PAL SRD encoding
and deterministic optional NIDs. Generated ELFs are not publication inputs.

## Depth target: register identity closed

The 16 `{id, value}` pairs in the authorized local depth descriptor are not an
opaque private namespace. Every ID equals the low context-space offset of one
public GFX10 DB register (`absolute register - 0xa000`):

```text
02 DB_DEPTH_VIEW             10 DB_Z_INFO
05 DB_HTILE_DATA_BASE        11 DB_STENCIL_INFO
07 DB_DEPTH_SIZE_XY          12 DB_Z_READ_BASE
0a DB_STENCIL_CLEAR          13 DB_STENCIL_READ_BASE
0b DB_DEPTH_CLEAR            14 DB_Z_WRITE_BASE
1a DB_Z_READ_BASE_HI         15 DB_STENCIL_WRITE_BASE
1b DB_STENCIL_READ_BASE_HI   1c DB_Z_WRITE_BASE_HI
1d DB_STENCIL_WRITE_BASE_HI  1e DB_HTILE_DATA_BASE_HI
```

This exact 16-of-16 match is substantially stronger than transferring names by
proximity. It also explains the five split 48-bit addresses already recovered:
Z read/write, stencil read/write and HTILE. `DB_DEPTH_SIZE_XY` independently
matches the observed two 14-bit `N-1` fields, and IDs `0x0a/0x0b` identify the
clear values without ambiguity.

Public PAL programs additional view-owned state outside this 16-pair block
(`DB_RENDER_CONTROL`, overrides, cache policy, polygon offset and HTILE
surface). AGC's defaults/state builders may own those separately; therefore a
standalone 16-pair write is a target-binding contract, not yet a complete safe
depth initialization sequence.

The safest initial depth mode is uncompressed/no-HTILE: public PAL explicitly
sets `TILE_SURFACE_ENABLE=0`, disables tile stencil, and disables depth/stencil
compression in that mode. But the physical surface swizzle and exact AGC state
builder inputs remain to be derived before runtime use.

## GFX1013 AddrLib boundary

Mesa merge commit `44bed00b8bbcb1825e2c920cf1a828efdc72b1f1`
(`amd/addrlib: Add more GFX1013 GPUs`) changes one semantic boundary: the
accepted external-revision interval expands from `0x84..0x85` to
`0x82..0x85`. It does not introduce a PS5-specific shader upload, allocation
algorithm or depth equation.

Current Mesa identifies those revisions as `GFX1013` inside `FAMILY_NV` and
routes them through GFX10 AddrLib. The family-conversion code contains no
explicit GFX1013 special case and does not enable RB+ for it. Consequently the
variable-block depth mode is unavailable and AddrLib's valid fixed fallback is
`ADDR_SW_64KB_Z_X`.

That classification is necessary but not sufficient to calculate bytes. Mesa
passes three independent items into `AddrCreate`: family, external revision and
the kernel-reported `GB_ADDR_CONFIG`. GFX10 AddrLib consumes at least its pipe
count, pipe-interleave size and maximum-compressed-fragment fields; its pattern
tables and metadata equations vary with topology. Therefore neither
"GFX1013", the MR revision interval, nor the common Navi10 analogy proves the
PS5 value. Prosper's current default of 16 pipes is explicitly documented by
that project as medium-confidence analogy, not measured PS5 topology.

There is one useful topology-independent subset. For a single-mip,
single-sample 2D D32 main plane, public AddrLib derives a 128×128-pixel 64 KiB
block from only block size, bpp and samples. It rounds 1920×1080 to a
1920×1152 footprint: exactly `0x870000` bytes aligned to 64 KiB. The pipe count
changes the permutation inside blocks, not this allocation size. Repeating the
same 32-bit clear word across every texel is also invariant under any such
permutation; an initial `1.0f` clear is therefore a whole-allocation fill with
`0x3f800000`.

The refined fail-closed boundary is: this is enough to reserve and uniformly
initialize the uncompressed main plane, but not to perform CPU
coordinate-addressing, construct HTILE, or claim a general tiler. Those still
require the actual topology value. The DB bind/state sequence and visibility
barrier must also be proven independently before runtime use.

### No-HTILE register plan and clear ordering

Public register definitions produce a reproducible depth-only candidate for
1920×1080 D32, one sample, `64KB_Z_X`:

```text
DB_DEPTH_VIEW       = 00000000
DB_DEPTH_SIZE_XY    = 0437077f
DB_STENCIL_CLEAR    = 00000000
DB_DEPTH_CLEAR      = 3f800000
DB_Z_INFO           = 00000183
DB_STENCIL_INFO     = 20000180
DB_RENDER_CONTROL   = 00000060
DB_DEPTH_CONTROL    = 000000b6
```

The last value enables depth read/write with `LESS_EQUAL`; stencil remains
disabled. `DB_RENDER_CONTROL` is deliberately outside the captured 16-pair
target block and disables both compression paths. This proves why replaying
only the 16 pairs would be incomplete. Base-address words remain runtime
relocations in 256-byte units; HTILE and stencil bases stay zero.

The authorized attachment transition proves a post-draw color+depth chain:
partial flush, CB/DB metadata events, terminal cache event, release label,
exact wait and ACQUIRE of the label. It proves completion ordering, not the
visibility of a newly written depth allocation before the first draw: that
ACQUIRE covers the 32-byte private label, not the depth surface.

The offline choice is now explicit: clear the fresh D32 allocation with one
immediate-data `DMA_DATA` packet containing `0x3f800000`, targeting all
`0x870000` bytes through L2, leaving write-confirm enabled and setting
`cp_sync=1`. The allocation fits under the packet's 26-bit byte-count limit.
Public PAL defines `sync` as halting subsequent processing on the selected
engine until the DMA completes, and RADV additionally states that the final
sync packet makes the 3D engine wait and that GFX9+ CP DMA through L2 is
coherent. Our Stage D already proved the same AGC builder mode over a larger
surface, including full target comparison and terminal fence.

For a fresh allocation with no prior DB owner, this removes the need to invent
a depth-range `ACQUIRE_MEM` before the first draw. It does not claim that depth
consumption has run on PS5: the first Cube-depth execution must still validate
the resulting occlusion and fence. Reuse after a prior DB draw remains governed
by the proven post-draw DB completion chain and per-frame ownership; it must not
be reduced to the label-only ACQUIRE.

### Corrected Stage G view constructor

The former inline 18-pair experiment was incomplete and contained one false
assumption: it pointed all stencil read/write bases at the depth allocation even
though stencil format and testing were disabled. It also omitted the cache,
override, HTILE-surface, polygon-offset and coherency registers written by PAL.

`stage_g_depth_state.c` now builds an independently testable 22-pair plan in
PAL's public GFX10 binding order. The first 21 pairs are the complete no-HTILE
D32 view, including `DB_Z_INFO`; the last pair is the separate
`DB_DEPTH_CONTROL=0xb6` state. Stencil and HTILE addresses are zero, depth
read/write addresses contain only the aligned runtime VA, polygon offset is
the public D32 float value `0x1e9`, and `DB_RENDER_OVERRIDE=0x2a` forces HiZ and
both HiS paths off.

The runtime default is intentionally 21 pairs. Thus the next hardware gate
binds a complete DSV after the synchronized DMA clear but leaves depth testing
disabled. Only after that transaction reaches the GPU fence and exact VideoOut
event will a one-variable successor use all 22 pairs and validate actual depth
consumption. Run `make agc-stage-g-check` before either build.

## Remaining offline questions

1. Exact meaning and safe producer of the optional indexed-draw modifier.
2. Depth per-coordinate addressing and HTILE (not required by the selected
   uniform-clear/no-HTILE bootstrap).
3. Hardware validation of Cube depth consumption and long-duration timing.

## Frame pacing and ownership

The renderer must keep two independent completions separate:

1. the terminal GPU fence reaches zero before command/shader/vertex memory can
   be reused;
2. the VideoOut flip event must carry the exact submitted positive 48-bit
   `flipArg` before that display buffer can be reused.

This ordering is already enforced by the Stage B completion state machine and
its verifier. It is sufficient for correctness and therefore Gears needs no new
pacing import. Each frame should use a monotonically increasing `flipArg`, keep
the last owner token per backbuffer, wait for both completion domains with a
deadline, and only then reset the corresponding per-frame arena.

`sceVideoOutWaitVblank` is a CPU scheduling pacer, not an ownership primitive;
returning immediately would create an unbounded loop. `GetFlipStatus` is useful
telemetry/fallback and reports the completed `flipArg`, but polling it is not
stronger than the exact event already exercised. Neither call may replace the
terminal GPU fence. For the first animation loop, retain the exact event path
and calculate animation time from a monotonic clock; add WaitVblank only if
profiling shows the event arrives too early to regulate CPU production.

Ghidra investigation will target only these narrow contracts and will publish
sanitized ABI facts, never proprietary bytes or substantial decompilation.

## Stage I offline integration

`stage_i_main.cpp` now links the clean-room frame tracker, animation, draw
composer, telemetry and frame runner into the private native harness. It
prebuilds one color-target pipeline per VideoOut buffer and runs 300 sequential
frames. Each frame waits until its buffer is renderable, clears color and the
D32 surface through synchronized L2 DMA, binds all 22 no-HTILE depth pairs,
emits three independently transformed lit draws, appends SetFlip plus release
fence, and waits for the fence and exact positive 48-bit token.

The SetFlip builder lives inside the runner's submit callback: the ownership
tracker therefore enters `SUBMITTED` before the first irreversible builder
operation. Any failure from that point returns post-submit retention. A
64-byte depth-tail guard and the existing color guards are checked only after
the final exact completion. Telemetry remains aggregate and is streamed as
structured `ps5log/1` records to the development PC.

This is compile-time evidence only. The signed artifact must not be deployed
before the independent Stage G/21, Stage G/22 and static Stage H hardware gates
have completed successfully.
