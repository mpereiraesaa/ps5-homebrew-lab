# PS5 AGC phase 0

Lowest-risk AGC runtime capability probe. It asks the internal sysmodule loader
to load AGC (`0x80000094`), records the result, and unloads it when successful.

It does not open VideoOut, allocate direct memory, create command buffers,
resolve or call AGC exports, submit GPU work, or emit PM4. A ten-second watchdog
terminates only the probe process if the module lifecycle blocks.

`ps5-agc-phase0b-hold.elf` holds the successfully loaded module for 20 seconds
so ps5debug can capture its mappings. It otherwise performs the same passive
lifecycle. Its watchdog deadline includes the intentional hold plus ten seconds
for the actual load/unload calls.

`ps5-agc-phase0c-driver-dmem.elf` is narrower still: it loads only
`libSceAgcDriver`, resolves the already-observed GetDmem export by NID, records
the returned base and size, and unloads it. It does not load `libSceAgc`, create
a context or queue, allocate GPU memory, touch VideoOut, emit commands, or
submit work. Its purpose is to explain the `FS Table offset has shifted`
warning before any later AGC API is attempted.

Hardware result on firmware 12.02 under `hbldr -> FAKE00000`:

```text
GetDmem rc=0
base=0xff0040000
size=0x1b0000
FS-table expected-base match: no
```

The expected base embedded in this firmware's `libSceAgc` is `0xfe0040000`,
so the host's region is shifted by exactly 4 GiB. The probe and driver unloaded
cleanly; the remaining `FAKE00000` container was then identified and closed by
the restricted supervisor. Do not progress to AGC context or submission in
this host based only on a successful module-load return code.

`ps5-agc-phase0d-dma-buildonly.elf` is a CPU-only audit of the recovered
four-byte label-initialization packet. It reconstructs the exact seven DWORD,
patches only DWORD4/5 to a private stack address, verifies immutable fields and
two canaries, logs the result, and exits. It deliberately does not load AGC or
AGCDriver, allocate direct memory, create a queue, call VideoOut, or submit the
array. It can run through the validated `hbldr -> FAKE00000` route only after
the foreground game has been closed and health rechecked.

`ps5-agc-phase0e-driver-queue-state.elf` loads only AgcDriver and resolves the
known `SubmitDcb` export solely to derive and validate the firmware module
base. It checks the exact 12.02 `SubmitDcb` and `CreateQueue` wrapper bytes,
then reads a bounded set of fields from the driver's default graphics-queue
object. It never calls either wrapper, never loads `libSceAgc`, and emits no
command or submit. Pointers are reported only as yes/no state so runtime
addresses are not persisted.

Phase 0E is retained as a negative experiment: `dladdr` returned no module base
in this host runtime. Do not rerun it. Phase 0F replaces that mechanism with a
25-second passive hold after loading AgcDriver. During the hold the supervisor
identifies exactly our `FAKE00000` process, enumerates mappings and reads the
known wrapper plus 0x50 bytes of queue metadata through ps5debug. It performs
no attach, target write or remote function call, waits for a clean driver
unload, and only then closes the host.

Phase 0G tested one final in-process discovery mechanism and is also retained
only as a negative experiment. It resolved the `SubmitDcb` NID, but attempting
to read the purported function address produced neither the expected signature
nor a recoverable fault/final log before the supervisor timeout. The supervisor
identified and cleanly closed exactly `FAKE00000`, then passed two health
checks. This proves that the `dlsym` value cannot be treated as a directly
readable code pointer in this host. Phase 0G is excluded from the default build
and supervisor CLI and must not be rerun.

`ps5-agc-phase0h-regshadow-info.elf` is an independent passive gate. It loads
only AgcDriver, resolves the public `sceAgcDriverGetRegShadowInfo` NID and
supplies a private 40-byte output buffer. Firmware 12.02 rejects a nonzero
process class before copying the output, so success demonstrates the
class-zero gate without deriving a module base or reading private pointers.
The probe records only a count of nonzero QWORDs, never their values. It does
not load libAgc, issue an ioctl itself, create or destroy a queue, allocate GPU
memory, emit PM4, or submit. A ten-second watchdog and exact-title supervisor
cleanup contain one execution.

`ps5-agc-phase0i-module-queue-state.elf` replaced the failed address discovery
with `sceKernelGetModuleList`/`sceKernelGetModuleInfo` on the calling process.
Its one hardware run found exactly one AgcDriver among eight modules and proved
that the queue range belonged to a readable segment. The executable-protection
gate did not accept the raw protection encoding, so it stopped before wrapper
or queue reads, unloaded cleanly, and the supervisor closed the exact host.
No queue call, write, attach or submit occurred. Phase 0I is retired and must
not be rerun. Phase 0J may log only relative segment offsets, sizes and raw
protections before any later queue-read attempt is designed.

Phase 0J completed that metadata-only inventory once. The four tuples were
`(0,0xc000,4)`, `(0xc000,0x8000,1)`, `(0x14000,0x4000,1)` and
`(0x18000,0xc000,3)`, exactly matching the geometry of the authorized native
dumps. It performed zero code/data reads beyond the module-info output itself,
unloaded cleanly and was retired. Raw `4` is the executable mapping class in
this API, rather than the `R|X=5` mask assumed by 0I. That result defined 0K's
gate: require the complete tuple set and read only bounded queue fields inside
segment 3, never the execute-only segment.

Phase 0K performed that final read-only queue observation once. It required the
exact four segment tuples, then read only 25 bytes from the queue object in
segment 3. It observed header size `0x38`, queue type 0, non-null token and lock,
and created sentinel 1. Thus the hardware-specific gate is now
`hardware_queue_initialized=true`. It read no code, called no queue function,
performed no write or submit, unloaded cleanly, and was retired from the
supervisor. Do not rerun 0K. This result does not prove GPU access or coherency
for homebrew-owned direct memory; those remain the next independent gates.

Phase 0L then proved the complete pre-submit layout without executing it. While
the same validated queue state was live, it allocated and mapped one 128 KiB
Main Direct Memory region (`type=3`, `prot=0x33`), placed the exact 60-byte
DMA_DATA+RELEASE_MEM stream at offset zero, a four-byte canary at `+0x1000`,
and a fence initialized to one at `+0x1008`. All ranges were non-overlapping;
the mapping was unmapped, released, and AgcDriver unloaded with zero returns.
No AGC export, queue call, or submit occurred. The one-shot supervisor action
was retired and 0L must not be rerun. GPU visibility and coherency are still
unproven; only a later bounded execution can establish them.

Phases 0N and 0O isolated the direct-memory policy mismatch without loading
AGC. 0N proved that `type=0x0c` allocation is available but a null requested VA
with `prot=0xf2, flags=0x10` is rejected. 0O first used
`sceKernelReserveVirtualRange`, then mapped 128 KiB of type `0x0c` memory with
that exact protection/flag pair at the reserved VA. The address was preserved,
CPU read/write canaries passed, and unmap/release returned zero. Both ended with
`submitted=no`, exact-title cleanup and stable health; both supervisor actions
are retired and must not be rerun.

`ps5-agc-phase0m-first-submit.elf` is now a local **draft only** and is not
approved for deployment. It is excluded from `all` and has no supervisor
action. The draft submits exactly 15 DWORDs against private memory and treats
only `fence==0 && target==0` as success. Once the submit call begins, every
uncertain outcome—including a nonzero return, call watchdog, or fence timeout—
parks forever while retaining the process, driver and mapping. Automation must
not close `FAKE00000` in that state. Static policy is captured in
`agc-phase0m-draft-safety.json`; this does not constitute hardware execution.
The draft now uses the phase-0O-proven fixed-VA allocation policy
(`ReserveVirtualRange`, type `0x0c`, `prot=0xf2`, flags `0x10`) instead of its
older type-3/`0x33` mapping. It remains unapproved and undeployed because the
first AGC command fetch is still the hazardous boundary.
Its pre-submit gate now also requires the exact class-0 state proven by 0P:
process class 0, selector 0, callback `module_base+0x1100`, and a zero lazy
registration counter. This ensures any future execution follows the statically
pinned first-submit registration path rather than an unknown reused state. The
compiled draft remains disabled and its safety manifest still says
`approved_for_deployment=false`.
The verifier additionally proves that the stream, target and 8-byte fence are
aligned, non-overlapping and inside one mapping, and imports the game-derived
ownership contract (`CPU 1 -> RELEASE_MEM data_sel 2 -> GPU 0`). This removes
layout ambiguity but deliberately leaves
`homebrew_gpu_visibility_proven=false`: only the supervised label execution can
cross that hardware boundary.

Phase 0P measured the remaining backend selector once, using only three bounded
reads from AgcDriver's validated writable data segment. In `FAKE00000`, module
load logged a provisionally named `ready=0`; static cross-check establishes
that field as `process_class=0`. The selector was zero, while the callback pointer
correctly equalled `module_base+0x1100`. Static analysis proves that callback
uses a direct command-VA fast path for class 1, but class 0 does not fail: it
tail-calls a distinct implementation at `+0x1450`. Therefore the class-1 VA
lifetime proof cannot yet be generalized to our class-0 host, and phase 0M
must not run until `+0x1450` is closed statically. 0P unloaded and the
host closed cleanly with all services stable; it is retired and must not be
rerun. The next work is the static class-0 backend, not another live experiment.
