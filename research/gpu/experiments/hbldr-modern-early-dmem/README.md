# Modern standalone early-host DMEM launcher

This builds the currently validated `ps5-shsrv` hbldr implementation as a
separate ELF. It defaults to the already uploaded passive DMEM probe and stops
NPXS40106 at `e_entry + 0x2d`, before the host constructor dispatcher.

It neither replaces the running shell nor embeds a second payload copy. The
remote payload must already exist at
`/data/homebrew/bin/ps5-agc-phase0c-driver-dmem` and be size-verified before a
run.
