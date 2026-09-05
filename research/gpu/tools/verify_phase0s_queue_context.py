#!/usr/bin/env python3
"""Compare parked 0S queue context with native snapshots; host-only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DRIVER=Path("research/gpu/dumps/game-libSceAgcDriver.sprx.bin")
GAME=DRIVER
PHASE=Path("research/gpu/dumps/phase0s-agcdriver-rw.bin")
MENU=Path("research/gpu/dumps/menu-libSceAgcDriver.sprx.bin")
INVENTORY=Path("research/gpu/captures/agc-phase0s-parked-inventory.json")
OUTPUT=Path("research/gpu/captures/agc-phase0s-queue-context-proof.json")
DATA=0x18000; QUEUE=0x228B8-DATA; STATE=0x22908-DATA

driver=DRIVER.read_bytes(); phase=PHASE.read_bytes()
game=GAME.read_bytes()[DATA:0x24000]; menu=MENU.read_bytes()[DATA:0x24000]
if hashlib.sha256(driver).hexdigest() != "5222f94758fa2230d01ed2d6afa2fea0b10d90791706d34d054bd1aecea40762":
    raise SystemExit("driver dump changed")
if hashlib.sha256(phase).hexdigest() != "70cd256cd716c4959a71023020824c2f3751d781d4286ed76706f8a04b100b31":
    raise SystemExit("phase 0S RW snapshot changed")

def u32(blob: bytes, off: int) -> int:
    return int.from_bytes(blob[off:off+4],"little")

fragments={
    0x1497:bytes.fromhex("bf00000200"),
    0x14A3:bytes.fromhex("237b08"),
    0x1630:bytes.fromhex("c1ef11"),
    0x2385:bytes.fromhex("41c7450800000200"),
}
for off,want in fragments.items():
    if driver[off:off+len(want)] != want:
        raise SystemExit(f"driver fragment changed at {off:#x}")

inventory=json.loads(INVENTORY.read_text())
host=next((p for p in inventory["processes"] if p["pid"]==1406),None)
if not host or host["name"]!="SceCloudClientApp":
    raise SystemExit("phase 0S host identity changed")
names={m["name"] for m in host["maps"]}
if "libSceAgcDriver.sprx" not in names or "libSceAgc.sprx" in names:
    raise SystemExit("phase 0S module-presence premise changed")

proof={
 "schema":1,"firmware_scope":"12.02","console_contacted":False,
 "phase0s_host":{"pid":1406,"process":"SceCloudClientApp",
                  "libSceAgcDriver_present":True,"libSceAgc_present":False},
 "queue_snapshots":{
   "phase0s":{"index":u32(phase,QUEUE+4),"flags_08":hex(u32(phase,QUEUE+8)),
              "mode_0c":hex(u32(phase,QUEUE+0xC)),"sentinel":phase[QUEUE+0x48],
              "registration_latch":u32(phase,STATE+0x1CC)},
   "san_andreas":{"index":u32(game,QUEUE+4),"flags_08":hex(u32(game,QUEUE+8)),
                   "mode_0c":hex(u32(game,QUEUE+0xC)),"sentinel":game[QUEUE+0x48],
                   "registration_latch":u32(game,STATE+0x1CC)},
   "compositor":{"index":u32(menu,QUEUE+4),"flags_08":hex(u32(menu,QUEUE+8)),
                  "mode_0c":hex(u32(menu,QUEUE+0xC)),"sentinel":menu[QUEUE+0x48]},
 },
 "driver_code":{
   "null_configuration_fallback_writes_queue_plus_08":"0x20000",
   "class0_backend_masks_queue_plus_08_with":"0x20000",
   "masked_bit_is_shifted_right":17,
 },
 "conclusions":{
   "sentinel_proves_execution_ready":False,
   "phase0s_used_null_configuration_fallback":True,
   "phase0s_reached_lazy_registration":True,
   "missing_libSceAgc_is_observed":True,
   "libSceAgc_load_will_reconfigure_queue":None,
   "next_test":"phase 0T load-only before/after comparison",
 }
}
OUTPUT.write_text(json.dumps(proof,indent=2,sort_keys=True)+"\n")
print(json.dumps(proof,indent=2,sort_keys=True))
