# AGC RegisterDefaults CPU gate (FW 12.02)

## Result

The legacy `sceAgcGetRegisterDefaults()` result is a 0x40-byte root object. It
contains three pointer banks (CX, SH and UC), a null fourth bank, two opaque
qwords, a type/index table pointer and a 32-bit count at offset 0x38.

On the tested FW 12.02 module, the type/index table is **137 count-delimited
8-byte records**, not 12-byte triplets:

```c
struct AgcTypeIndexPair {
    uint32_t key;
    uint32_t encoded_index; // (index << 2) | bank
};
```

Bank selectors 0, 1 and 2 resolve to CX, SH and UC. Their observed counts are
84, 32 and 21. Within each bank, decoded indexes are exactly the ordered range
`0..N-1`. The structure and the type table have no sentinel: `count` is their
only terminator. Register-pair targets remain opaque at this gate because the
root object supplies no per-target length. Reading beyond the first validated
pair based on guessed zero sentinels or pointer spacing would therefore violate
the bounded-read rule.

## Evidence and reproducibility

`capture_agc_defaults_cpu.py` validates every complete read against exactly one
readable process map before reading it. It emits counts, ranges, invariants and
SHA-256 values, never raw tables. Two separately launched processes produced
different PIDs and identical sanitized results. Use:

```sh
python3 research/gpu/tools/verify_agc_defaults_cpu_runs.py \
  research/gpu/captures/agc-defaults-cpu-run1.json \
  research/gpu/captures/agc-defaults-cpu-run2.json
```

The verifier rejects the wrong schema or firmware, inconsistent count, bank,
index, pointer range or termination model, malformed hashes, a changed safety
envelope, equal PIDs, and any reproducibility mismatch.

## Public/static contrast

The public Prosper/Kyty implementation corroborates the 0x40 root layout and
the `(index << 2) | bank` encoding. Its public `GetRegisterDefaults2` model uses
12-byte records and currently reports 128 entries (79 CX, 29 SH, 20 UC). The
live FW 12.02 legacy export uses 8-byte pairs and 137 entries (84/32/21). This is
an API/version-model difference; the public table must not be treated as a
byte-for-byte description of this firmware export.

The five captured regions (root, three pointer banks and type/index table) were
also matched to the corresponding file-backed blocks in the local Ghidra
analysis image `game-libSceAgc.analysis.elf`. No proprietary bytes or keys are
included here.

## Safety boundary and next gate

This gate performs no process writes, debugger attach, remote in-process calls,
shader calls, queue/DCB creation, PM4 emission, submit or VideoOut work. Its
output is sufficient to design the inputs and rejection checks for a later,
separate `sceAgcCreateShader` experiment; it does not authorize that experiment.
