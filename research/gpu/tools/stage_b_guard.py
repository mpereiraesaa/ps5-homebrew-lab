#!/usr/bin/env python3
"""Conservatively classify future AGC stage-B presentation logs."""
from __future__ import annotations

from enum import Enum
import re


class State(str, Enum):
    NOT_STARTED = "not_started"
    PRE_TRANSACTION_EXIT = "pre_transaction_exit"
    PRESENT_COMPLETE = "present_complete"
    PARKED = "parked"
    UNKNOWN_RETAIN = "unknown_retain"


PARK_MARKERS = (
    "PARKED_STAGE_B_TRANSACTION",
    "PARKED_STAGE_B_BUILDER_ERROR",
    "PARKED_STAGE_B_SUBMIT_ERROR",
    "PARKED_STAGE_B_FENCE_TIMEOUT",
    "PARKED_STAGE_B_VIDEOOUT_TIMEOUT",
    "PARKED_STAGE_B_CLEANUP_REFUSED",
)


def classify(log: str) -> dict[str, object]:
    markers = [marker for marker in PARK_MARKERS if marker in log]
    # Stage F/G retain the Stage-E transaction/completion contract while
    # extending geometry and depth.  They must never fall back to the older
    # SetFlip-only classification path.
    stage_i = "AGC native Stage I v1" in log
    stage_e = stage_i or any(marker in log for marker in (
        "AGC native Stage E v1", "AGC native Stage F v1",
        "AGC native Stage G v1", "AGC native Stage G/22 v1",
        "AGC native Stage G/23 OFF v1", "AGC native Stage G/23 ON v1",
        "AGC native Stage H v1",
    ))
    transaction_marker = (
        "STAGE_I_LOOP_BEGIN buffers=2 depth_registers=22"
        if stage_i else
        "STAGE_E_TRANSACTION_STARTED one_submit=true" if stage_e else
        "SETFLIP_TRANSACTION_STARTED")
    transaction = transaction_marker in log or bool(markers)
    fence_marker = "STAGE_I_GPU_FENCE_ZERO" if stage_i else "STAGE_B_GPU_FENCE_ZERO"
    videoout_marker = ("STAGE_I_VIDEOOUT_EVENT_EXACT" if stage_i else
                       "STAGE_B_VIDEOOUT_EVENT_ONE")
    fence = fence_marker in log
    videoout = videoout_marker in log
    normal_exit = "AGC stage B exit result=0" in log
    any_exit = "AGC stage B exit result=" in log
    pre_transaction_cleanup = "STAGE_B_PRE_TRANSACTION_CLEANUP_COMPLETE" in log
    ordered = False
    stage_i_counts = re.search(
        r"stage_i_frames_requested=0x([0-9a-fA-F]+).*"
        r"stage_i_frames_completed=0x([0-9a-fA-F]+).*"
        r"stage_i_frames_verified=0x([0-9a-fA-F]+)", log, re.S)
    stage_i_count_exact = bool(stage_i_counts and
        len({int(value, 16) for value in stage_i_counts.groups()}) == 1)
    stage_i_pipeline_metrics = bool(
        re.search(r"stage_i_max_frames_in_flight=0x0*2\b", log) and
        re.search(r"stage_i_loop_elapsed_ns=0x[0-9a-fA-F]*[1-9a-fA-F][0-9a-fA-F]*\b", log) and
        re.search(r"stage_i_frame_interval_ns_average=0x[0-9a-fA-F]*[1-9a-fA-F][0-9a-fA-F]*\b", log))
    stage_i_rt_clear = (
        "STAGE_I_RT_CLEAR_READY method=fullscreen_triangle vertices=3 "
        "color_dma=false" in log)
    stage_e_required = ((
        "STAGE_E_PREFLIGHT_COMPLETE", "STAGE_I_DOUBLE_PIPELINE_READY",
        "STAGE_I_TELEMETRY_END", "STAGE_I_LOOP_COMPLETE",
        "STAGE_I_GUARDS_INTACT color=true depth=true",
        "STAGE_I_VISIBLE_HOLD_COMPLETE", "STAGE_E_SHADER_ARENA_SCRUBBED",
        "STAGE_E_COMPLETE cleanup complete",
    ) if stage_i else (
        "STAGE_E_PREFLIGHT_COMPLETE", "stage_e_submit=0x00000000",
        "STAGE_E_GUARDS_INTACT", "STAGE_E_RECOVERY_BUFFER_UNTOUCHED",
        "STAGE_E_VISIBLE_HOLD_COMPLETE", "STAGE_E_SHADER_ARENA_SCRUBBED",
        "STAGE_E_COMPLETE cleanup complete",
    ))
    stage_e_complete = (not stage_e or all(item in log for item in stage_e_required))
    if stage_i:
        stage_e_complete = (stage_e_complete and stage_i_count_exact and
                            stage_i_pipeline_metrics and stage_i_rt_clear)
    if transaction and fence and videoout and normal_exit and not markers and stage_e_complete:
        ordered_markers = [transaction_marker]
        if stage_i:
            ordered_markers += [fence_marker, videoout_marker,
                                "STAGE_I_GUARDS_INTACT color=true depth=true",
                                "STAGE_I_LOOP_COMPLETE",
                                "STAGE_I_VISIBLE_HOLD_COMPLETE",
                                "STAGE_E_SHADER_ARENA_SCRUBBED"]
        else:
            ordered_markers += [fence_marker, videoout_marker]
        if stage_e and not stage_i:
            ordered_markers += ["STAGE_E_VISIBLE_HOLD_COMPLETE",
                                "STAGE_E_SHADER_ARENA_SCRUBBED"]
        ordered_markers += ["AGC stage B exit result=0"]
        ordered = all(log.index(a) < log.index(b)
                      for a, b in zip(ordered_markers, ordered_markers[1:]))

    if markers:
        state = State.PARKED
        reason = "SetFlip/submit/presentation state uncertain; retain every resource"
    elif ordered:
        state = State.PRESENT_COMPLETE
        reason = "GPU fence and VideoOut completion precede normal exit"
    elif any_exit and not transaction and pre_transaction_cleanup:
        state = State.PRE_TRANSACTION_EXIT
        reason = "probe cleaned up and exited before SetFlip could reserve presentation state"
    elif not log.strip():
        state = State.NOT_STARTED
        reason = "no stage-B log"
    else:
        state = State.UNKNOWN_RETAIN
        reason = "active, truncated, stale or contradictory log cannot prove presentation completion"

    cleanup_allowed = state in (State.PRE_TRANSACTION_EXIT, State.PRESENT_COMPLETE)
    unsafe = [
        "close_ppsa99998",
        "launch_title",
        "launch_payload",
        "unregister_video_buffers",
        "delete_videoout_event",
        "close_videoout",
        "unmap_command_memory",
        "unmap_video_memory",
        "release_direct_memory",
        "unload_agc_driver",
    ]
    return {
        "state": state.value,
        "cleanup_allowed": cleanup_allowed,
        "close_allowed": cleanup_allowed,
        "completion_proven": state is State.PRESENT_COMPLETE,
        "transaction_started_or_possible": transaction,
        "gpu_fence_proven": fence and not markers,
        "videoout_completion_proven": videoout and not markers,
        "completion_markers_ordered": ordered,
        "stage_e": stage_e,
        "stage_i": stage_i,
        "stage_e_completion_contract": stage_e_complete,
        "pre_transaction_cleanup_proven": pre_transaction_cleanup,
        "park_markers": markers,
        "retain_all_resources": not cleanup_allowed,
        "reason": reason,
        "automated_actions_allowed": (
            ["record_state", "verified_cleanup", "verified_close"]
            if cleanup_allowed else
            ["read_only_health", "record_state", "stop_automation"]
        ),
        "automated_actions_forbidden": unsafe if not cleanup_allowed else [],
        "operator_recovery": (
            "retain PPSA99998 and all resources; do not run cleanup or Close Game"
            if not cleanup_allowed else "none"
        ),
    }
