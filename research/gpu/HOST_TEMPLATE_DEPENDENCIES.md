# BigApp host dependency analysis

## NPXS40106 startup imports

The firmware-12.02 Game Streaming eboot has `e_entry=0x80`. Its first three
PLT calls resolve as follows using the SDK's own `prospero-nid` generator:

| Call site | PLT symbol | Plain symbol | Effect |
|---|---|---|---|
| `entry+0x14` | `bzQExy189ZI` | `_init_env` | libc environment setup |
| `entry+0x1c` | `8G2LB+A3rzg` | `atexit` | register cleanup callback |
| `entry+0x28` | `8G2LB+A3rzg` | `atexit` | register second callback |

The direct call at `entry+0x2d` is the eboot constructor dispatcher, followed
by application main at `entry+0x3a`. None of the three imported calls is an AGC
initializer.

## Decisive pre-entry dependency

The decrypted eboot declares 53 `DT_NEEDED` modules. They include both:

```text
libSceAgcDriver.prx
libSceAgc.prx
```

Dynamic dependencies are processed before control reaches `e_entry`. This
explains why moving hbldr from `entry+0x3a` to `entry+0x2d` left GetDmem at
`0xff0040000/0x1b0000`: the AGC dependency and its process policy already
exist. An `entry+0x00` breakpoint cannot prevent `DT_NEEDED` loading and is no
longer a useful next experiment.

## Other signed system BigApps

Read-only copies of three installed system eboots were compared locally:

| Title | Purpose | Needed modules | Direct AGC dependencies | Standard hbldr offsets |
|---|---|---:|---|---|
| `NPXS40074` | Remote Play | 38 | driver + AGC | yes |
| `NPXS40099` | Share Play | 35 | driver + AGC | yes |
| `NPXS40106` | Game Streaming | 53 | driver + AGC | yes |
| `NPXS40250` | HRTF Personalization | 27 | driver + AGC | yes |

All four use the same 72-byte CRT startup shape: `_init_env`, two `atexit`
calls, constructor dispatch at `entry+0x2d`, main at `entry+0x3a`, and exit.
HRTF is therefore structurally compatible with the current replacement point
and is the smallest available signed BigApp host, but it is not an AGC-free
control. A reversible HRTF-host GetDmem run can still determine whether the
4-GiB relocation is specific to Game Streaming's dependency/process setup or
common to system BigApps.

Any such test must preserve encrypted SELF bytes with a console-side backup,
verify the candidate through decrypted readback, run only phase 0C, and restore
the original console-side bytes with verified decrypted SHA-256 before ending.
