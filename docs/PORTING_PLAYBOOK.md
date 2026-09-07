# PS5 (Prospero) porting playbook

This is a **cross-project** document. It applies to every project under
`projects/` that ports third-party code to native PS5, present and future.
Read it before starting a new port and before spending a day bisecting a
crash. Keep it alive: when a blocker is solved, add a post-mortem here and, if
it generalizes, a rule.

The lesson that created this file: a "filesystem crash loading `gfx/palette.lmp`"
turned out to be an unusable `strcasestr` exported by `libSceLibcInternal`. It
cost a full session of reactive, app-level hypotheses (buffer overflow, fd
mismatch, null memory pool) because the **class** of the bug was never checked
first. This playbook exists so the next agent checks the class first.

## Principle 1 — a system symbol that is *exported* is not *working*

Prospero system libraries (`libSceLibcInternal`, `libkernel`, …) export many
symbols that are placeholders, aliases, or subtly wrong for the payload
runtime. Treat "provided by `libSceLibcInternal`" in a symbol-gap report as a
**yellow flag, not a green check**.

- When the port already ships a portable, self-contained implementation of a
  libc-ish helper behind a `HAVE_X` flag, **default to the in-tree one
  (`HAVE_X=0`)**. It is already written and upstream-tested; for string/util
  helpers it costs nothing and removes an entire bug class.
- This is not "always avoid the system lib." Core, standard, widely-exercised
  functions are usually fine (`strcasecmp`, `strncasecmp`, `strnlen`,
  `strlcpy`, `strlcat`, `malloc`, `pthread_*`, sockets, `clock_gettime` all
  work here). Decide **case by case**, biased toward the in-tree impl when the
  function is non-standard (e.g. `strcasestr`) or unverified.
- **Verify by execution, not by the symbol table.** A three-line smoke test at
  boot that actually calls the symbol on real input catches this in minutes.
  A grep of `--dyn-syms` only tells you it is *imported*, not that it *works*.

## Principle 2 — read the fault signature before theorizing

The register/fault signature narrows the *class* before you touch app code.

| Signature | Most likely class | Check first |
| --- | --- | --- |
| `pc` outside your image **and** `rax == pc`, `addr=0` | indirect call through a bad/placeholder pointer | an unresolved or broken **imported symbol** (Principle 1); dump `--dyn-syms` |
| `addr` = small value, `pc` in your code | null-pointer deref | an uninitialized global/pool/handle |
| `addr` = a large heap/stack address, `pc` in your code | out-of-bounds **data** write | a fixed-size buffer; a size derived from data |
| `pc` on the stack after a clean call chain | smashed return address | a buffer overrun in an *earlier* frame, or a broken `ret`/`call` target |

A data overrun of `buf[n]` faults at `buf+n` (a data address), **not** with
`pc` on the stack. If `pc` is a fixed system address and `rax==pc`, stop
theorizing about heaps and buffers and look at imported symbols.

## Principle 3 — diagnosis discipline (what actually works here)

1. **Reproduce deterministically, one variable per run.** Bisect data and
   config the way the lab bisects everything.
2. **Prove the change is in the binary before trusting a result.** Patches to a
   pinned submodule can silently *not* compile (or get reverted). After every
   instrumentation build:
   `strings build/.../llvm-pie.elf | grep <MY_MARKER>` — if it is not there,
   your last "it did not fire" conclusion is worthless.
3. **Name the exact caller with `__builtin_return_address(0/1/2)`** logged
   through `ps5log/1`, then map the addresses offline against the linked ELF
   (`llvm-nm --numeric-sort` + nearest-symbol; note module-local symbols may be
   stripped by `objcopy -G lib_<name>_exports`, so a caller in a relocatable
   module can resolve to "nothing" — that itself tells you which layer).
4. **Bracket the crash statement-by-statement.** Put a telemetry marker before
   and after each call/return in the suspect function; the last marker before
   the fault localizes it to one statement.
5. **When the fault is a control transfer (Principle 2, row 1), check the ELF's
   dynamic imports and whether the platform lib truly implements that symbol —
   before app-level hypotheses.** This is the step whose absence cost the
   `strcasestr` day.

## The Prospero runtime contract (living list)

What the FW 12.02 ShadowMount payload title actually does, measured. Extend it
as new facts appear. Full detail and evidence in `docs/FINDINGS.md`.

- Descriptors 0–2 start **closed**; `dup2` onto them returns `EPERM`.
- `libSceLibcInternal` `getcwd()` **faults**; `strcasestr` is **unusable**.
- `chdir`, `access`, libc `opendir` return `EPERM` broadly; `getdents` returns
  `EINVAL` on the `/app0` nullfs image (works on `/download0`).
- `/download0` is writable/persistent with positive `downloadDataSize`;
  `/temp0` is absent; `/data`, `/user` are outside the sandbox.
- libc heap is ~8 MiB and **cannot be grown** from a title (no `sceLibcHeapSize`
  in the SDK); route large allocations to anonymous `mmap`.
- **No** file-backed `mmap`, **no** POSIX named semaphores, **no** `execve` of
  filesystem ELFs, **no** arbitrary `dlopen`; IPv6 via SDK `getaddrinfo`
  unusable. `dup`/`dup2` unavailable. (Cross-checked with BlackBear's
  `ps5-python/docs/ps5-limitations.md`.)
- Working, verified: `socket`/`bind`/`sendto`/`poll`, `pthread_*`,
  `clock_gettime`, `sceKernelOpen`/`Read`/`Write`/`Close`/`Stat`/`Getdents`,
  `strcasecmp`/`strncasecmp`/`strnlen`/`strlcpy`/`strlcat`.

## New-port pre-flight checklist

- [ ] List every libc/syscall symbol the port will depend on; for the
      non-standard ones, add a boot-time **smoke test** that calls each on real
      input and reports through `ps5log/1`.
- [ ] Default every `HAVE_X`-style "use system impl" flag to the port's own
      implementation; opt into a system one only with a reason and a smoke test.
- [ ] After the first link, dump `--dyn-syms` and review every imported symbol:
      is each one known-good, or merely exported?
- [ ] Keep the fd lifecycle in one namespace: if you shim `open` to
      `sceKernelOpen`, verify `read`/`lseek`/`write`/`close`/`fstat` on that fd
      (they worked here via libc, but verify per port).
- [ ] Reuse the lab's evidence discipline: `ps5log/1` markers, immutable run
      manifests, one variable per hardware run.

## Blocker post-mortems

Record every non-trivial blocker here with this shape, so the next agent
recognizes the pattern instead of re-deriving it.

**Template:** *Symptom* (observable, incl. fault signature) · *False leads*
(what looked plausible and was wrong) · *Actual cause* · *Fix* · *General rule*
(what to check first next time) · *Reference* (project, PR, run id).

### strcasestr from libSceLibcInternal is unusable (Xash3D, 2026-09-07)

- **Symptom:** deterministic `SIGSEGV` while loading `gfx/palette.lmp`,
  `pc=0x7eeffa2d0` (a fixed system address), `rax==pc`, `addr=0`, `rsp=0`. Read
  for a whole session as a "gfx filesystem crash."
- **False leads (all disproved with telemetry):** overflow of
  `FS_OpenReadFile`'s `netpath[1024]`; a `lseek`/`read` fd-namespace mismatch on
  `sceKernelOpen` fds; a null `host.imagepool` in `Image_CopyPalette32bit`. The
  whole filesystem chain (open, size 768, alloc, read 768, close, return) was
  proven correct.
- **Actual cause:** `Image_LoadLMP` calls `Q_stristr(name,"palette.lmp")`, which
  the build mapped to `strcasestr` via `-DHAVE_STRCASESTR=1`. That import
  resolved to an unusable placeholder in `libSceLibcInternal`; the indirect call
  jumped to it (hence the constant `rax==pc` at a fixed system address). It was
  the first `Q_stristr` on the file-load path, so it presented as a gfx bug.
- **Fix:** `HAVE_STRCASESTR=0` → Xash's portable `Q_stristr` from `crtlib`.
  Verify: `llvm-readelf --dyn-syms <elf> | grep -i strcasestr` returns empty.
- **General rule:** Principle 1 — an exported system symbol is not a working
  one; prefer the in-tree portable impl for non-standard helpers, and check the
  imported-symbol class (Principle 2, row 1) before app-level hypotheses.
- **Reference:** `projects/ps5-xash3d` (Phase 5 gate 2, `exp/engine-boot`).
