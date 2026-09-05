# Agent guidance

## Canonical development tools

- Run `make check` before committing lab changes.
- Use `projects/logging_server` and the `ps5log/1` contract for
  machine-readable runtime evidence. Filesystem and USB logging are deprecated.
- Use `tools/ps5_remoteplay.py` for visual access to the owned PS5 through
  Chiaki:

  ```sh
  python3 tools/ps5_remoteplay.py build
  python3 tools/ps5_remoteplay.py stream --host "$PS5_HOST" --nickname PS5-054
  python3 tools/ps5_remoteplay.py screenshot
  python3 tools/ps5_remoteplay.py record --seconds 30
  ```

- Remote Play captures belong under the ignored
  `research/gpu/captures/remoteplay/` tree unless the owner explicitly
  selects and audits one for publication.
- Pairing output contains a PIN and PSN Account ID. Never commit, archive,
  quote in logs or send those values to telemetry. Use
  `docs/REMOTEPLAY.md` for the pinned Headless LinkDev workflow.
- A screenshot or video proves visual output only. Renderer completion,
  ownership and cleanup still require artifact identity plus structured GPU and
  VideoOut telemetry.

## Repository workflow

- Public renderer work belongs in `projects/ps5-agc-gears`.
- Both the lab and public renderer use topic branches and pull requests; never
  push changes directly to `main`.
- Keep third-party source and generated artifacts out of the lab repository.
