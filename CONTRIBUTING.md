# Contributing

Thanks for helping improve the PS5 Homebrew Lab. Contributions should be
small, reproducible and reviewable without access to proprietary material.

## Workflow

1. Open or select an issue that states the observable problem or capability.
2. Create a topic branch; never work directly on `main`.
3. Add or update a host regression for behavioral changes.
4. Run `make check` from the repository root.
5. Open a pull request describing scope, evidence and remaining limitations.

Hardware claims require an exact artifact identity and structured `ps5log/1`
telemetry. A screenshot or video is useful visual evidence but does not prove
GPU completion, resource ownership or teardown by itself.

## Publication boundary

Do not commit game executables or assets, firmware or vendor SDK content,
module/memory dumps, decompiler output, credentials, pairing data, private
captures, runtime logs or generated build products. Only project-authored
source, redistributable third-party material and reviewed factual notes belong
in pull requests.

Keep compatibility work reusable by subsystem. Target-specific observations
may guide a regression, but production code should not branch on a game name
or unpublished binary identity.

## Licensing

Each project carries its own license and notices. By contributing, you agree
that your change may be distributed under the license of the project it
modifies. Call out copied or adapted upstream code and preserve its attribution.
