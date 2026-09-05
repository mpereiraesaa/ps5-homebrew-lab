#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TITLE_ID = "PPSA99998"
REFERENCE_COMMIT = "722f2227a8bb6fa2229120546995b6562552c752"
EXPECTED_RUNTIME_SHA256 = "e6ff45d16adf687855cc3b33b0c8a4132b6504360b221e0a34c7e99fb3ba0036"
EXPECTED_ASSETS = {
    "geometry.header.bin": (376, "13d2949bdc764703179a7ab77873930e987f3676a0dec9246a144fca1984fcd4"),
    "geometry.text.bin": (736, "7e4af7b5daf3926467a32684334c8e4d5bc7b1aab919eb67b86e799587637a77"),
    "pixel.header.bin": (384, "1384eb79521959aaaa2799ac1e0caba1bb3489e508a963b13d5c4fb8e9f24b52"),
    "pixel.text.linear-buffer.bin": (2304, "2ab90cd91412acf6102b6f158ff1d430c02849454d6c86a89a7cf464e143b91c"),
}


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def phdrs(blob: bytes, base: int = 0) -> list[dict[str, int]]:
    if blob[base:base + 4] != b"\x7fELF":
        raise SystemExit("missing ELF magic")
    offset = struct.unpack_from("<Q", blob, base + 0x20)[0]
    entry_size = struct.unpack_from("<H", blob, base + 0x36)[0]
    count = struct.unpack_from("<H", blob, base + 0x38)[0]
    if entry_size != 56:
        raise SystemExit("unexpected program-header size")
    result = []
    for index in range(count):
        values = struct.unpack_from("<IIQQQQQQ", blob, base + offset + index * entry_size)
        result.append(dict(zip(
            ("type", "flags", "offset", "vaddr", "paddr", "filesz", "memsz", "align"),
            values,
        )))
    return result


def main() -> int:
    metadata_path = ROOT / "sce_sys/param.json"
    elf_path = ROOT / "build/eboot.elf"
    self_path = ROOT / f"dist/{TITLE_ID}/eboot.bin"
    runtime_path = ROOT / f"dist/{TITLE_ID}/sce_module/libc.prx"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    asset_root = ROOT.parents[2] / "third_party/ProsperoTV/assets/private"
    for name, (size, expected_hash) in EXPECTED_ASSETS.items():
        path = asset_root / name
        if path.stat().st_size != size or sha256(path.read_bytes()) != expected_hash:
            raise SystemExit(f"local-only asset mismatch: {name}")
    if metadata.get("titleId") != TITLE_ID:
        raise SystemExit("metadata title mismatch")
    if metadata.get("applicationDrmType") != "free":
        raise SystemExit("native development title must use free DRM metadata")
    if metadata.get("applicationCategoryType") != 0 or metadata.get("contentBadgeType") != 1:
        raise SystemExit("metadata does not describe a PS5 game application")
    if metadata.get("downloadDataSize") != 256:
        raise SystemExit("downloadDataSize must use the hardware-validated platform value 256")
    intents = metadata.get("gameIntent", {}).get("permittedIntents", [])
    if not any(item.get("intentType") == "launchActivity" for item in intents):
        raise SystemExit("launchActivity intent missing")

    elf = elf_path.read_bytes()
    if elf[7] != 9 or elf[8] != 2:
        raise SystemExit("expected FreeBSD OS ABI 9 / ABI version 2")
    if struct.unpack_from("<H", elf, 16)[0] != 0xFE10:
        raise SystemExit("expected ET_SCE_EXEC_ASLR")
    headers = phdrs(elf)
    if len(headers) != 14:
        raise SystemExit(f"expected fourteen program headers, got {len(headers)}")
    process = [item for item in headers if item["type"] == 0x61000001]
    dynamic = [item for item in headers if item["type"] == 2]
    dynlib = [item for item in headers if item["type"] == 1 and item["flags"] == 0]
    relro = [item for item in headers if item["type"] == 0x6474E552]
    if len(process) != 1 or process[0]["filesz"] < 0x60:
        raise SystemExit("real PT_SCE_PROCPARAM is missing")
    if len(dynamic) != 1 or len(dynlib) != 1 or len(relro) != 1:
        raise SystemExit("SCE dynamic/RELRO layout is incomplete")
    proc = process[0]
    proc_blob = elf[proc["offset"]:proc["offset"] + proc["filesz"]]
    if proc_blob[8:12] != b"ORBI":
        raise SystemExit("process parameter magic missing")
    entrypoint = struct.unpack_from("<Q", elf, 24)[0]
    executable = [item for item in headers if item["type"] == 1 and item["flags"] == 1]
    if len(executable) != 1:
        raise SystemExit("expected one execute-only load segment")
    text = executable[0]
    if not (text["vaddr"] <= entrypoint < text["vaddr"] + text["memsz"]):
        raise SystemExit("entrypoint is outside the execute-only segment")
    if elf[text["offset"]:text["offset"] + 16] != b"\xcc" * 16:
        raise SystemExit("converter startup guard is missing")

    required = (
        b"/download0/agc-native-sce-phase0.log",
        b"AGC CPU direct-memory link probe v2",
        b"direct_allocate=",
        b"direct_map=",
        b"preflight_ranges=",
        b"create_pre_raster=",
        b"create_pixel=",
        b"cx_matches_host_and_static=",
        b"uc_matches_host_and_static=",
        b"direct_arena_scrubbed=",
        b"direct_unmap=",
        b"direct_release=",
        b"cleanup complete; parked-safe; close exact title PPSA99998",
        b"31e91809f4db88374370d53fb0e7806d602db9ccdbed16c647f4bfa498b2c1d1",
        b"38558bc0496f75ff9f399b8f1f52ba6883259c89e2fa0bf7f756d62dcb090685",
        b"libSceLibcInternal.prx",
        b"libSceAgc.prx",
        b"libSceSysmodule.prx",
        b"libkernel.prx",
    )
    missing = [item.decode() for item in required if item not in elf]
    if missing:
        raise SystemExit(f"required lifecycle/runtime strings missing: {missing}")
    forbidden_names = (b"sceAgcSubmit", b"sceAgcCreateQueue", b"sceVideoOut")
    if any(item in elf for item in forbidden_names):
        raise SystemExit("forbidden queue/submit/VideoOut name present")
    forbidden_packets = (
        bytes.fromhex("005005c0"), bytes.fromhex("004906c0"),
        bytes.fromhex("003c05c0"), bytes.fromhex("005806c0"),
    )
    if any(item in elf for item in forbidden_packets):
        raise SystemExit("forbidden PM4 packet header present")

    fself = self_path.read_bytes()
    if fself[:4] != bytes.fromhex("4f153d1d"):
        raise SystemExit("unexpected development SELF magic")
    embedded = fself.find(b"\x7fELF")
    if embedded < 0 or struct.unpack_from("<H", fself, embedded + 16)[0] != 0xFE10:
        raise SystemExit("FSELF does not embed ET_SCE_EXEC_ASLR")
    if len(phdrs(fself, embedded)) != 14:
        raise SystemExit("FSELF embedded program-header count differs")
    runtime = runtime_path.read_bytes()
    if sha256(runtime) != EXPECTED_RUNTIME_SHA256:
        raise SystemExit("clean-room runtime hash mismatch")

    proof = {
        "title_id": TITLE_ID,
        "reference_commit": REFERENCE_COMMIT,
        "console_contacted": False,
        "launchability_on_fw_12_02_proven": False,
        "metadata": {
            "application_drm_type": "free",
            "launch_activity": True,
            "download_data_size": metadata["downloadDataSize"],
        },
        "elf": {
            "sha256": sha256(elf),
            "type": "0xfe10",
            "os_abi": 9,
            "abi_version": 2,
            "entrypoint": entrypoint,
            "program_header_count": len(headers),
            "process_parameter_magic": "ORBI",
            "dynamic_present": True,
            "dynlibdata_present": True,
            "relro_present": True,
        },
        "fself": {"sha256": sha256(fself), "embedded_elf_type": "0xfe10"},
        "runtime": {"sha256": sha256(runtime), "reproducible_clean_room": True},
        "scope": {
            "cpu_create_and_link_only": True,
            "direct_memory_arena": {
                "bytes": 0x10000, "alignment": 0x4000,
                "type": 0x0C, "protection": 0x33,
            },
            "queue_or_submit_present": False,
            "videoout_present": False,
            "known_pm4_headers_present": False,
            "parked_until_exact_title_close": True,
            "local_assets_hash_pinned": True,
            "expected_cx_sha256": "31e91809f4db88374370d53fb0e7806d602db9ccdbed16c647f4bfa498b2c1d1",
            "expected_uc_sha256": "38558bc0496f75ff9f399b8f1f52ba6883259c89e2fa0bf7f756d62dcb090685",
        },
    }
    output = ROOT.parents[2] / "research/gpu/captures/agc-native-sce-phase0-local-proof.json"
    output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
