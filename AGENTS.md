# Agent guidance

## Canonical development tools

- Run `make check` before committing lab changes.
- Use `projects/logging_server` and the `ps5log/1` contract for
  machine-readable runtime evidence. Filesystem and USB logging are deprecated.
- Use `tools/ps5_remoteplay.py` for visual access to the owned PS5 through
  Chiaki. The normal path reuses the registered `PS5-054` target and launches
  the stream directly from the CLI; discovery, pairing and the Chiaki main
  window are not part of each iteration:

  ```sh
  python3 tools/ps5_remoteplay.py stream --host "$PS5_HOST" --nickname PS5-054
  python3 tools/ps5_remoteplay.py screenshot
  python3 tools/ps5_remoteplay.py record --seconds 30
  python3 tools/ps5_remoteplay.py record-demo --name "Xash3D Phase 5"
  python3 tools/ps5_remoteplay.py stop-stream
  ```

- `stream` uses a private temporary Chiaki configuration containing only the
  selected registered console, cleans a stale CLI-owned stream when necessary,
  and never places pairing credentials on the command line. Build or pair only
  for initial setup or recovery; see `docs/REMOTEPLAY.md`.
- Remote Play captures belong under the ignored
  `research/gpu/captures/remoteplay/` tree unless the owner explicitly
  selects and audits one for publication.
- Use `record-demo` for operator-controlled community presentations. It records
  until Enter or `Ctrl+C`, produces a web-compatible MP4, and keeps the raw
  capture private until the owner reviews it for visible personal information.
- Do not leave Chiaki as the active window after automation. The wrapper
  restores the prior workspace focus without overriding a later user focus
  choice. `stop-stream` targets only a PID whose process identity is verified
  as the CLI-owned Chiaki stream.
- Pairing output contains a PIN and PSN Account ID. Never commit, archive,
  quote in logs or send those values to telemetry. Use
  `docs/REMOTEPLAY.md` for the pinned Headless LinkDev workflow.
- A screenshot or video proves visual output only. Renderer completion,
  ownership and cleanup still require artifact identity plus structured GPU and
  VideoOut telemetry.

## Repository workflow

- Public application work belongs in independent repositories under `projects/`;
  `ps5-agc-gears` is the frozen graphics demo and `ps5-xash3d` is the active
  renderer integration.
- Both the lab and public projects use topic branches and pull requests; never
  push changes directly to `main`.
- Keep third-party source and generated artifacts out of the lab repository.
