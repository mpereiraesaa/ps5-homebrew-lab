#!/usr/bin/env python3
"""Audit the fixed-page, no-submit phase 0W bootstrap probe."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path

SOURCE=Path("legacy/probes/ps5-agc-phase0/libagc_fixed_fs_bootstrap_probe.c")
ELF=Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0w-fixed-fs-bootstrap.elf")
MAKEFILE=Path("legacy/probes/ps5-agc-phase0/Makefile")
SUPERVISOR=Path("tools/night_supervisor.py")
AGC=Path("research/gpu/dumps/system-libSceAgc.sprx")
OUTPUT=Path("research/gpu/captures/agc-phase0w-draft-safety.json")

source=SOURCE.read_text(); elf=ELF.read_bytes(); supervisor=SUPERVISOR.read_text()
required=("FS_TABLE_VA UINT64_C(0xfe0040000)",
          "RELOCATED_FS_TABLE_VA UINT64_C(0xff0040000)",
          "AGC_FS_POINTER_OFFSET UINT64_C(0x45f90)",
          "FS_TABLE_COPY_SIZE ((size_t)0x4000)",
          "FS_TABLE_MAPPING_SIZE ((size_t)0x10000)",
          "memcpy(mapping,(const void *)original,FS_TABLE_COPY_SIZE)",
          "*fs_pointer=(uintptr_t)mapping", "rc=bootstrap(&context_word,8)",
          "submitted=no mapping_lifetime=process")
missing=[x for x in required if x not in source]
if missing: raise SystemExit(f"phase 0W source contract missing: {missing}")
for forbidden in ("SubmitDcb","sceKernelBatchMap","sceVideoOut","0xc0064900","0xc0055000"):
    if forbidden in source or forbidden.encode() in elf:
        raise SystemExit(f"phase 0W contains forbidden capability: {forbidden}")
recipe=MAKEFILE.read_text().split("all:",1)[1].split("\n\n",1)[0]
if "phase0w" in recipe: raise SystemExit("phase 0W entered default build")
sha=hashlib.sha256(elf).hexdigest()
for item in (f'PHASE0W_SHA256 = "{sha}"',"def run_phase0w_fixed_fs_bootstrap(",
             '"run-phase0w-fixed-fs-bootstrap"',"candidate!=old_log"):
    if item not in supervisor: raise SystemExit(f"supervisor contract missing: {item}")
dis=subprocess.check_output(["llvm-objdump","-d",str(AGC)],text=True)
for item in ("9990: 48 8b 04 24","99e6: e9 35 f0 ff ff",
             "809a: 48 8b 0d ef de 03 00", "80a6: 48 ba 00 00 04 e0 0f 00 00 00",
             "80da: 48 8b 0d af de 03 00", "80e6: 48 ba 00 00 04 e0 0f 00 00 00"):
    if item not in dis: raise SystemExit(f"AGC fixed-FS evidence missing: {item}")
result={"schema":1,"firmware_scope":"12.02","source":str(SOURCE),
        "source_sha256":hashlib.sha256(source.encode()).hexdigest(),"elf":str(ELF),
        "elf_sha256":sha,"elf_bytes":len(elf),"fixed_va":"0xfe0040000",
        "copied_bytes":0x4000,"agc_fs_pointer_offset":"0x45f90","version":8,
        "submitted":False,"videoout_used":False,"default_build":False,
        "approved_for_deployment":True,"console_contacted":False}
OUTPUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
print(json.dumps(result,indent=2,sort_keys=True))
