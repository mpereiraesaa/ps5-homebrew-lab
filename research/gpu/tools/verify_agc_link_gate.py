#!/usr/bin/env python3
"""Run the complete host-only sceAgcLinkShaders evidence gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agc_link_shaders_planner import Region, ShaderFacts, build_plan


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, stdout=subprocess.DEVNULL)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=Path("research/gpu/captures/agc-link-gate.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    tools = root / "research/gpu/tools"
    with tempfile.TemporaryDirectory(prefix="agc-link-gate-") as temporary:
        tmp = Path(temporary)
        proof_path, pair_path, transform_path = tmp / "proof.json", tmp / "pair.json", tmp / "transform.json"
        run([sys.executable, str(tools / "verify_agc_link_shaders.py"),
             "--output", str(proof_path)], root)
        run([sys.executable, str(tools / "verify_agc_link_pair.py"),
             "--output", str(pair_path)], root)
        run([sys.executable, str(tools / "verify_agc_link_host_transform.py"),
             "--output", str(transform_path)], root)
        run([sys.executable, str(tools / "test_agc_link_shaders_planner.py")], root)
        proof = json.loads(proof_path.read_text())
        pair = json.loads(pair_path.read_text())
        transform = json.loads(transform_path.read_text())

    pre_meta, pixel_meta = pair["pre_raster"], pair["pixel"]
    pre = ShaderFacts("pre_raster", pre_meta["type_raw"], 0x3000, pre_meta["bytes"],
                      0x3080, 0x30, 0x30C0, tuple(pre_meta["input_keys"]),
                      0x3100, tuple(pre_meta["output_keys"]), 0x3120,
                      pre_meta["cx_register_count"], 0x3180, pre_meta["sh_register_count"],
                      tuple((0x31A0 + i * 0x10, n) if n else (0, 0)
                            for i, n in enumerate(pre_meta["resource_group_counts"])), True)
    pixel = ShaderFacts("pixel", pixel_meta["type_raw"], 0x4000, pixel_meta["bytes"],
                        0x4080, 0x30, 0x40C0, tuple(pixel_meta["input_keys"]),
                        0, tuple(pixel_meta["output_keys"]), 0x4120,
                        pixel_meta["cx_register_count"], 0x4180, pixel_meta["sh_register_count"],
                        tuple((0x41A0 + i * 0x10, n) if n else (0, 0)
                              for i, n in enumerate(pixel_meta["resource_group_counts"])), True)
    plan = build_plan(
        Region(0x1000, 0x110, True, True, "cx"),
        Region(0x2000, 0x18, True, True, "uc"),
        Region(0x3000, 0x200, True, False, "pre"),
        Region(0x4000, 0x200, True, False, "pixel"),
        pre, pixel, pair["pair_selection"]["primitive_type"],
        outputs_fresh=True, ownership_proven=True)
    if plan["matched_semantic_keys"] != [15]:
        raise SystemExit("selected pair did not pass the planner")
    if proof["symbol"]["nid"] != "MqAdbRMdNz4" or proof["symbol"]["size"] != 1180:
        raise SystemExit("symbol proof mismatch")
    if not (transform["selected_pair_deterministic"] and transform["all_canaries_intact"] and
            transform["all_inputs_unchanged"] and transform["all_returns_zero"] and
            transform["selected_outputs_fully_overwritten_by_prefill_differential"]):
        raise SystemExit("host transform proof is incomplete")
    commercial_ref_paths = [
        root / "research/gpu/captures/san-andreas-agc-import-refs.json",
        root / "research/gpu/sessions/game-eboot-agc-refs.json",
    ]
    commercial_refs = [json.loads(path.read_text()) for path in commercial_ref_paths]
    for refs in commercial_refs:
        if any(item.get("target_offset") == "0x103f0" for item in refs["references"]):
            raise SystemExit("commercial capture unexpectedly imports LinkShaders directly")

    result = {
        "schema": 1, "firmware_scope": "12.02", "gate": "PASS",
        "symbol_nid": proof["symbol"]["nid"],
        "function_sha256": proof["symbol"]["sha256"],
        "function_bytes": proof["symbol"]["size"],
        "cx_bytes": proof["outputs"]["cx_bytes"],
        "uc_bytes": proof["outputs"]["uc_bytes"],
        "primitive_mapping": proof["primitive"]["mapping"],
        "contract": {
            "stages": proof["stages"], "alignment": proof["alignment"],
            "workspace": proof["workspace"], "outputs": proof["outputs"],
            "return_codes": {"only_observed_and_reachable": 0},
            "ownership": "caller retains inputs and outputs through pipeline/GPU quiescence",
            "aliasing": "planner rejects every overlapping region",
            "rollback": "fresh outputs are discarded before publication on any indeterminate state",
        },
        "pair_id": pair["pair_id"], "pair_callsite_sha256": pair["pair_selection"]["callsite_sha256"],
        "pair_header_hashes": [pre_meta["header_sha256"], pixel_meta["header_sha256"]],
        "pair_code_hashes": [pre_meta["code_sha256"], pixel_meta["code_sha256"]],
        "matched_semantic_keys": plan["matched_semantic_keys"],
        "selected_cx_sha256": transform["selected_cx_sha256"],
        "selected_uc_sha256": transform["selected_uc_sha256"],
        "host_transform_cases": len(transform["cases"]),
        "output_canaries_intact": True,
        "outputs_fully_overwritten": True,
        "inputs_unchanged": True,
        "register_resource_compatibility": pair["compatibility"],
        "positive_planner_cases": 1, "negative_planner_cases": 17,
        "raw_bytes_emitted": False, "console_contacted": False,
        "console_calls": 0, "gpu_submission": False,
        "public_corroboration": {
            "prosper_commit": "df1bbae324714bbfc2c0b1a2743c2ab8c1d60bb6",
            "prosper_hle_sha256": "bd6c1ebae96eb668f0f97c881a894518775f9b74eb1f114019ad44d6a980f353",
            "kyty_provenance": "indirect through Prosper's MIT-ported layout and constructor notes",
            "prosperotv_commit": "fdee81e746308f7f2b27f7914a84eab678088fb6",
        },
        "owned_game_callsites": {
            "captures_checked": len(commercial_refs),
            "agc_import_references_checked": sum(len(x["references"]) for x in commercial_refs),
            "direct_link_shaders_imports": 0,
            "evidence_sha256": [file_sha(path) for path in commercial_ref_paths],
            "interpretation": "negative evidence only; selected pair comes from ProsperoTV",
        },
        "uncertainties": [
            "official public enum labels for every primitive value are incomplete",
            "optional auxiliary three-stage corpus pair has not been selected",
            "individual undocumented bits outside the named register fields remain opaque",
        ],
        "future_cpu_only_probe_conditions": [
            "separate explicit authorization for a console call",
            "exact selected input hashes and primitive 6",
            "fresh non-aliased CX/UC buffers with external canaries",
            "retained constructor-approved shader storage and bounded nested ranges",
            "no queue, DCB, PM4, submit, VideoOut, process write, or debugger",
            "cleanup path for normal and indeterminate outcomes",
        ],
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
