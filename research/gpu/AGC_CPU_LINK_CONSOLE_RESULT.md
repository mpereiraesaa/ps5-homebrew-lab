# AGC CPU constructor/link result — FW 12.02

On 2026-09-04 the native `PPSA99998` probe completed one bounded CPU-only run.
Both shader constructors and `sceAgcLinkShaders(..., primitive_type=6)` returned
zero. The console produced the exact CX and UC SHA-256 values previously
obtained from the isolated host oracle. External canaries remained intact and
LinkShaders changed neither constructed header nor code storage.

The probe scrubbed all mutable copies, unloaded the AGC sysmodule, emitted its
safe parking marker, and was closed by exact title. No BigApp remained and
ps5debug, FTP, shsrv and elfldr were stable in two post-close observations.

## Reproduction gates

- `legacy/apps/agc-native-sce/verify.py` pins all four private inputs by size/hash and
  verifies the SCE container, imports and prohibited API/packet absence.
- `research/gpu/tools/verify_agc_link_gate.py` supplies one positive planner
  case, 17 negative planner cases, nine isolated transform cases and 18 unit
  tests.
- `tools/night_supervisor.py ... run-agc-cpu-link` performs the recoverable
  eboot swap, ShadowMountPlus reload, launch, sanitized result validation and
  safe exact-title close.

## Postmortem: FTP false collision

The first automated attempt stopped before writing because the console FTP
server reports `SIZE(-1)` for a missing hidden file as unsigned
`UINT64_MAX`, rather than a 550 error. The transaction interpreted that value
as an existing staging and backup file. No swap, reload or launch occurred.
`file_exists()` now treats only that sentinel as absent; the subsequent run
completed normally. The previous eboot remains retained as a recoverable
backup on the console.

No shader bytes, register values, dumps or proprietary source fragments are
recorded in these results.
