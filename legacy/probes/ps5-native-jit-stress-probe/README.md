# PS5 native JIT stress probe

Bounded JIT validation for the `hbldr` BigApp environment. It validates every
16 KiB code page in caches of 1, 16, 64 and 128 MiB, then runs 1,000 W^X
rewrite/execute cycles concurrently on four threads, both with unsynchronized
permission changes and with `mprotect()` serialized by a mutex. Results are written to
`/data/ps5-native-jit-stress-probe.log`; `FAKE00000` closes automatically.
