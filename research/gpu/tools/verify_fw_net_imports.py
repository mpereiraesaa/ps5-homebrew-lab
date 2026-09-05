#!/usr/bin/env python3
"""Cross-check native logger imports against an authorized firmware ELF view."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path


NID_SUFFIX = bytes.fromhex("518d64a635ded8c1e6b039b1c3e55230")
REQUIRED = (
    "sceNetConnect",
    "sceNetEpollControl",
    "sceNetEpollCreate",
    "sceNetEpollDestroy",
    "sceNetEpollWait",
    "sceNetErrnoLoc",
    "sceNetGetsockopt",
    "sceNetSend",
    "sceNetSetsockopt",
    "sceNetShutdown",
    "sceNetSocket",
    "sceNetSocketClose",
)


def nid(name: str) -> str:
    digest = hashlib.sha1(name.encode("ascii") + NID_SUFFIX).digest()[:8]
    return base64.b64encode(digest[::-1]).decode("ascii")[:11].replace("/", "-")


def symbols(path: Path) -> str:
    return subprocess.run(
        ["objdump", "-T", str(path)], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware-elf", required=True, type=Path)
    parser.add_argument("--app-elf", required=True, type=Path)
    args = parser.parse_args()

    firmware = args.firmware_elf.read_bytes()
    app = args.app_elf.read_bytes()
    firmware_symbols = symbols(args.firmware_elf)
    exports = set(re.findall(r"\b([A-Za-z0-9+\-]{11})#[A-Za-z]#[A-Za-z]\b",
                             firmware_symbols))
    checks = []
    for name in REQUIRED:
        value = nid(name)
        checks.append({
            "name": name,
            "nid": value,
            "firmware_export": value in exports,
            "app_import": value.encode("ascii") in app,
        })
    names = {
        "firmware_soname": b"libSceNet.prx" in firmware,
        "firmware_library": b"libSceNet" in firmware,
        "app_soname": b"libSceNet.prx" in app,
        "app_library": b"libSceNet" in app,
    }
    valid = all(c["firmware_export"] and c["app_import"] for c in checks)
    valid = valid and all(names.values())
    result = {
        "schema": 1,
        "firmware_elf_sha256": hashlib.sha256(firmware).hexdigest(),
        "app_elf_sha256": hashlib.sha256(app).hexdigest(),
        "module_names": names,
        "imports": checks,
        "valid": valid,
    }
    print(json.dumps(result, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
