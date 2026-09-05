#!/usr/bin/env python3
"""Classify sanitized logs from the native ownership-label probe."""
def classify(log: str):
    parked="PARKED_NATIVE_LABEL" in log or "DO_NOT_CLOSE_PPSA99998" in log
    complete=(log.count("GPU ownership complete fence=0 target=0")==1 and
              log.count("probe_complete=true")==1 and
              all(f"{x}=0x00000000" in log for x in
                  ("agc_init","submit_dcb","batch_unmap","direct_release",
                   "virtual_release","agc_unload")) and
              "batch_unmap_processed=0x00000001" in log and not parked)
    pre=("pre-submit clean failure; parked-safe; close exact title PPSA99998" in log and
         "submit_dcb=" not in log and not parked)
    state="gpu_complete" if complete else "pre_submit_clean" if pre else "parked_retain" if parked else "unknown_retain"
    return {"state":state,"close_allowed":state in ("gpu_complete","pre_submit_clean"),"completion_proven":complete,"retain_all":state not in ("gpu_complete","pre_submit_clean")}
