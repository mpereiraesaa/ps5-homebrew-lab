# AGC laboratory integration

This document is the implemented contract for `legacy/apps/agc-native-sce`, not a
future migration plan. Since 2026-09-05, active AGC builds use network-only
structured telemetry and never write a log file on the console.

## Build contract

`legacy/apps/agc-native-sce/build_stage_f.sh`:

1. requires the private, git-ignored `projects/logging_server/dev.conf`;
2. compiles `client/ps5log.c` as C11 and links `ps5log.o`;
3. packages the config as `dist-stage-<variant>/PPSA99998/dev.conf`, which is
   visible to the title as `/app0/dev.conf`;
4. never embeds a host address in source or in the public repository.

All F/G/H/I variants share this path. A missing config is a build error rather
than a silently unobservable artifact.

### Native loader prerequisite

The firmware-12.02 native-title smoke test originally failed before `main()`
even though every `libSceNet` import and NID had been validated. The defect was
in the older boilerplate module writer: the RELRO program header was derived
from `.got` instead of the beginning of `.data.rel.ro`, which could violate the
PS5 loader's 16 KiB `p_offset % p_align == p_vaddr % p_align` requirement once
the logging backend added relocations. The local boilerplate fix derives RELRO
from `.data.rel.ro`, checks the congruence while writing the ELF, and includes a
regression test. This is a packaging/linker prerequisite, not a networking ABI
workaround; do not remove logging or change verified NIDs to mask this class of
loader failure.

## Runtime contract

At the start of `main()`, before AGC or VideoOut initialization, the runtime:

- loads only `/app0/dev.conf`;
- creates one monotonic boot token;
- passes that same token to the `ps5log/1` HELLO and logs it as
  `LOG_BOOT_MONOTONIC_NS`;
- declares `LOG_SCHEMA=3`, structured TCP transport and disabled filesystem
  sinks.

The existing fragment-based `log_text/log_hex*` interface is preserved, but
`log_bytes()` now assembles complete lines in a fixed 1 KiB buffer and emits
each through `ps5log_line`. Therefore every application line has a sequence
number and console monotonic timestamp; AGC runs must have `raw_lines=0`.

There is no USB path, `/download0` path, `open`, `write`, `fsync`, mirror fd or
mount retry in the active runtime. Network initialization and sends are
bounded. Failure disables telemetry without changing the GPU transaction.

Native titles compile `ps5log.c` with `ps5log_ps5_net.h` and link
`ps5log_ps5_net.c`. This backend maps only network handles to `sceNet*`, uses
`SCE_NET_SO_NBIO` plus `sceNetEpoll*` for bounded connect, and leaves file
descriptors such as `/app0/dev.conf` on the ordinary libc path.

The runtime emits BYE after clean teardown, after a pre-submit clean failure,
or after recording a retained-state park. The classifier still controls
cleanup: a clean transport close never makes an ambiguous GPU state safe.

## Host workflow

Start the tested server explicitly:

```sh
cd projects/logging_server
make check
make serve
```

Run the canonical monitor from the lab root:

```sh
python3 tools/agc_net_monitor.py --host "$PS5_HOST" --launch \
  --artifact legacy/apps/agc-native-sce/dist-stage-g/PPSA99998/eboot.bin
```

The monitor refuses to launch unless localhost TCP 9300 is listening. It
snapshots existing runs, follows only a newly created
`PPSA99998/agc-native-sce` transcript, and waits for its atomic manifest.

`tools/ps5log_evidence.py` verifies:

- exact title/app and matching HELLO/log boot tokens;
- TCP `ps5log/1`, HELLO, BYE and matching final sequence;
- structured records only, no gaps or oversized records;
- manifest byte count and SHA-256 against the transcript;
- safe basename resolution for the referenced log.

The phase classifier then evaluates GPU ownership. The monitor copies both
server artifacts into `research/gpu/captures/runtime/` and creates a capture
manifest containing the deployed artifact hash. `--close-on-safe` passes the
manifest, boot and transcript hash to `night_supervisor`, which revalidates all
three immediately before exact-title close.

## Failure policy

- No ps5logd listener: fail before launch.
- No connection or no finalized fresh run: retain/fail; never query console
  files as a fallback.
- Gap, RAW line, missing BYE, identity mismatch or hash mismatch: reject.
- Park marker after submit: preserve the classifier's retained-state result
  even when the network manifest is clean.
- Reconnect is forbidden inside a GPU transaction.

## Required checks

`make agc-check` runs the server/client/roundtrip suites, network observability
tests, manifest tamper tests, close revalidation tests, phase classifiers and
the renderer's host contracts. It also asserts that active runtime and launcher
sources cannot silently regain USB, `/download0`, `nmount` or `fsync`.

## Hardware gates

The payload client has already been demonstrated on firmware 12.02. Native
title use remains a hardware gate and must be validated in order with the AGC
roadmap: G/21, G/22, H, then I. Offline builds do not prove network access from
the native-title sandbox or GPU execution.
