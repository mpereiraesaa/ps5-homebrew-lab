# BigApp control helpers

Small PS5 ELFs for unattended test orchestration. Each binary has a title ID
compiled into it and refuses operations outside that identity.

- `close-fake.elf`: cleanly closes `FAKE00000` only.
- `status.elf`: reports the actual running BigApp without changing state.
- `launch-san-andreas.elf`: launches San Andreas only when no BigApp is active.
- `close-san-andreas.elf`: cleanly closes San Andreas only.
- `launch-agc-gears.elf` / `close-agc-gears.elf`: operate only the standalone
  public demo identity `PPSA99997`.
- `launch-xash3d.elf` / `close-xash3d.elf`: operate only the PS5 Xash3D
  development identity `PPSA99996`.
- `launch-prospero-win.elf` / `close-prospero-win.elf`: operate only the
  Win32 compatibility layer identity `PPSA99995`.

Closing uses `sceSystemServiceKillApp` and polls for completion. It never sends
signals to arbitrary processes, never kills system processes, never replaces a
different active title and never re-launches an already running title.

`sceSystemServiceLaunchApp` is considered successful for any non-negative
return; on this firmware success returns the positive application ID.
The launch-context definition is the canonical 32-byte SDK layout and is
compile-time checked. `AGCP12002` deliberately has no launch helper while its
launch contract remains unresolved. A title-specific clean-close helper is
retained only for recovery if that exact BigApp is independently identified.
