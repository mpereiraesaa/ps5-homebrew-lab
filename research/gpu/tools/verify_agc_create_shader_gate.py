#!/usr/bin/env python3
"""Final reproducibility verifier for the host-only CreateShader CPU gate."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SHA = re.compile(r"^[0-9a-f]{64}$")


def require(value: bool, message: str) -> None:
    if not value:
        raise SystemExit(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-proof", type=Path, required=True)
    parser.add_argument("--corpus-proof", type=Path, required=True)
    parser.add_argument("--callsite-proof", type=Path, required=True)
    args = parser.parse_args()
    static = json.loads(args.static_proof.read_text(encoding="utf-8"))
    corpus = json.loads(args.corpus_proof.read_text(encoding="utf-8"))
    callsites = json.loads(args.callsite_proof.read_text(encoding="utf-8"))

    symbol = static["symbol"]
    require(static["schema"] == 1 and static["firmware_scope"] == "12.02",
            "wrong static-proof scope")
    require(symbol["nid"] == "f3dg2CSgRKY" and symbol["offset"] == "0xef70" and
            symbol["size"] == 888 and symbol["system_runtime_equal"] and
            symbol["dynsym_export_verified"] and symbol["ghidra_analysis_equal"],
            "symbol/ABI proof mismatch")
    require(bool(SHA.fullmatch(symbol["sha256"])), "bad constructor hash")
    require(static["relocation_helper"]["system_runtime_equal"] and
            bool(SHA.fullmatch(static["relocation_helper"]["sha256"])),
            "relocation helper proof mismatch")
    require(static["dispatch"]["accepted_stage_range"] == [0, 7] and
            static["dispatch"]["stages_without_register_search"] == [4, 5],
            "stage dispatch mismatch")
    require(set(static["return_codes"]) == {
        "success", "bad_magic", "bad_version", "missing_stage_register",
        "already_bound", "runtime_unready", "target_policy", "target_helper",
    }, "return-code inventory mismatch")
    require(static["lifecycle"] == {
        "allocation_performed_by_export": False,
        "caller_owns_header_and_code": True,
        "destination_aliases_mutated_header": True,
        "destroy_shader_export_identified": False,
        "release_rule": "only after downstream references are zero and GPU/pipeline use is quiescent",
        "missing_stage_register_failure_occurs_after_mutation": True,
        "post_mutation_failure_action": "discard mutable copy; never retry it",
    }, "ownership/lifecycle proof mismatch")
    require(not static["console_contacted"] and not static["future_probe_authorized"],
            "static proof exceeded host-only scope")
    require(len(static["uncertainties"]) >= 4 and
            len(static["future_probe_conditions"]) >= 7,
            "uncertainties/probe conditions are incomplete")

    require(corpus["schema"] == 1 and corpus["firmware"] == "12.02",
            "wrong corpus-proof scope")
    require(corpus["authorized_pairs_planned"] == 47 and corpus["rejected_pairs"] == 0,
            "authorized corpus was not fully planned")
    for key in ("all_required_stage_registers_matched",
                "all_nested_user_data_ranges_bounded",
                "all_header_and_code_sizes_bounded",
                "cross_capture_relocated_outcomes"):
        require(corpus[key] is True, f"missing corpus invariant: {key}")
    require(bool(SHA.fullmatch(corpus["sanitized_plan_digest"])), "bad plan digest")
    for key in ("raw_bytes_emitted", "register_values_emitted", "console_contacted",
                "create_shader_called", "future_probe_authorized"):
        require(corpus[key] is False, f"scope violation: {key}")

    require(callsites["schema"] == 1 and callsites["firmware"] == "12.02",
            "wrong callsite-proof scope")
    require(callsites["direct_initializer_calls"] == 47 and
            callsites["generic_wrapper_calls"] == 1,
            "callsite inventory mismatch")
    for key in ("got_resolves_pinned_create_shader", "plt_thunk_verified",
                "all_three_arguments_correlated", "all_return_values_checked",
                "all_headers_match_cross_capture_relocated_outcomes"):
        require(callsites[key] is True, f"missing callsite invariant: {key}")
    for key in ("initializer_sha256", "sanitized_callsite_digest"):
        require(bool(SHA.fullmatch(callsites[key])), f"bad callsite hash: {key}")
    for key in ("raw_bytes_emitted", "shader_bytes_emitted", "console_contacted",
                "create_shader_called"):
        require(callsites[key] is False, f"callsite scope violation: {key}")

    print(json.dumps({
        "verified": True,
        "firmware": "12.02",
        "nid": symbol["nid"],
        "constructor_bytes": symbol["size"],
        "authorized_pairs_planned": corpus["authorized_pairs_planned"],
        "authorized_direct_callsites": callsites["direct_initializer_calls"],
        "sanitized_plan_digest": corpus["sanitized_plan_digest"],
        "console_contacted": False,
        "future_probe_authorized": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
