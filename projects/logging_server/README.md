# logging_server — TCP line-stream debug logging for PS5 homebrew

A development-PC log server plus a tiny C client so PS5 payloads and native
titles stream their debug output over the LAN instead of writing files inside
the title sandbox, on USB, or through privileged bind mounts.

```text
PS5 homebrew ──(ps5log client, dev.conf: DEV_SERVER=<pc-ip>)──▶ ps5logd on the PC
                                                                 ├─ live terminal view
                                                                 ├─ runs/<utc>_<title>_<app>_<boot>.log  (verbatim)
                                                                 └─ runs/<same>.json                     (manifest)
```

Why this route: the console kernel delivers anything already handed to
`send()` even if the process dies the next instruction, the PC sees every
line within milliseconds, nothing on the console needs `/data`, `/mnt/usb0`,
or a helper that edits the sandbox mount table, and the resulting run files
are ordinary evidence artifacts with hashes and sequence-gap detection.

The project is self-contained: Python 3 standard library on the PC, C11 with
BSD sockets on the console, no other dependencies.

## Layout

| Path | Purpose |
| --- | --- |
| `server/ps5logd.py` | The server. `python3 server/ps5logd.py --help`. |
| `server/tests/` | Unit and loopback tests for the server. |
| `client/ps5log.h` | Single-header client library (stb style; no heap, no threads). `client/ps5log.c` is an optional two-line wrapper for two-file builds. |
| `client/tests/` | Host unit tests and an end-to-end round trip through a loopback server. |
| `client/examples/hello_log.c` | Minimal client; builds for the host and as a PS5 payload. |
| `dev.conf.example` | Configuration template. Copy to `dev.conf` (git-ignored). |
| `PROTOCOL.md` | Wire format and manifest fields. |
| `INTEGRATION.md` | How to adopt the client in an existing app or payload, including the concrete plan for `legacy/apps/agc-native-sce` (build script, runtime hook, verifier, supervisor) and the remaining hardware gates. |

## Quick start

On the PC:

```sh
make check          # server tests, client host tests, end-to-end round trip
make serve          # listen on 0.0.0.0:9300 (TCP + UDP), runs -> ./runs
```

The server prints a `dev.conf hint` line with the address to use. Put that in
`dev.conf` on the console side:

```ini
DEV_SERVER=192.168.0.10
DEV_PORT=9300
```

Where the client looks for it, in order: `/app0/dev.conf` (package it as
`dist/<TITLE>/dev.conf`),
`/data/homebrew/dev.conf` (payloads), `./dev.conf`. `PS5LOG_CONF` overrides
the list.

The AGC laboratory uses a stricter profile: only packaged `/app0/dev.conf`,
TCP, structured records and no console filesystem mirror. Its launcher never
mounts USB and its supervisor trusts only complete PC-side manifests.

## Using it in a homebrew: three levels

**1. Single header, zero-change `printf`.** Copy `client/ps5log.h` into the
project. In one source file, as the first include:

```c
#define PS5LOG_IMPLEMENTATION
#include "ps5log.h"

int main(void) {
    ps5log_quickstart("PPSA99998", "my-app", PS5LOG_CAPTURE_STDIO);
    printf("this line reaches the PC unchanged\n");   /* stored as RAW */
    fprintf(stderr, "so does stderr\n");
    /* ... existing code, untouched ... */
    ps5log_close("done");
    return 0;
}
```

`ps5log_quickstart` reads `dev.conf`, connects within the timeout, sends the
HELLO line and duplicates the socket onto fd 1 and fd 2. Existing `printf`,
`puts`, `fprintf(stderr, ...)` and C++ `std::cout` output is streamed as RAW
lines; stdout is switched to line buffering so every `\n` is sent
immediately. `ps5log_close` puts the original descriptors back. If no
`dev.conf` exists or the PC is down, nothing is redirected and the program
behaves exactly as before.

**2. Structured records where they matter.** Same header, add `LOG()`-style
calls for the lines you want sequence numbers and device timestamps on:

```c
#define PS5LOG_SHORT_MACROS      /* LOG / LOGW / LOGE / LOGM */
#include "ps5log.h"

LOGM("STAGE_E_PREFLIGHT_COMPLETE");          /* MARK: checkpoint */
LOG("dcb dwords=%u", dwords);                /* INFO */
ps5log_hex64(PS5LOG_INFO, "fence", fence);   /* fence=0x1100 */
LOGE("submit rc=0x%08x", rc);                /* ERR */
```

Without `PS5LOG_SHORT_MACROS` the same macros are `PS5LOG_LOG`,
`PS5LOG_WARNF`, `PS5LOG_ERRF`, `PS5LOG_MARKF`. Structured and RAW lines can
share one connection; framing is preserved because every line is one write.

**2b. Existing `write(fd)`-style loggers.** If the program already builds its
own log lines and writes them with `write()`, forward the same bytes with
`ps5log_raw(ptr, len)`; fragments are fine because TCP preserves order and
the server reassembles lines. This is the route for the AGC lab's
`log_bytes()`; the step-by-step plan is in `INTEGRATION.md` section 3.

**3. No client at all.** Shell payloads or anything with `nc`:

```sh
printf 'hello from a shell payload\n' | nc <pc-ip> 9300
```

Two-file builds are still supported: compile `client/ps5log.c` (which only
defines `PS5LOG_IMPLEMENTATION` and includes the header) and include
`ps5log.h` normally everywhere else.

### What capture cannot do

- Captured lines have no sequence number or device timestamp; the server
  timestamps them on arrival and reports them as `raw_lines`, never as gaps.
- UDP mode does not support capture (no ordered stream to duplicate).
- **Enable capture before the first `printf`.** The call switches `stdout`
  to line buffering with `setvbuf`, which C only guarantees on an unused
  stream; glibc silently keeps full buffering otherwise, and then `printf`
  lines only leave the process on `fflush(stdout)`, a full buffer, or exit.
  `ps5log_quickstart(...)` as the first statement of `main()` satisfies
  this. `stderr` is unbuffered and always immediate. Output written without
  a trailing newline stays buffered until flushed, exactly as with a file.
- A PC that disappears mid-run is handled: the next structured send fails,
  the channel is disabled and fd 1/2 are restored, so later `printf` calls
  go back to where they went before. On PS5/FreeBSD the socket carries
  `SO_NOSIGPIPE`; on a Linux host pass `PS5LOG_CAPTURE_IGNORE_SIGPIPE` or
  ignore `SIGPIPE` yourself, otherwise a `printf` racing the disconnect can
  raise SIGPIPE.

## Behaviour guarantees of the client

- Never blocks longer than `DEV_CONNECT_TIMEOUT_MS` at init or
  `DEV_SEND_TIMEOUT_MS` per record.
- Never fails the application: without `dev.conf`, with `DEV_ENABLED=0`, or
  with an unreachable PC every call becomes a no-op that still increments the
  sequence number and still writes to the optional mirror descriptor.
- Disables itself on the first socket failure to keep the stream framed;
  `ps5log_reconnect()` re-attaches at a point the caller chooses.
- No heap allocation, no threads, no signal handlers. Not thread-safe: call
  from one thread or wrap the calls.
- Only dotted IPv4 addresses are accepted, so no DNS lookup can stall a run.
  The address is parsed by the header itself: the payload's undefined
  network symbols are exactly `socket`, `connect`, `send` and `poll`, so no
  extra network library is linked into a title.

## Tests

`make check` runs three suites:

| Suite | What it proves |
| --- | --- |
| `make test-server` | Parsing, framing (partial lines, CRLF, oversized lines), gap detection, manifests, retention, TCP/UDP loopback, shutdown finalization. |
| `make test-client` | Config parsing and file search, record/HELLO formatting and truncation, disabled and unreachable-server paths, mirror fallback, bounded connect time, stdio capture and restore, capture release when the peer vanishes. |
| `make roundtrip` | The compiled single-header C example against a real loopback server: verbatim log, manifest, `printf` capture interleaved with structured records, UDP mode, `PS5LOG_CONF`, dead server, no config. |

Verified on Linux with GCC 13 and Python 3.12. The PS5 payload build
(`make ps5-example`) needs the PS5 payload SDK.

## Hardware verification (PS5 firmware 12.02, 2026-09-05)

`build/hello_log.elf` and `build/hello_log_capture.elf` were sent through
elfldr (port 9021) with `/data/homebrew/dev.conf` pointing at this PC. Runs
are kept under `runs/` (git-ignored).

| Gate | Observed |
| --- | --- |
| Payload, TCP, structured records | HELLO received, 9 records, `gaps=[]`, `clean=true`, config path `/data/homebrew/dev.conf` reported by the client. Init took 4 ms. |
| Zero-change `printf` capture on the PS5 libc | The init status line, a `printf` line and a `stderr` line arrived as RAW, in program order, before the structured record issued after them. After `ps5log_close()` the final status line went back to the elfldr socket, proving fd 1 was restored. `raw_lines=3`, `records=9`, `gaps=[]`. |
| PC reachable but server stopped | `network=connect() failed`, errno 61 (ECONNREFUSED), init 2 ms, all 9 records counted as dropped, payload exited normally. |
| PC address silent (forced timeout) | `network=connect() timed out`, errno 60 (ETIMEDOUT), init 500 ms with `DEV_CONNECT_TIMEOUT_MS=500`, payload exited normally. |

Not yet exercised: the client inside a native title (`/app0/dev.conf`), which
needs a title rebuild and belongs to the AGC lab's own gate sequence.

## Port

Default `9300` on both TCP and UDP. It does not collide with the ports the
laboratory already uses on the console (744, 755, 2121, 2323, 3232, 6969,
8082, 9021) or on the PC (8011, 8089).

## Status

Host-verified and payload-verified on hardware (see above); native-title use
pending. Licensing and the public repository name are still to be decided by
the owner; nothing here embeds a LAN address, console identity, or
proprietary material.
