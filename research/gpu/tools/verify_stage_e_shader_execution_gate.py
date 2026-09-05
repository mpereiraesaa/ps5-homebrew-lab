#!/usr/bin/env python3
"""Fail closed until Stage E has compiler-derived graphics metadata."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HEADER = ROOT / "legacy/probes/ps5-agc-phase0/stage_e_shader_header.c"
GENERATED = ROOT / "legacy/probes/ps5-agc-phase0/stage_e_compiled_metadata.h"
PIPELINE = ROOT / "legacy/probes/ps5-agc-phase0/stage_e_pipeline_registers.c"
PIPELINE_HEADER = ROOT / "legacy/probes/ps5-agc-phase0/stage_e_pipeline_registers.h"
PIPE = ROOT / "research/gpu/shaders/stage-e/fullscreen_triangle.pipe"
AUDIT = ROOT / "research/gpu/captures/agc-authorized-graphics-contract.json"
OUTPUT = ROOT / "research/gpu/captures/agc-stage-e-shader-execution-gate.json"
METADATA = ROOT / "research/gpu/captures/stage-e-gfx1013-pal-metadata.json"
AGC_METADATA = ROOT / "research/gpu/captures/stage-e-gfx1013-agc-metadata.json"
RUNTIME = ROOT / "legacy/apps/agc-native-sce/stage_b_main.cpp"
RUNTIME_CAPTURE = ROOT / "research/gpu/captures/agc-stage-e-centered-triangle-runtime.json"


def main() -> int:
    source = HEADER.read_text()
    generated = GENERATED.read_text()
    pipeline_source = PIPELINE.read_text()
    pipeline_header = PIPELINE_HEADER.read_text()
    audit = json.loads(AUDIT.read_text())
    current_cx_zero = not all(token in source for token in (
        "stage_e_pre_raster_cx_template", "stage_e_pixel_cx_template",
        "arena->header.num_cx_registers", "arena->header.cx_registers"))
    functional_corpus_has_cx = (
        audit["aggregate_histograms"]["cx_count"] == {"10": 1, "9": 15})
    pipe = PIPE.read_text()
    complete_pipeline_spec = all(token in pipe for token in (
        "gl_VertexIndex", "layout(location = 0) out vec4 color",
        "VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP",
        "VK_FORMAT_B8G8R8A8_UNORM", "channelWriteMask = 15"))
    elf = ROOT / "research/gpu/build/stage-e-shaders/fullscreen_triangle.pal.elf"
    metadata = json.loads(METADATA.read_text()) if METADATA.is_file() else {}
    agc_metadata = json.loads(AGC_METADATA.read_text()) \
        if AGC_METADATA.is_file() else {}
    compiler_metadata_valid = (
        elf.is_file() and metadata.get("target") == "gfx1013" and
        metadata.get("elf_machine_flags") == "0x42" and
        metadata.get("pipeline_type") == "Ngg" and
        metadata.get("no_relocations") is True and
        metadata.get("symbols") == {"pre_raster_gs": True, "ps": True})
    translated_metadata_valid = (
        agc_metadata.get("target") == "gfx1013" and
        agc_metadata.get("pipeline_type") == "Ngg" and
        agc_metadata.get("pre_raster_cx_count") == 10 and
        agc_metadata.get("pixel_cx_count") == 9 and
        agc_metadata.get("sh_count_each") == 6 and
        agc_metadata.get("draw_modifier_derived") is True and
        agc_metadata.get("private_values_used") is False and
        agc_metadata.get("vertex_index_abi") == {
            "base_vertex": True, "base_instance": True,
            "draw_index": False, "draw_index_auto": True})
    header_translation_complete = (
        not current_cx_zero and "STAGE_E_DRAW_MODIFIER_DERIVED 1" in generated and
        "arena->specials.draw_modifier = STAGE_E_DRAW_MODIFIER" in source)
    functional_builder_appends_shader_cx = (
        "STAGE_E_CX_REGISTER_COUNT = 84" in pipeline_header and
        pipeline_source.index("linked_cx, sizeof(*linked_cx)") <
        pipeline_source.index("pre_raster_cx,") <
        pipeline_source.index("pixel_cx,"))
    execution_gate_passed = (
        functional_corpus_has_cx and complete_pipeline_spec and
        compiler_metadata_valid and translated_metadata_valid and
        header_translation_complete and functional_builder_appends_shader_cx)
    runtime = RUNTIME.read_text()
    checkpoint = re.search(
        r"stage_e_runtime_checkpoint\s*=\s*(\d+)\s*;", runtime)
    checkpoint_visual = checkpoint is not None and int(checkpoint.group(1)) == 6
    branch_start = runtime.index("#ifdef STAGE_E_TRIANGLE", runtime.index(
        "auto *command_words"))
    branch_end = runtime.index("#elif defined(STAGE_D_VISIBLE_CLEAR)", branch_start)
    stage_e_submit_branch = runtime[branch_start:branch_end]
    unique_submit_path = (
        runtime.count("return sceAgcDriverSubmitDcb(&submit);") == 1 and
        runtime.count("submit_adapter(command_words") == 4 and
        stage_e_submit_branch.count("submit_adapter(command_words") == 3 and
        "if (stage_e_wait_flip_isolation != 0)" in stage_e_submit_branch and
        "} else {" in stage_e_submit_branch)
    runtime_capture = (json.loads(RUNTIME_CAPTURE.read_text())
                       if RUNTIME_CAPTURE.is_file() else {})
    hardware_validated = (
        runtime_capture.get("gpu_fence_zero") is True and
        runtime_capture.get("videoout_event_exact") is True and
        runtime_capture.get("teardown_complete") is True)
    submit_authorized = (execution_gate_passed and checkpoint_visual and
                         unique_submit_path)
    result = {
        "schema": 1,
        "firmware_scope": "12.02",
        "current_stage_e_header_declares_zero_cx": current_cx_zero,
        "authorized_graphics_headers_with_nonzero_cx": functional_corpus_has_cx,
        "functional_builder_appends_shader_cx": functional_builder_appends_shader_cx,
        "complete_own_pipeline_spec_present": complete_pipeline_spec,
        "compiler_derived_pal_metadata_valid": compiler_metadata_valid,
        "translated_agc_metadata_valid": translated_metadata_valid,
        "header_translation_complete": header_translation_complete,
        "execution_gate_passed": execution_gate_passed,
        "runtime_checkpoint_visual": checkpoint_visual,
        "unique_submit_path": unique_submit_path,
        "iteration_mode": "bounded_classified_retries",
        "hardware_validated": hardware_validated,
        "hardware_validation_capture": str(RUNTIME_CAPTURE.relative_to(ROOT)),
        "submit_authorized": submit_authorized,
        "submit_ready": submit_authorized,
        "required_next_artifact": str(elf.relative_to(ROOT)),
        "raw_proprietary_bytes_emitted": False,
        "proprietary_register_values_emitted": False,
        "console_contacted": False,
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
