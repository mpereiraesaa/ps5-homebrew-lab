# `sceAgcCreateShader` CPU gate — FW 12.02

> Registro histórico del gate CPU anterior a Stage E. Ya no expresa el próximo
> objetivo; consulte `STAGE_E_TRIANGLE.md` y `../../docs/ROADMAP.md`.

## Scope and result

This gate defines and now validates the CPU-side contract. On 2026-09-04 an
independent Stage E pair was accepted by `sceAgcCreateShader` and
`sceAgcLinkShaders` in `PPSA99998` on FW 12.02. The experiment created no queue,
emitted/submitted no DCB, and used neither draw nor VideoOut. Its recorded
output is limited to return codes, hashes, canaries and cleanup status.

The FW 12.02 export is NID `f3dg2CSgRKY`, at `libSceAgc+0xef70`. Its 888 bytes
and its 212-byte relocation helper match between the system module and an
authorized runtime copy. The NID/value/size tuple is read from the module's
dynamic symbol table, and the function also matches the local analysis ELF
opened in Ghidra. The SysV x86-64 ABI is:

```c
int32_t sceAgcCreateShader(AgcShaderHeader **destination,
                           AgcShaderHeader *mutable_header,
                           const void *code);
```

The export allocates nothing. On success it relocates self-relative pointers
inside the caller's writable header, stores `code` at header offset `0x10`,
patches a stage program register, writes the same header address to
`*destination`, and returns zero. Therefore the returned value is an alias,
not an independently owned shader object.

## Fixed prefix and bounded inputs

`include/agc_create_shader_contract.h` records the 0x60-byte prefix and the
0x38-byte nested user-data structure with compile-time offset assertions. The
constructor reads or modifies six header pointer fields at offsets 0x08, 0x18,
0x20, 0x28, 0x30 and 0x38. The relocation helper treats every nonzero value as
self-relative to its own field.

The pointer at 0x08 is structurally mandatory on FW 12.02. Ghidra's decompile
of the relocation helper shows that a zero value produces a null local pointer
which is then dereferenced unconditionally. The 0x38-byte user-data structure
must therefore be present and writable even when it describes no resources.
Its five nested pointers may be null when all corresponding counts are zero.

The host planner consequently requires:

- a writable 8-byte destination slot initially containing null;
- an 8-byte-aligned, readable and writable header whose declared size covers
  the fixed prefix and every relocated array;
- magic `0x34333231`, version `0x18`, and a null code field;
- readable code covering the declared shader size at a 256-byte-aligned base;
- enough code bytes for the constructor's footer access and a validated
  `barefoot` marker;
- stage in 0..7 and, except for stages 4/5, a nonempty SH array containing the
  stage-required register;
- bounded CX/SH, input/output semantics and nested direct/sharp resource arrays;
- a present, writable 0x38-byte user-data structure;
- a runtime mode and target policy accepted by the byte-pinned firmware logic.

The export itself does not protect the caller from null pointers, malformed
self-relative ranges, short code, or misalignment. Those are mandatory planner
checks, not claimed firmware guarantees.

## Target and return policy

The target branch table is reproduced in `agc_create_shader_planner.py`.
Targets with the high bit set require an external helper whose semantics remain
unproven and therefore fail closed. Targets 10, 12, 13 and 15 have feature-flag
conditions; targets 13+ also pass through the SDK-word gate when their special
branch permits it. The authorized local corpus uses target 5, avoiding all four
feature-dependent cases.

Byte-pinned returns are: success `0`, bad magic `0x8a6c0003`, bad version
`0x8a6c0004`, missing required stage register `0x8a6c0005`, already-bound header
`0x8a6c001f`, rejected runtime mode `0x8a6c002f`, target policy
`0x8a6c003d`, and failed signed-target helper `0x8a6c0042`.

## Ownership and retirement

No symmetric DestroyShader export has been identified. The safe contract is
caller ownership of both mutable header and code for the entire lifetime of
every pipeline and GPU reference. Retirement is allowed only after the caller
proves the downstream reference count is zero and pipeline/GPU use is
quiescent. ProsperoTV corroborates this model operationally: it drains first,
then unmaps and releases the common shader allocation; it does not destroy an
independent shader allocation.

The missing-stage-register error `0x8a6c0005` is reached after relocation and
code binding. It therefore consumes/poisons that mutable copy even though
`*destination` is not published. The copy must be discarded, not retried.
Unknown errors are classified as indeterminate and require retaining the
allocation. The host mock tests this state machine separately from retirement.

## Cross-checks

- Prosper/Kyty corroborate the 0x60 header prefix, self-relative relocation,
  code binding, stage-program patching and aliasing write to `*destination`.
  Prosper adds emulator-side registry bookkeeping; that registry is not a
  behavior of the PS5 export.
- ProsperoTV declares the same three-argument ABI, supplies retained direct
  memory with aligned code offsets, and releases it only after drain.
- The authorized local game evidence contains 47 unrelocated/matching-code
  pairs and corresponding already-relocated runtime outcomes. The corpus
  verifier ran the planner over all 47: 31 stage 0, 15 stage 1, one stage 2,
  all target 5. Every declared header/code size, nested user-data range and
  required stage-register match passed. Only aggregate counts and a sanitized
  plan digest were emitted.
- The owned-game runtime callsite verifier resolves its GOT slot to
  `libSceAgc+0xef70`, pins the PLT thunk, and identifies 47 direct calls in one
  initializer plus one generic wrapper call. For all 47 direct calls it
  correlates the three prepared arguments with the authorized relocated header
  outcomes and verifies that the return value is tested. Addresses and bytes
  are reduced to counts and sanitized hashes in the emitted proof.

This cross-capture result demonstrates the constructor transformation shape;
it does not identify a graphics pair, authorize copying proprietary material,
or prove GPU execution.

## Reproduction

From `homebrew_ps5/`:

```sh
python3 research/gpu/tools/verify_agc_create_shader.py \
  --system research/gpu/dumps/system-libSceAgc.sprx \
  --runtime research/gpu/dumps/game-libSceAgc.sprx.bin \
  --output research/gpu/captures/agc-create-shader-proof.json
python3 research/gpu/tools/verify_agc_create_shader_corpus_contract.py \
  --manifest research/gpu/captures/agc-authorized-shader-pairs.json \
  --shaders research/gpu/shaders/san-andreas-authorized \
  --module research/gpu/dumps/game-libSceAgc.sprx.bin \
  --output research/gpu/captures/agc-create-shader-corpus-contract.json
python3 research/gpu/tools/verify_agc_create_shader_gate.py \
  --static-proof research/gpu/captures/agc-create-shader-proof.json \
  --corpus-proof research/gpu/captures/agc-create-shader-corpus-contract.json \
  --callsite-proof research/gpu/captures/agc-create-shader-callsites.json
python3 -m unittest research/gpu/tools/test_agc_create_shader_planner.py
```

## Remaining conditions for a later probe

A separate goal must select a legally usable, non-published shader/header pair;
prove its stage semantics and target/global compatibility; define an exact
allocation, rollback and retirement state machine; and independently authorize
one console call. Construction success must remain distinct from pipeline or
GPU success.
