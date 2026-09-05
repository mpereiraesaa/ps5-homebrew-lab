#!/usr/bin/env python3
"""Conservatively classify one private-memory Stage C DMA fill log."""
from __future__ import annotations

from enum import Enum


class State(str, Enum):
    NOT_STARTED = "not_started"
    PRE_TRANSACTION_EXIT = "pre_transaction_exit"
    COMPLETE = "complete"
    PARKED = "parked"
    UNKNOWN_RETAIN = "unknown_retain"


def classify(log: str, expected_fill_bytes: int) -> dict[str, object]:
    header = "AGC native Stage C v1" in log
    size = f"stage_c_fill_bytes=0x{expected_fill_bytes:08x}" in log
    transaction = "STAGE_C_TRANSACTION_STARTED" in log
    submit = "stage_c_submit=0x00000000" in log
    fence = "STAGE_C_GPU_FENCE_ZERO" in log
    target = "stage_c_target_matches=true" in log
    prefix = "stage_c_prefix_canary_intact=true" in log
    suffix = "stage_c_suffix_canary_intact=true" in log
    outside = "stage_c_outside_untouched=true" in log
    scrubbed = "stage_c_arenas_scrubbed=true" in log
    cleanup = all(marker in log for marker in (
        "data_batch_unmap=0x00000000",
        "data_batch_unmap_processed=0x00000001",
        "data_direct_release=0x00000000",
        "data_virtual_release=0x00000000",
        "command_batch_unmap=0x00000000",
        "command_batch_unmap_processed=0x00000001",
        "command_direct_release=0x00000000",
        "command_virtual_release=0x00000000",
        "agc_unload=0x00000000",
        "STAGE_C_COMPLETE cleanup complete; parked-safe; close exact title PPSA99998",
    ))
    parked = "PARKED_STAGE_C_TRANSACTION" in log
    pre_cleanup = "STAGE_C_PRE_TRANSACTION_CLEANUP_COMPLETE" in log
    ordered = False
    ordered_markers = (
        "STAGE_C_TRANSACTION_STARTED",
        "stage_c_submit=0x00000000",
        "STAGE_C_GPU_FENCE_ZERO",
        "stage_c_target_matches=true",
        "stage_c_prefix_canary_intact=true",
        "stage_c_suffix_canary_intact=true",
        "stage_c_outside_untouched=true",
        "stage_c_arenas_scrubbed=true",
        "STAGE_C_COMPLETE cleanup complete",
    )
    if all(marker in log for marker in ordered_markers):
        positions = [log.index(marker) for marker in ordered_markers]
        ordered = positions == sorted(positions)

    complete = (header and size and submit and fence and target and prefix and
                suffix and outside and scrubbed and cleanup and ordered and
                not parked)
    if parked:
        state = State.PARKED
        reason = "post-submit state or verification is unsafe; retain both mappings"
    elif complete:
        state = State.COMPLETE
        reason = "fill, fence, full CPU verification and cleanup completed in order"
    elif pre_cleanup and not transaction:
        state = State.PRE_TRANSACTION_EXIT
        reason = "probe cleaned up before submit"
    elif not log.strip():
        state = State.NOT_STARTED
        reason = "no Stage C log"
    else:
        state = State.UNKNOWN_RETAIN
        reason = "active, truncated, stale or contradictory Stage C log"

    close_allowed = state in (State.PRE_TRANSACTION_EXIT, State.COMPLETE)
    return {
        "state": state.value,
        "close_allowed": close_allowed,
        "completion_proven": state is State.COMPLETE,
        "expected_fill_bytes": expected_fill_bytes,
        "header_matches": header,
        "size_matches": size,
        "transaction_started": transaction,
        "submit_zero": submit,
        "gpu_fence_zero": fence,
        "target_matches": target,
        "prefix_canary_intact": prefix,
        "suffix_canary_intact": suffix,
        "outside_untouched": outside,
        "arenas_scrubbed": scrubbed,
        "cleanup_complete": cleanup,
        "markers_ordered": ordered,
        "retain_all_resources": not close_allowed,
        "reason": reason,
        "operator_recovery": (
            "retain PPSA99998 and both direct mappings; do not Close Game"
            if not close_allowed else "none"
        ),
    }
