#!/usr/bin/env python3
"""Fail-closed local gate for the first native ownership-fenced submit."""
import hashlib, json, struct, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ELF=ROOT/"build-submit/eboot.elf"
PIE=ROOT/"build-submit/llvm-pie.elf"
SELF=ROOT/"dist-submit/PPSA99998/eboot.bin"
SOURCE=ROOT/"submit_main.cpp"
OUT=ROOT.parents[2]/"research/gpu/captures/agc-native-label-local-proof.json"

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def phdr_count(blob,base=0): return struct.unpack_from("<H",blob,base+0x38)[0]

elf=ELF.read_bytes(); pie=PIE.read_bytes(); fself=SELF.read_bytes(); source=SOURCE.read_text()
if elf[:4]!=b"\x7fELF" or elf[7:9]!=bytes((9,2)) or struct.unpack_from("<H",elf,16)[0]!=0xfe10 or phdr_count(elf)!=14:
    raise SystemExit("native ELF contract mismatch")
off=fself.find(b"\x7fELF")
if fself[:4]!=bytes.fromhex("4f153d1d") or off<0 or struct.unpack_from("<H",fself,off+16)[0]!=0xfe10 or phdr_count(fself,off)!=14:
    raise SystemExit("development SELF contract mismatch")
required=(b"AGC native label v5",b"separate target/fence cache lines",b"sceAgcInit state_bytes=8",b"pre-submit clflush64+mfence",b"BatchMap protection=f2 memory_type=0c",b"libSceAgc.prx",b"libSceAgcDriver.prx",b"agc_init=",b"batch_map_processed=",b"target_offset=1000 fence_offset=1100 cache_lines_separate=true",b"cache_publication=clflush64+mfence",b"batch_policy=f2/0c",b"submit_dcb=",b"target_after_fence=",b"GPU ownership complete fence=0 target=0",b"PARKED_NATIVE_LABEL",b"DO_NOT_CLOSE_PPSA99998",b"cleanup complete; parked-safe; close exact title PPSA99998")
if any(x not in elf for x in required): raise SystemExit("required submit/lifecycle marker missing")
if b"UglJIZjGssM" not in elf: raise SystemExit("SubmitDcb NID import missing")
if any(x in elf for x in (b"libSceVideoOut",b"f3dg2CSgRKY",b"DrawIndex",b"SetFlip")): raise SystemExit("out-of-scope import present")
dma=struct.pack("<4I",0xc0055000,0xc0300000,0,0)
join=struct.pack("<4I",4,0xc0064900,0x06000528,0x42010000)
if elf.count(dma)!=1 or elf.count(join)!=1: raise SystemExit("minimal stream missing or ambiguous")
order=("sceAgcInit(&agc_state,sizeof(agc_state))","sceKernelReserveVirtualRange","sceKernelAllocateMainDirectMemory","sceKernelBatchMap","submitted=1","sceAgcDriverSubmitDcb","ownership fence timeout","GPU ownership complete fence=0 target=0","sceKernelReleaseDirectMemory","sceKernelMunmap","sceSysmoduleUnloadModuleInternal")
for item in order:
    if item not in source: raise SystemExit(f"source lifecycle missing: {item}")
calls=("load=sceSysmoduleLoadModuleInternal(AGC)",
       "init=sceAgcInit(&agc_state,sizeof(agc_state))",
       "reserve=sceKernelReserveVirtualRange(&map,ARENA,0,ALIGN)",
       "alloc=sceKernelAllocateMainDirectMemory(ARENA,ALIGN,0x0c,&phys)",
       "mapping=sceKernelBatchMap(&e,1,&processed)",
       "flush_gpu_data(b,ARENA)",
       "submitted=1", "submit_rc=sceAgcDriverSubmitDcb(&info)",
       "GPU ownership complete fence=0 target=0",
       "batch_unmap=sceKernelBatchMap(&e,1,&unmap_processed)",
       "release=sceKernelReleaseDirectMemory(phys,ARENA)",
       "unmap=sceKernelMunmap(map,ARENA)",
       "unload=sceSysmoduleUnloadModuleInternal(AGC)")
positions=[source.index(item) for item in calls]
if positions != sorted(positions): raise SystemExit("runtime call order mismatch")
if source.index("submitted=1")>source.index("submit_rc=sceAgcDriverSubmitDcb(&info)"): raise SystemExit("retention marker follows submit")
if source.index("GPU ownership complete fence=0 target=0")>source.rindex("sceKernelBatchMap(&e,1,&unmap_processed)"): raise SystemExit("BatchMap cleanup precedes ownership")
if "BatchEntry e{map,phys,ARENA,0xf2,0x0c,0,0}" not in source: raise SystemExit("exact BatchMap map policy missing")
if "BatchEntry e{map,0,ARENA,0xf2,0x0c,0,1}" not in source: raise SystemExit("exact BatchMap unmap policy missing")
if "sceKernelMapDirectMemory" in source or "sceKernelAllocateDirectMemory" in source: raise SystemExit("legacy mapping path remains")
if '"clflush (%0)"' not in source or '"mfence"' not in source or "at+=64" not in source: raise SystemExit("ProsperoTV cache publication contract missing")
if "TARGET=0x1000,FENCE=0x1100" not in source: raise SystemExit("target/fence cache-line separation missing")
clflush=pie.find(bytes.fromhex("0fae39")); mfence=pie.find(bytes.fromhex("0faef0"))
if clflush<0 or mfence<0 or clflush>=mfence: raise SystemExit("compiled clflush/mfence sequence missing")
proof={"schema":5,"firmware":"12.02","elf_sha256":sha(ELF),"fself_sha256":sha(SELF),"bootstrap_api":"sceAgcInit","bootstrap_state_bytes":8,"cache_publication":{"instruction":"clflush","line_bytes":64,"ordering":"mfence","range":"entire arena before submit","machine_code_sequence_verified":True},"label_layout":{"target_offset":0x1000,"fence_offset":0x1100,"separate_cache_lines":True},"elf_dependencies":["libSceAgc.prx","libSceAgcDriver.prx"],"stream_dwords":15,"target_bytes":4,"arena_bytes":0x20000,"arena_alignment":0x10000,"allocation_api":"sceKernelAllocateMainDirectMemory","mapping_api":"sceKernelBatchMap","memory_type":12,"protection":0xf2,"batch_map_processed_required":1,"watchdog_seconds":12,"fence_deadline_seconds":2,"post_submit_ambiguity_policy":"park and retain process, driver and mapping","exact_stream_unique":True,"videoout":False,"shader_or_draw":False,"console_contacted":False,"approved_for_unattended_execution":False}
OUT.write_text(json.dumps(proof,indent=2,sort_keys=True)+"\n")
print(json.dumps(proof,indent=2,sort_keys=True))
