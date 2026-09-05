#!/usr/bin/env python3
"""Verify the phase 0T load-only artifact; never contacts the console."""
from __future__ import annotations

import hashlib
import json
import base64
import struct
import subprocess
from pathlib import Path

SOURCE=Path("legacy/probes/ps5-agc-phase0/libagc_load_queue_probe.c")
ELF=Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0t-libagc-load-queue.elf")
AGC=Path("research/gpu/dumps/system-libSceAgc.sprx")
LIBC_STUB=Path("../ps5debug-NG/ps5-payload-sdk/install/target/lib/libSceLibcInternal.so")
MAKEFILE=Path("legacy/probes/ps5-agc-phase0/Makefile")
SUPERVISOR=Path("tools/night_supervisor.py")
OUTPUT=Path("research/gpu/captures/agc-phase0t-draft-safety.json")
source=SOURCE.read_text(); elf=ELF.read_bytes(); supervisor=SUPERVISOR.read_text()
required=("dlopen(AGC_NAME,RTLD_NOW|RTLD_LOCAL)","record_queue(\"before-libAgc\"",
          "record_queue(\"after-libAgc\"","phase0T exit result=%d submitted=no")
missing=[x for x in required if x not in source]
if missing: raise SystemExit(f"phase 0T source contract missing: {missing}")
for forbidden in ("SubmitDcb","sceKernelBatchMap","sceVideoOut","0xc0064900","0xc0055000"):
    if forbidden in source or forbidden.encode() in elf:
        raise SystemExit(f"phase 0T contains forbidden capability: {forbidden}")
all_recipe=MAKEFILE.read_text().split("all:",1)[1].split("\n\n",1)[0]
if "phase0t" in all_recipe: raise SystemExit("phase 0T entered default build")
sha=hashlib.sha256(elf).hexdigest()
for item in (f'PHASE0T_SHA256 = "{sha}"',"def run_phase0t_libagc_load(",
             '"run-phase0t-libagc-load"',"candidate != old_log",
             'self.checked_close("FAKE00000")'):
    if item not in supervisor: raise SystemExit(f"supervisor contract missing: {item}")
symbols=subprocess.check_output(["readelf","-Ws",str(ELF)],text=True)
undefined=sorted({line.split()[-1] for line in symbols.splitlines()
                  if " UND " in f" {line} " and line.split()[-1]!="UND"})
NID_SALT=bytes.fromhex("518d64a635ded8c1e6b039b1c3e55230")
NID_CHARS="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-"
def encode_nid(name: str) -> str:
    digest=bytearray(hashlib.sha1(name.encode()+NID_SALT).digest())
    digest[:8]=struct.pack("<Q",struct.unpack(">Q",digest[:8])[0])
    digest[8:16]=b"\0"*8
    return base64.b64encode(digest,altchars=b"+-").decode()[:11]

libc_symbols=subprocess.check_output(
    ["nm","-D","--defined-only",str(LIBC_STUB)],text=True)
nid_matches=[line.split(maxsplit=2)[2] for line in libc_symbols.splitlines()
             if len(line.split(maxsplit=2)) == 3 and
             encode_nid(line.split(maxsplit=2)[2]) == "YQ0navp+YIc"]
if nid_matches != ["puts"]:
    raise SystemExit(f"unexpected YQ0navp+YIc resolution: {nid_matches}")
agc_disassembly=subprocess.check_output(
    ["llvm-objdump","-d","--start-address=0xdb98","--stop-address=0xdc40",str(AGC)],
    text=True,stderr=subprocess.DEVNULL)
for instruction in ("callq\t0x17040", "callq\t0x16fa0", "dc34:"):
    if instruction not in agc_disassembly:
        raise SystemExit(f"constructor continuation evidence missing: {instruction}")
result={"schema":1,"firmware_scope":"12.02","source":str(SOURCE),
        "source_sha256":hashlib.sha256(source.encode()).hexdigest(),"elf":str(ELF),
        "elf_sha256":sha,"elf_bytes":len(elf),"loads_libSceAgc":True,
        "reads_queue_before_after":True,"mapping_used":False,"queue_api_called":False,
        "submitted":False,"videoout_used":False,"default_build":False,
        "constructor_warning_import_nid":"YQ0navp+YIc",
        "constructor_warning_import_symbol":"puts",
        "constructor_continues_after_warning":True,
        "approved_for_deployment":True,"console_contacted":False,
        "undefined_symbols":undefined}
OUTPUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
print(json.dumps(result,indent=2,sort_keys=True))
