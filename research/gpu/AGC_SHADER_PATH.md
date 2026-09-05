# AGC shader path

## Firmware 12.02 constructor

The exported `sceAgcCreateShader` symbol (`f3dg2CSgRKY`) is present at
`libSceAgc+0xef70`. The complete 888-byte function is identical in the system
and authorized runtime captures.

Its x86-64 ABI is now statically pinned:

```text
RDI = AgcShader **destination
RSI = mutable AgcShader header
RDX = 256-byte-aligned shader code
```

The wrapper validates header magic `0x34333231` (`1234`), version `0x18`, and
an initially-null code field at `header+0x10`. It relocates the header in place,
stores the code pointer at `+0x10`, checks stage-specific SH registers, then
writes the constructed header pointer to `*destination`.

Consequently, a raw `.shader_text` blob is not enough. We need its matching
`.shader_header`, must preserve a writable copy because construction mutates it,
and must keep both header and 256-byte-aligned code storage alive while used.
The public constructor gives us a concrete registration route once an
authorized pair is located; it does not itself emit pipeline commands.

## Current source inventory

The authorized San Andreas and other-game eboot captures contain no ELF magic,
but this is no longer the end of the shader route. A second structural search
found 47 raw San Andreas AGC headers and their matching code blobs. Every pair
was cross-validated against the already-relocated copy in the other authorized
capture: all six self-relative header fields, the bound code pointer, exact code
bytes, 256-byte alignment, and the `barefoot` footer agree.

`tools/extract_authorized_agc_shaders.py` now reproduces the corpus under
`shaders/san-andreas-authorized/`; `tools/verify_authorized_agc_shaders.py`
checks all 47 pairs and all 94 files. The raw type inventory is 31 type 0,
15 type 1, and one type 2. Register-table correlation strongly indicates type
0 is compute and type 1 is pixel. Type 2 is the only plausible pre-raster stage,
but that name and its compatible pixel partner are deliberately not yet marked
proven.

The authorized captures contain no embedded AMDGPU ELF container.
The inventory now requires a structurally valid ELF64 `EM_AMDGPU` object and
bounded section table before it reports a candidate, and separately records
whether both `.shader_header` and `.shader_text` exist. Synthetic positive,
malformed, truncated, and wrong-machine cases are covered by unit tests.

For the first accelerated solid-color stage, shader acquisition remains off the
critical path because the planned `DMA_DATA` fill needs no shader. A shader pair
becomes mandatory for the later triangle stage. We now possess validated binary
and metadata pairs; the remaining shader gate is semantic pairing, not sourcing.
