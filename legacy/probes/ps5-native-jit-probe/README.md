# PS5 native JIT probe

Tests executable anonymous memory inside the `hbldr` BigApp host:

- anonymous `RW` mapping followed by `RW -> RX` and execution;
- a second `RX -> RW -> RX` dynamic recompilation cycle;
- direct anonymous `RWX` mapping and execution.

Results are written to `/data/ps5-native-jit-probe.log`. The probe then closes
its `FAKE00000` BigApp automatically.
