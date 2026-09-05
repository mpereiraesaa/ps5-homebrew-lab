# Native AGC phase-0 app

Local build experiment for running the passive AGC module-lifecycle probe as
its own fSELF BigApp instead of injecting it into the NPXS40106 streaming host.

The fSELF/auth-info recipe comes from the payload SDK `install_app` sample. The
title is isolated as `AGCP12002`, which follows the observed
four-letter/five-digit Title ID shape. Building does not install or modify the
PS5.
Installation remains a separate, gated operation because it writes application
directories and registration state.

This first eboot still performs only AGC sysmodule load/unload. It has no
VideoOut, allocation, AGC export calls, command buffers, PM4 or submit.

`verify_artifacts.py` enforces matching metadata, the observed `AAAA99999`
Title ID shape, 16-KiB-aligned non-empty RX/R/RW `PT_LOAD` segments and the
fake-SELF container magic. It also proves that the entrypoint belongs to the
RX segment, rejects writable+executable loads and `PT_DYNAMIC`, and rejects
known PM4 packet signatures or queue/submit/VideoOut names. Required lifecycle
names must remain present. The explicit eight-byte data anchor exists only to
prevent the linker from dropping the RW load segment.

Both local metadata files intentionally use the SDK sample's minimal three-key
schema (`applicationCategoryType`, `localizedParameters`, `titleId`). Earlier
local metadata added content/attribute/SDK fields that the reference does not
need. This isolates one variable for a future daytime registration experiment;
it does not establish that metadata caused `0x80aa001a`.

`make` builds both the isolated fSELF and a separate registration helper.
There is deliberately no install/test target: deployment requires a healthy
console, a collision check for `AGCP12002`, backups of any pre-existing title
directories, and an explicit staged rollback path. The eboot writes its small
result log to `/data/ps5-agc-native-phase0.log` and truncates it on each run.
After the module lifecycle completes, it waits eight seconds before exiting so
the supervisor can positively observe the BigApp identity. The AGC module is
already unloaded during this observation window.

The supervisor's `install-agc-phase0` action is intentionally transactional
only until AppInstUtil registration. It requires the read-only preflight,
creates only the previously absent `AGCP12002` paths, verifies every upload by
remote size, and removes only paths created in that invocation if an upload or
registration fails. Once registration succeeds it never attempts speculative
uninstall or deletion; any later error leaves the isolated title intact for
manual review.

## Firmware 12.02 result

An earlier revision used experimental ID `FAKE0AGC0`, whose suffix violates
that five-digit form. Its files were uploaded and verified and the required batch
`sceAppInstUtilAppInstallAll()` path returned `0`. Nevertheless,
`sceSystemServiceLaunchApp("FAKE0AGC0", ...)` returned `0x80940005` twice and
no BigApp was created. Treat successful batch registration and launchability
as separate gates. Do not retry the standalone title until its appmeta,
category and firmware-12 indexing contract are resolved. The same passive
module-lifecycle probe was already validated through `hbldr -> FAKE00000`.

The replacement build uses `AGCP12002`. Both remote paths were confirmed absent
read-only before installation; file verification and AppInstUtil registration
then succeeded. Its single launch attempt advanced past the old error but was
rejected with `0x80aa001a`; no BigApp or probe log was created and all services
remained healthy. The launch action was removed from the unattended supervisor
until the fSELF/app-data contract is understood. Neither installed experimental
title is retried, overwritten, or removed.

Post-failure comparison with the SDK reference found that the installed build
had only RX and R `PT_LOAD` segments: its empty `.data` section had been dropped.
The local source now retains an eight-byte data anchor and rebuilds to three
non-empty RX/R/RW segments, matching the reference shape. This corrected fSELF
has **not** been uploaded over the registered title and has not been launched.
An unmodified SDK reference was rebuilt separately under `/tmp`: both containers
now advertise six SELF metadata entries, embed four ELF program headers and
process three 16-KiB-aligned load segments in RX/R/RW order. Remaining size,
entrypoint and payload hashes differ naturally with program content. The local
verifier also proves that the program headers embedded in the fSELF match the
source ELF exactly; this is structural parity, not launchability proof.

## Clean second-title experiment

`AGCP12003` preserves `AGCP12002` as historical evidence and packages the
corrected three-load-segment image under a separate experimental ID. Its launch
and close helpers are compiled with that exact identity. Local verification is
recorded in `research/gpu/captures/agc-native-phase0-v2-local-proof.json`.
The console must still pass an absence/collision check before any directories
are created; local verification alone proves neither installation nor launch.

On firmware 12.02, `AGCP12003` installed and registered with return zero, and
`sceSystemServiceLaunchApp` accepted the request with app ID `0x8018`. No
BigApp or probe log appeared. A single subsequent launch from Home reproduced
the pre-entry failure visibly as system-software error `CE-108262-9`; the
interface disappeared temporarily while the background remained visible.
All payload services survived and no BigApp remained. Further launches of both
experimental IDs are forbidden. The corrected RX/R/RW shape therefore does
not satisfy the native PS5 loader contract: the embedded image remains a
minimal static `ET_EXEC` (`e_type=2`, four program headers), whereas the
observed working PS5 game is SCE ASLR executable `e_type=0xFE10` with fourteen
program headers. A future experiment must prove SCE process/dynamic metadata
parity locally before deployment.
