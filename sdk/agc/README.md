# Sanitized AGC compatibility subset

This directory is the compatibility facade retained for the historical private
GPU lab. The canonical reusable interface is
`projects/ps5-agc-gears/include/`; this directory contains no independent copy
of the common AGC declarations.

`include/ps5_agc.h` includes the public canonical header and adds only aliases
and experimental imports needed to rebuild archived stages.

The NIDs are generated from the exported names by the PS5 SDK tooling. The
research gates additionally pin the firmware-12.02 dynamic-symbol mapping.
The bound-index trio is deliberately absent because only its names/NIDs—not
its complete native ABI—are currently validated.

New projects must consume the public project's headers and stubs. Only archived
legacy applications should include `sdk/agc/include`.

The Python readiness gate remains a regression suite and evidence index. It is
not required at application runtime, but should remain in CI while this API is
research-derived.

Run `make agc-sdk-check` from the `homebrew_ps5` root for the reusable API test.
