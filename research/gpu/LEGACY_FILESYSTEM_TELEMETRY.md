# Legacy filesystem telemetry

This directory contains evidence and source snapshots from experiments that
predate the `ps5log/1` network contract. References to `/download0`, USB, FTP
log retrieval or per-record `fsync` below `research/gpu/` and in frozen native
probe sources are historical facts, not supported operations.

The active AGC path is deliberately narrower:

- build only with `legacy/apps/agc-native-sce/build_stage_f.sh` (variants F-I);
- package the private `/app0/dev.conf` selected at build time;
- receive records with `projects/logging_server/server/ps5logd.py`;
- launch, capture and validate with `tools/agc_net_monitor.py`;
- close automatically only from a complete local `ps5logd` manifest.

Legacy native build entry points terminate with a deprecation error. Legacy
Stage B/C/E actions are not exposed by `night_supervisor.py`. The old
`capture_agc_defaults_cpu.py` remains solely to reproduce its already-recorded
read-only parser analysis; it is not part of runtime monitoring.

No new console filesystem logging implementation may be added to an active
runtime. `make agc-observability-check` enforces this boundary.
