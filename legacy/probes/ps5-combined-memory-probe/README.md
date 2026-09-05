# PS5 combined memory probe

Holds and verifies 320 MiB of anonymous heap plus a 64 MiB dual-mapped JIT
cache while allocating, mapping and touching a configurable Main Direct Memory
arena. The default direct arena is 3072 MiB; set `PS5_DIRECT_MIB` in `shsrv`
before launching to select another value, capped at 4096 MiB.

It also holds a 128 MiB 4K double-buffer allocation, AudioOut, DualSense and
eight busy CPU workers for up to three minutes. Heap, Direct Memory and JIT are
sampled once per second. OPTIONS exits early. Results go to
`/data/ps5-combined-memory-probe.log`.
