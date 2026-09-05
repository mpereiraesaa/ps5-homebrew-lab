# PS5 GLSlim/Piglet staged probe

This produces four independent ELFs. They must be run in order and one at a
time. A later phase repeats all earlier checks because every ELF is a new
process.

1. `piglet-phase1-resolve.elf`: load GLSlim and resolve symbols only.
1b. `piglet-phase1b-sysmodule.elf`: load internal sysmodule `0x800000a9`,
    resolve symbols, close the handle and unload it; no EGL/Piglet calls.
2. `piglet-phase2-getconfig.elf`: additionally call only the read-only
   `scePigletGetConfigurationVSH` into a bounded opaque buffer.
3. `piglet-phase3-egl-init.elf`: additionally try `eglGetDisplay` and
   `eglInitialize`, then terminate.
4. `piglet-phase4-clear-swap.elf`: additionally try an ES2 window context,
   one blue clear and one swap, then destroy all EGL objects.

The probe never patches a module and never calls
`scePigletSetConfigurationVSH`. Every phase has a 12-second process watchdog
and writes `/data/ps5-piglet-probe.log`. Do not run phase 2+ until the previous
phase exited normally and its log was collected.

Build with `make`. There is intentionally no deploy/run target: execution on
the console is a separate, explicit manual action.
