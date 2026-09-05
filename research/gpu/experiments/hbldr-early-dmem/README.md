# Early-host passive DMEM probe

This is a separate, disposable launcher artifact. It embeds only
`ps5-agc-phase0c-driver-dmem.elf` and stops the firmware-12 NPXS40106 host at
`e_entry + 0x2d`, immediately before its constructor dispatcher.

It does not replace the deployed `shsrv`, modify application metadata, unmap
GPU memory, patch AGC constants, create an AGC context, or submit commands.

The single question is whether `sceAgcDriverGetDmem` returns the preferred
full-layout base (`0xfe0040000`) before host constructors run, instead of the
relocated base observed through normal hbldr (`0xff0040000`).

Run only with no commercial BigApp active. After the result, identify and
close exactly `FAKE00000`, then verify ports 744, 2121, 2323, and 9021.
