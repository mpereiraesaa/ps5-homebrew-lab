# PS5 (Prospero) porting playbook

This is a **cross-project** document. It applies to every project under
`projects/` that ports third-party code to native PS5, present and future.
Read it before starting a new port and before spending a day bisecting a
crash. Keep it alive: when a blocker is solved, add a post-mortem here and, if
it generalizes, a rule.

The lesson that created this file: a "filesystem crash loading `gfx/palette.lmp`"
turned out to be an unusable `strcasestr` import routed by the SDK stub to
`libScePosixForWebKit`. It cost a full session of reactive, app-level
hypotheses (buffer overflow, fd
mismatch, null memory pool) because the **class** of the bug was never checked
first. This playbook exists so the next agent checks the class first.

## Principle 1 — a system symbol that is *exported* is not *working*

Prospero system libraries (`libSceLibcInternal`, `libkernel`, …) export many
symbols that are placeholders, aliases, or subtly wrong for the payload
runtime. Treat "provided by `libSceLibcInternal`" in a symbol-gap report as a
**yellow flag, not a green check**.

- When the port already ships a portable, self-contained implementation of a
  libc-ish helper behind a `HAVE_X` flag, use it as the safe starting point
  until the target implementation has an execution test. **Keep the system
  implementation when that smoke test passes**; select the fallback only for
  a failing or still-unverified symbol. The objective is a measured Prospero
  contract, not blanket replacement of `libSce*`.
- This is not "always avoid the system lib." Core, standard, widely-exercised
  functions are usually fine (`strcasecmp`, `strncasecmp`, `strnlen`,
  `strlcpy`, `strlcat`, `malloc`, `pthread_*`, sockets, `clock_gettime` all
  work here). Decide **case by case**, biased toward the in-tree impl when the
  function is non-standard (e.g. `strcasestr`) or unverified.
- **Verify by execution, not by the symbol table.** A three-line smoke test at
  boot that actually calls the symbol on real input catches this in minutes.
  A grep of `--dyn-syms` only tells you it is *imported*, not that it *works*.
- The platform is not a black box: when a call fails or its provider/ABI is
  ambiguous, inspect the matching firmware dump in Ghidra and reconcile its
  control flow with the runtime fault. Static analysis explains a result; it
  does not replace the hardware smoke test that accepts a symbol.

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
- `libSceLibcInternal` `getcwd()` **faults**;
  `libScePosixForWebKit`'s `strcasestr` route is **unusable**.
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
- **`MAP_FIXED` silently replaces live mappings, and `MAP_EXCL` is
  ignored.** Measured: two `MAP_FIXED|MAP_EXCL` requests for the same
  address both succeeded, and a plain `MAP_FIXED` over a live mapping
  overwrote its contents. FreeBSD's `MAP_EXCL` exists precisely to make a
  fixed request fail rather than clobber, and it does not work here, so
  `MAP_FIXED` is unusable unless the range has been proven free first.
  Prefer the **hint form** — a plain `mmap` with an address argument and no
  `MAP_FIXED` — which cannot displace anything, is honoured exactly when the
  range is available, and can simply be checked afterwards.
- **Low addresses are freely available, and `MAP_32BIT` is not.** The low
  4 GiB of a process is nearly empty — the image occupies roughly
  `0x400000`–`0x584000` and essentially nothing else — and a hint anywhere
  above that is granted exactly, up to at least **3 GiB contiguous** below
  4 GiB. `MAP_32BIT` is ignored and returns high memory. `KERN_PROC_VMMAP`
  via `sysctl` works and is the way to see the layout before asking.
  Relevant to any port whose payload uses 32-bit pointers.
- **A low mapping can be made executable, including writable and
  executable together.** `mprotect` to `r-x` and to `rwx` both succeeded on
  an anonymous low mapping. Measured in an `elfldr` payload, which is more
  privileged than a title; confirm in the context that will actually run
  before depending on it.
- **The page size is 16 KiB, not 4 KiB**, measured through
  `sysconf(_SC_PAGESIZE)` (which works) and confirmed by `mprotect`
  behaviour. Anything that assumes 4 KiB will appear to work on a host and
  fail here. In particular `munmap` and `mprotect` operate on 16 KiB
  boundaries, and **FreeBSD's `munmap` truncates a misaligned address
  downward and extends the length to match** — so a misaligned trim does
  not fail, it releases memory you are still using. Round every reservation
  up to whole pages before trimming it.
- **The LDT is unavailable, so 32-bit machine code cannot run.** Every
  `sysarch` LDT operation returns `EINVAL` on FW 12.02 — reads and writes,
  explicit indices and `LDT_AUTO_ALLOC` alike — while a control operation
  (`AMD64_GET_FSBASE`) succeeds, so `sysarch` itself works and only the LDT
  ops are refused. `machdep.max_ldt_segment`, the sysctl that would size
  the table, does not exist (`ENOENT`), which points at the support being
  compiled out rather than set to zero: there is no knob to turn on. The
  matrix was run from `elfldr`, which is more privileged than a title, so
  this is kernel-wide and not a sandbox restriction. Consequence:
  compatibility mode cannot be entered, WoW64-style ABI thunking is out,
  and a port with a 32-bit payload needs JIT recompilation or a 64-bit-only
  scope. Measured 2026-09-08 by `prospero-win` gate 0.2a; details in its
  `docs/COMPAT32_PHASE0A.md`, and the reusable probe is
  `tools/ldt-probe/`.
  The mechanism, for whoever revisits this: a thread reaches compatibility
  mode only by far-jumping to a code descriptor with `L` clear and `D/B`
  set. User code cannot write a descriptor table, so the kernel has to
  install one, and on FreeBSD amd64 `sysarch(I386_SET_LDT, ...)`
  (`amd64_set_ldt`) exists for exactly that; the pinned payload SDK even
  declares it (`x86/sysarch.h`, `SYS_sysarch` 165) alongside
  `I386_SET_FSBASE` for 32-bit TLS. Those declarations describe FreeBSD,
  not what Sony's kernel permits — a header declaration is weaker evidence
  than an export, and here it turned out to be worth nothing at all.
- Working, verified: `socket`/`bind`/`sendto`/`poll`, `pthread_*`,
  `clock_gettime`, `sceKernelOpen`/`Read`/`Write`/`Close`/`Stat`/`Getdents`,
  `strcasecmp`/`strncasecmp`/`strnlen`/`strlcpy`/`strlcat`. Xash3D run
  `20260907T162442485Z_PPSA99996_xash3d-engine_0xb88fc0cf77a3` explicitly
  called `strcasecmp`, `strnlen`, `strlcpy` and `strlcat` on representative
  strings before engine startup, then spawned `c1a0` and closed cleanly.

## New-port pre-flight checklist

- [ ] List every libc/syscall symbol the port will depend on; for the
      non-standard ones, add a boot-time **smoke test** that calls each on real
      input and reports through `ps5log/1`.
- [ ] For every `HAVE_X`-style "use system impl" flag, begin conservatively,
      run a real target smoke test, and record the result. Keep a passing
      system implementation enabled; select the port fallback for a failing
      or unverified symbol.
- [ ] After the first link, dump `--dyn-syms` and review every imported symbol:
      is each one known-good, or merely exported?
- [ ] Keep the fd lifecycle in one namespace: if you shim `open` to
      `sceKernelOpen`, verify `read`/`lseek`/`write`/`close`/`fstat` on that fd
      (they worked here via libc, but verify per port).
- [ ] Reuse the lab's evidence discipline: `ps5log/1` markers, immutable run
      manifests, one variable per hardware run.

The Xash3D implementation is the current reference: `XASH_LIBC_SMOKE=1`
forces real boot-time calls, while `xash/tools/audit_dyn_imports.py` combines
the linked ELF, its needed libraries, SDK-stub providers and a hardware
evidence ledger. It fails banned imports and leaves every unproven entry
labelled `EXPORTED ONLY`.

## Blocker post-mortems

Record every non-trivial blocker here with this shape, so the next agent
recognizes the pattern instead of re-deriving it.

**Template:** *Symptom* (observable, incl. fault signature) · *False leads*
(what looked plausible and was wrong) · *Actual cause* · *Fix* · *General rule*
(what to check first next time) · *Reference* (project, PR, run id).

### EINVAL read as a platform limit when the argument was wrong (prospero-win, 2026-09-08)

- **Symptom:** `sysarch(I386_SET_LDT, ...)` returned `EINVAL` from a title,
  and that was written up as "the firmware refuses LDT descriptors".
- **Actual cause of the *evidence*:** the call asked for two descriptors in
  one go with `LDT_AUTO_ALLOC`. FreeBSD's amd64 `amd64_set_ldt` honours that
  sentinel only for a single descriptor; with `num=2` it takes the
  range-check path, where `start=0xffffffff` is refused as `EINVAL`
  regardless of policy. The errno was reporting a malformed argument, which
  is exactly what `EINVAL` means, and the conclusion drawn from it was not
  supported.
- **What actually settled it:** three cheap additions. A **control**
  operation known to work (`AMD64_GET_FSBASE` succeeded, proving `sysarch`
  dispatches); the **full argument matrix** (the correct single-descriptor
  call, explicit indices, and a pure `I386_GET_LDT` read all failed
  identically, which is the signature of a zero-sized table rather than one
  bad shape); and a **privilege comparison** (the same matrix from `elfldr`
  behaves identically, so it is kernel-wide, not a sandbox rule). The
  absent `machdep.max_ldt_segment` sysctl then explained why.
- **General rule:** `EINVAL` is the weakest possible evidence of a platform
  limit, because it is also what your own bad argument produces. Before
  recording any refused platform call as a limit, add a control operation, a
  matrix of argument shapes, and — where the environment allows it — the
  same probe at a different privilege level. `EPERM` or `ENOSYS` would have
  been worth more on their own; `EINVAL` is worth nothing until the
  arguments are above suspicion.
- **Reference:** `projects/prospero-win` gate 0.2a, `tools/ldt-probe/`.

### A misaligned munmap released live memory (prospero-win, 2026-09-08)

- **Symptom:** `SIGSEGV`, `code=1` (`SEGV_MAPERR`), `addr=0x200088000`,
  `pc=0x20001c210` — a program counter inside a freshly mmap'd *data*
  region, so execution had been transferred into memory that contains no
  code. Reproducible, and only on the console: every host test passed.
- **False leads:** the fault address equalled the `rsp` reported from
  `uc_mcontext`, which reads as a stack overflow. It was not: a stack
  anchor printed from `main` showed the real stack three orders of
  magnitude away, at `0x7eeffbd54`. `mc_rsp` is simply not populated
  reliably for a SEGV here, exactly as the Xash3D backend already warns.
  `sysconf` was also suspected as an unmeasured import; it works and
  returns 16384.
- **Actual cause:** a reservation helper over-allocated, aligned, then
  trimmed the padding with `munmap`. The reservation size came from a PE
  image's `SizeOfImage`, which is section-aligned to 4 KiB — `0x7000` here
  — so the tail address was not a multiple of the 16 KiB page. FreeBSD's
  `munmap` truncates a misaligned address **down** and extends the length,
  so instead of releasing padding it released the last three pages of the
  live region. Later writes then ran off the end of a partially unmapped
  reservation.
- **Fix:** round the reservation up to whole pages before computing either
  trim, so both ends fall on page boundaries.
- **General rules:** (1) the page size here is 16 KiB, and any size derived
  from another format's alignment — a PE section, an ELF segment, a texture
  row — is not automatically a whole number of pages; (2) never ignore the
  return value of `munmap`/`mprotect`, because the failure mode is silent
  and delayed; (3) `mc_rsp` in a signal context is not trustworthy, so
  print a stack anchor from a known frame before believing a stack
  diagnosis; (4) stream evidence as it is produced — the first two runs
  buffered their records and a crash took every one of them, leaving a
  transcript that ended with no indication of where it stopped.
- **Reference:** `projects/prospero-win`, gate 0.1, accepted run
  `20260908T111650513Z_PPSA99995_prospero-win_0xf65743b2ac43`.

### strcasestr via libScePosixForWebKit is unusable (Xash3D, 2026-09-07)

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
  was routed by the SDK stub to `libScePosixForWebKit.sprx`; its runtime target
  was unusable and the indirect call jumped to it (hence the constant `rax==pc`
  at a fixed system address). It was
  the first `Q_stristr` on the file-load path, so it presented as a gfx bug.
- **Fix:** `HAVE_STRCASESTR=0` → Xash's portable `Q_stristr` from `crtlib`.
  The accepted client fSELF
  `b622cec5561f1cfb49731e6cad9b58cad49480afd970ee8fe9e6e858952666dc`
  (linked ELF
  `f4287a6f817ecdab19a1c8a60433cf3c6f33324e767a51b32aa543e8bb311c11`)
  loaded and expanded the palette, returned from `Image_LoadLMP`, and loaded
  the Half-Life DLL in run
  `20260907T154452596Z_PPSA99996_xash3d-engine_0xb663524c9f61`.
  `llvm-readelf --dyn-syms <elf> | grep -i strcasestr` is empty; the build now
  rejects any ELF that reintroduces the import. A later pre-flight ELF
  `f40d7c2b3cad0f56e96ef974785cbc53b4c6512bf3dd05b871ef985ed4aec7a1`
  independently repeated the empty-symbol check while directly importing and
  passing the other four optional string helpers on hardware.
- **General rule:** Principle 1 — an exported system symbol is not a working
  one; prefer the in-tree portable impl for non-standard helpers, and check the
  imported-symbol class (Principle 2, row 1) before app-level hypotheses.
- **Reference:** `projects/ps5-xash3d` (Phase 5 gate 2, `exp/engine-boot`),
  smoke run `20260907T162442485Z_PPSA99996_xash3d-engine_0xb88fc0cf77a3`,
  fSELF `3aa7835949b1dd0f98de9fc8d6a9dec36fc16c68460617304b20eabb7cb5ce9f`.
