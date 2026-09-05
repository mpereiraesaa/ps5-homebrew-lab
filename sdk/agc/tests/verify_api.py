#!/usr/bin/env python3
"""Validate the reusable sanitized AGC headers, stubs and deterministic NIDs."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SDK = ROOT / "sdk/agc"
CANONICAL = ROOT / "projects/ps5-agc-gears/include/ps5_agc.h"
NID_TOOL = ROOT / "third_party/ps5-native-app-boilerplate/.deps/native/ps5-payload-sdk/bin/prospero-nid"


def main() -> int:
    manifest = json.loads((SDK / "nids.json").read_text())
    wrapper = (SDK / "include/ps5_agc.h").read_text()
    if '../../../projects/ps5-agc-gears/include/ps5_agc.h' not in wrapper:
        raise SystemExit("lab compatibility header no longer includes canonical ABI")
    headers = CANONICAL.read_text() + "\n" + "\n".join(
        path.read_text() for path in (SDK / "include").glob("*.h"))
    stubs = "\n".join(path.read_text() for path in (SDK / "stubs").glob("*.c"))
    for library in manifest["library"].values():
        for name, expected in library.items():
            if re.search(rf"\b{re.escape(name)}\s*\(", headers) is None:
                raise SystemExit(f"missing public declaration: {name}")
            if re.search(rf"\b{re.escape(name)}\s*\(", stubs) is None:
                raise SystemExit(f"missing link facade: {name}")
            actual = subprocess.check_output([str(NID_TOOL), name], text=True).strip()
            if actual != expected:
                raise SystemExit(f"NID drift for {name}: {actual} != {expected}")

    with tempfile.TemporaryDirectory(prefix="ps5-agc-api-") as directory:
        output = Path(directory) / "test"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            f"-I{SDK / 'include'}", str(SDK / "tests/test_header.c"),
            str(SDK / "stubs/libSceAgc_link_stub.c"), "-o", str(output),
        ], check=True)
        subprocess.run([str(output)], check=True)
    print("sanitized AGC API passed: 16 declarations/stubs, deterministic NIDs, "
          "Gears constants and safe DMA-fill arguments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
