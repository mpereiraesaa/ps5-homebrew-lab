# Early-host analysis for AGC

## Observed startup sequence

The decrypted firmware-12 `NPXS40106` eboot has `e_entry=0x80`. Its startup
sequence is:

```text
entry+0x00  save registers / capture argc and argv
entry+0x14  first imported CRT setup call
entry+0x19  imported setup call for argv
entry+0x21  imported setup call for process-global data
entry+0x2d  call eboot constructor dispatcher at VA 0x10
entry+0x3a  call application main
entry+0x41  imported exit call
```

The dispatcher at VA `0x10` walks two arrays of function pointers and invokes
each non-null entry. The integrated shsrv `hbldr` historically breaks at
`entry+58` decimal, which is exactly `entry+0x3a`, immediately before `main`
but after this constructor dispatcher.

This initially made the eboot constructor dispatcher a plausible source of the
inherited AGC/compositor mappings observed inside `SceCloudClientApp`.

## Bounded experimental variant

`bundles/hbldr/hbldr.c` now exposes a compile-time
`HBLDR_BREAKPOINT_OFFSET`, while retaining `0x3a` as the default. A dedicated
diagnostic build can use `0x2d` to execute the three initial CRT setup calls but
stop before the eboot constructor dispatcher. This source change does not alter
the currently deployed loader or the normal build.

The first early-host payload must remain phase 0C only: load AgcDriver, query
GetDmem, unload, log, and exit. Success means
`base=0xfe0040000,size=0x1b0000`; any other result or a missing clean exit ends
the experiment. It must not load `libSceAgc`, allocate GPU resources, create a
queue, touch VideoOut, submit commands, or modify mappings.

## Safety gates before deployment

1. Build the normal loader and prove its bytes/behavior remain unchanged apart
   from the configurable constant in source.
2. Build the early variant as a separate artifact; never overwrite the active
   shsrv binary in place.
3. Verify no BigApp and two consecutive healthy service checks.
4. Launch only the existing phase-0C getter with a watchdog.
5. Identify and cleanly close only `FAKE00000`; do not kill an unidentified
   process.
6. If the early process does not reach the payload or any service degrades,
   stop hardware work and retain the proven normal loader.

An entrypoint breakpoint (`offset=0`) exists in the older standalone loader,
but it skips all eboot-side CRT setup and is therefore not the first choice.
`0x2d` isolates the constructor hypothesis with a smaller behavioral change.

## Hardware result (firmware 12.02)

The modern shsrv hbldr implementation was built as a separate standalone ELF,
with its normal `0x3a` breakpoint changed only to `0x2d` and a fixed path to
the previously size-verified phase-0C payload. It did not replace or restart
the deployed shsrv. Two complete health checks passed, no BigApp was active,
and the payload ran and exited cleanly.

```text
GetDmem rc=0
base=0x0000000ff0040000
size=0x001b0000
```

Therefore the host eboot's constructor dispatcher is **not** what causes the
4-GiB relocation. The relevant mapping/policy is already established before
`entry+0x2d`, most plausibly during process creation, dependency loading, or
the three imported CRT/process setup calls. The probe automatically left no
BigApp running; the close helper correctly refused to act because there was
nothing to close. All four services remained healthy and the shell returned to
`NPXS40112`.

Do not repeat offsets `0x2d` or `0x3a`; they now answer the same question. An
entrypoint (`0x00`) experiment would distinguish process/dependency policy from
the early imported calls, but it changes more startup state and needs a probe
that cannot depend on skipped CRT initialization. Static analysis of those
three imports and the loader-time dependency set is the safer next step.
