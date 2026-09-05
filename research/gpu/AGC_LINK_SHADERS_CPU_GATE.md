# `sceAgcLinkShaders` static gate — PS5 FW 12.02

## Result

The host-only gate reconstructs the six-argument ABI, pins the implementation
at NID `MqAdbRMdNz4`, validates both linked-output sizes, and selects one real
pre-raster/pixel pair from the local authorized ProsperoTV corpus. No console
call, process write, command-buffer emission, or GPU submission is part of this
gate.

The selected pair is not inferred from `type` alone. Three independent facts
agree:

1. one explicit source call passes the two constructed shader objects together
   to `sceAgcLinkShaders` with primitive type 6;
2. the pre-raster header has one output semantic key, `0x0f`, and the pixel
   header has one input semantic key, also `0x0f`;
3. both headers declare the same target value. The private assets remain local;
   the proof records only hashes, counts, roles and semantic keys.

The two owned-game import inventories were also checked explicitly. Neither has
a direct reference to `libSceAgc+0x103f0`; they use `CreateShader`, fused-shader
and split state-building paths instead. This is useful negative evidence, not a
commercial-game pair claim. The selected pair and its positive same-callsite
correlation come solely from the local ProsperoTV corpus.

The register/resource audit also bounds both CX and SH arrays and all five
user-resource groups. The selected stages have zero cross-stage register-ID
overlap. Their resource-group overlap counts are recorded rather than treated
as register collisions: one shared direct-resource identifier is an intentional
cross-stage binding, while the other four groups do not overlap. Digests pin
the inventories without publishing their values.

## ABI and outputs

The SysV AMD64 register contract proven from the FW 12.02 implementation is:

```c
int32_t sceAgcLinkShaders(
    AgcLinkedCx1202 *cx,                 // RDI, optional, writes 0x110 bytes
    AgcLinkedUc1202 *uc,                 // RSI, optional, writes 0x18 bytes
    const void *aux_pre_raster_shader,   // RDX, optional input
    const void *primary_pre_raster,      // RCX, optional at firmware level
    const void *pixel_shader,            // R8, optional at firmware level
    uint32_t primitive_type);            // R9D
```

`LinkShaders` allocates nothing. It initializes 32 eight-byte
`{register_offset, register_value}` CX entries for `SPI_PS_INPUT_CNTL`, followed
by `VGT_SHADER_STAGES_EN` at `0x100` and `VGT_GS_OUT_PRIM_TYPE` at `0x108`.
UC is three register pairs: `GE_CNTL`, `GE_USER_VGPR_EN`, and
`VGT_PRIMITIVE_TYPE`; writes end at offset `0x17`. These names and layouts are
independently corroborated by Prosper's Kyty-derived split implementations
`CreateInterpolantMapping` and `CreatePrimState`. Inputs are read but not mutated. The caller owns
and must retain every shader and output until no downstream pipeline/GPU
reference remains.

The firmware permits null outputs and null shader arguments, but these paths
produce defaults or partial results. The planner intentionally rejects them for
a usable graphics link. Output/input aliasing is also rejected even though the
implementation does not check it.

An isolated host transform runs the pinned self-contained implementation over
private copies of the selected inputs. Two executions begin with different CX
and UC prefills and converge on identical hashes, proving the complete output
ranges are overwritten deterministically. Canaries immediately before and
after both outputs remain intact, and relocated input copies remain unchanged.
Additional null-output, null-stage, and out-of-table primitive cases pin the
optional branches. No output bytes are persisted.

## Semantic algorithm

The pixel input count is a 32-bit field at header `+0x50`, with its array at
`+0x30`. The pre-raster output count is a 16-bit field at `+0x56`, with its
array at `+0x38`. Each element is four bytes. Matching uses the low byte of the
pixel word against the low byte of every pre-raster output word.

The output capacity is 32 entries. A pixel count above 31 reaches the default
fill path after the main loop; it is not reported as an error. The fail-closed
planner instead rejects counts above 32, duplicate pixel keys, and any missing
pre-raster producer. For the selected pair, the exact interface is one producer
and one consumer with key 15.

## Primitive type

For input values 1 through 18, the implementation indexes this verified map:

`[0, 1, 1, 2, 2, 2, 3, 2, 2, 1, 1, 2, 2, 2, 2, 2, 4, 1]`

For the CX `VGT_GS_OUT_PRIM_TYPE` value, zero and values above 18 silently use
value 2. UC `VGT_PRIMITIVE_TYPE` instead receives the original raw input. This
distinction is proven both statically and by host cases for 0 and 19. The planner
rejects out-of-table values. Prosper/Kyty corroborate common raw topology names
(1 point, 2 line list, 3 line strip, 4 triangle list, 5 triangle fan, 6 triangle
strip, and the observed 7/17 rect-list forms), but names for every enumerator
remain deliberately unclaimed.

## Return and rollback

Every control-flow exit in the pinned implementation converges on `xor eax,eax`:
the function always returns zero. It cannot certify stage correctness, semantic
compatibility, pointer validity, or output quality. A nonzero result in a future
probe would therefore mean ABI/firmware drift and the outputs must be retained
as indeterminate until safely retired. Planner rejection occurs before any call.

Because the transform mutates CX/UC immediately, outputs must be fresh and
disposable. There is no rollback and no identified destroy export; retirement
means waiting for zero downstream references and proven GPU quiescence, then
releasing outputs before backing shader storage.

## Stages and remaining uncertainty

The chosen corpus proves `type_raw=2` (VS/ES producer in the Kyty-derived public
layout) in the pre-raster position and `type_raw=1` (PS) in the pixel position.
The export itself does not inspect or reject either type field, so it does
**not** enforce a stage enum. The
planner admits only this observed role/type combination. The optional third
shader is proven structurally as another pre-raster contributor because its
special-state block affects both CX and UC, but no authorized three-stage pair
has yet been selected.

The implementation performs no alignment check and uses scalar x86 loads and
stores, so the machine-code path has no alignment precondition beyond readable
or writable bytes. The documented C structures have natural four-byte alignment;
the planner deliberately requires eight bytes. Remaining uncertainty is limited
to individual undocumented register bits, the complete primitive enum names,
and a concrete optional three-stage pair. These do not weaken the selected
pair's bounded proof.

## Reproduction

From `homebrew_ps5`:

```sh
python3 research/gpu/tools/verify_agc_link_gate.py
```

The gate checks dynsym, byte equality across the system/runtime/Ghidra copies,
instruction pins, the primitive lookup table, local pair hashes, the explicit
callsite, semantic compatibility, nine isolated host-transform cases, one
positive plan and seventeen negative cases.
Its sanitized manifest is
`research/gpu/captures/agc-link-gate.json`.

## Future CPU-only probe conditions

A later console probe remains a separate authorization boundary. Before one is
considered, it must use fresh non-aliased `0x110`/`0x18` buffers, retained
constructor-approved shader storage, the exact selected hashes, primitive 6,
prevalidated nested ranges, canaries outside both outputs, no queue/DCB/PM4 or
VideoOut work, and a written cleanup path for normal and indeterminate states.
