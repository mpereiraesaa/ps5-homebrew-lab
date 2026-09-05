# PS5 jitshm dual-mapping probe

Experimental probe for Sony's JIT shared-memory interfaces. It requests a
16 MiB object and maps the same physical pages twice: RW for code generation
and RX for execution. It validates the first and last pages without using RWX
or runtime `mprotect()` transitions. It then performs 100,000 rewrite/execute
cycles per worker with 1, 4, 8, 12 and 16 concurrent workers.

The ABI is inferred from the PS4 interfaces and must be validated empirically
on PS5. Results go to `/data/ps5-jitshm-probe.log`.
