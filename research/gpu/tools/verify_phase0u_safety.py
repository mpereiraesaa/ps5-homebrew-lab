#!/usr/bin/env python3
"""Audit the no-submit phase 0U context-bootstrap probe."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

SOURCE=Path("legacy/probes/ps5-agc-phase0/libagc_context_bootstrap_probe.c")
ELF=Path("legacy/probes/ps5-agc-phase0/ps5-agc-phase0u-context-bootstrap.elf")
MAKEFILE=Path("legacy/probes/ps5-agc-phase0/Makefile")
SUPERVISOR=Path("tools/night_supervisor.py")
AGC=Path("research/gpu/dumps/system-libSceAgc.sprx")
DRIVER=Path("research/gpu/dumps/system-libSceAgcDriver.sprx")
OUTPUT=Path("research/gpu/captures/agc-phase0u-draft-safety.json")

source=SOURCE.read_text(); elf=ELF.read_bytes(); supervisor=SUPERVISOR.read_text()
required=("AGC_CONTEXT_BOOTSTRAP_NID \"23LRUSvYu1M\"",
          "rc=bootstrap(&context_word,8)",
          "record_queue(\"before-bootstrap\"",
          "record_queue(\"after-bootstrap\"",
          "phase0U exit result=%d submitted=no", "_exit(rc?14:0)")
missing=[item for item in required if item not in source]
if missing: raise SystemExit(f"phase 0U source contract missing: {missing}")
for forbidden in ("SubmitDcb","sceKernelBatchMap","sceVideoOut",
                  "sceKernelAllocateMainDirectMemory","0xc0064900","0xc0055000"):
    if forbidden in source or forbidden.encode() in elf:
        raise SystemExit(f"phase 0U contains forbidden capability: {forbidden}")
all_recipe=MAKEFILE.read_text().split("all:",1)[1].split("\n\n",1)[0]
if "phase0u" in all_recipe: raise SystemExit("phase 0U entered default build")
sha=hashlib.sha256(elf).hexdigest()
for item in (f'PHASE0U_SHA256 = "{sha}"',"def run_phase0u_context_bootstrap(",
             '"run-phase0u-context-bootstrap"',"candidate != old_log"):
    if item not in supervisor: raise SystemExit(f"supervisor contract missing: {item}")

agc_dis=subprocess.check_output(["llvm-objdump","-d",str(AGC)],text=True)
driver_dis=subprocess.check_output(["llvm-objdump","-d",str(DRIVER)],text=True)
static_contract=(
    "9990: 48 8b 04 24",       # exported v8 entry observed in San Andreas
    "99e6: e9 35 f0 ff ff",    # tail-call internal bootstrap +0x8a20
    "8aa4: e8 67 e4 00 00",    # call driver setter PLT
)
for item in static_contract:
    if item not in agc_dis: raise SystemExit(f"AGC bootstrap evidence missing: {item}")
driver_contract=(
    "3fd0: 55",                # exported setter oFb2hMcoJa4
    "4089: 0d 00 00 02 00",    # set queue flag 0x20000
    "4096: 25 ff ff fd ff",    # clear queue flag 0x20000
    "40a8: 89 05 12 e8 01 00", # store queue+0x08
)
for item in driver_contract:
    if item not in driver_dis: raise SystemExit(f"driver setter evidence missing: {item}")

result={"schema":1,"firmware_scope":"12.02","source":str(SOURCE),
        "source_sha256":hashlib.sha256(source.encode()).hexdigest(),"elf":str(ELF),
        "elf_sha256":sha,"elf_bytes":len(elf),"agc_entry_nid":"23LRUSvYu1M",
        "agc_entry_offset":"0x9990","version":8,
        "driver_flag_setter_nid":"oFb2hMcoJa4","driver_flag_setter_offset":"0x3fd0",
        "reads_queue_before_after":True,"mapping_used":False,"submitted":False,
        "videoout_used":False,"default_build":False,
        "approved_for_deployment":True,"console_contacted":False}
OUTPUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
print(json.dumps(result,indent=2,sort_keys=True))
