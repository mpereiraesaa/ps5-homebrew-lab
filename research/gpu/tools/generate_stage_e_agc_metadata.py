#!/usr/bin/env python3
"""Translate our own LLPC/PAL metadata into the Stage E AGC register subset."""
from __future__ import annotations

import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "research/gpu/captures/stage-e-gfx1013-pal-metadata.json"
OUTPUT = ROOT / "legacy/probes/ps5-agc-phase0/stage_e_compiled_metadata.h"
CAPTURE = ROOT / "research/gpu/captures/stage-e-gfx1013-agc-metadata.json"


def b(value: object) -> int:
    return int(bool(value))


def pack_array(values: list[int], width: int) -> int:
    return sum((value & ((1 << width) - 1)) << (index * width)
               for index, value in enumerate(values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--capture", type=Path, default=CAPTURE)
    args = parser.parse_args()
    source_path = args.source if args.source.is_absolute() else ROOT / args.source
    output = args.output if args.output.is_absolute() else ROOT / args.output
    capture = args.capture if args.capture.is_absolute() else ROOT / args.capture
    source = json.loads(source_path.read_text())
    if (source["target"], source["pipeline_type"], source["no_relocations"]) != (
            "gfx1013", "Ngg", True):
        raise SystemExit("expected a relocation-free gfx1013 NGG pipeline")
    g = source["graphics_register_metadata"]
    gs = source["stages"]["pre_raster_gs"]
    ps = source["stages"]["ps"]

    # Public PAL ABI mappings correspond directly to Kyty's public
    # ShaderDrawModifier bitfield. DrawIndexAuto supplies no index-buffer
    # offset; it does need the consecutive BaseVertex/BaseInstance SGPR pair
    # that LLPC reserves for the first graphics stage.
    user_map = {value for value in gs["user_data_reg_map"]
                if value != 0xFFFFFFFF}
    base_vertex = 0x10000003 in user_map
    base_instance = 0x10000004 in user_map
    draw_index = 0x10000005 in user_map
    draw_modifier = (b(base_vertex) << 0) | (b(base_instance) << 2) | \
                    (b(draw_index) << 3)
    if not (base_vertex and base_instance) or draw_index:
        raise SystemExit("unexpected gfx1013 DrawIndexAuto user-data ABI")

    onchip = g[".vgt_gs_onchip_cntl"]
    subgroup = g[".ge_ngg_subgrp_cntl"]
    stages = g[".vgt_shader_stages_en"]
    db = g[".db_shader_control"]
    ps_addr = g[".spi_ps_input_addr"]
    ps_ena = g[".spi_ps_input_ena"]
    bary = g[".spi_baryc_cntl"]

    def ps_inputs(fields: dict[str, object]) -> int:
        names = (".persp_sample_ena", ".persp_center_ena", ".persp_centroid_ena",
                 ".persp_pull_model_ena", ".linear_sample_ena", ".linear_center_ena",
                 ".linear_centroid_ena", ".line_stipple_tex_ena", ".pos_x_float_ena",
                 ".pos_y_float_ena", ".pos_z_float_ena", ".pos_w_float_ena",
                 ".front_face_ena", ".ancillary_ena", ".sample_coverage_ena",
                 ".pos_fixed_pt_ena")
        return sum(b(fields.get(name, False)) << bit for bit, name in enumerate(names))

    pre_cx = [
        (0x1FF, g[".max_verts_per_subgroup"] & 0x3ff),
        (0x2D3, (subgroup[".prim_amp_factor"] & 0x1ff) |
                  ((subgroup[".threads_per_subgroup"] & 0x1ff) << 9)),
        (0x207, 0),  # No clip/cull/misc exports in this shader.
        (0x1C2, g[".spi_shader_idx_format"] & 0xf),
        (0x1C3, pack_array(g[".spi_shader_pos_format"], 4)),
        (0x1B1, b(g[".spi_vs_out_config"].get(".no_pc_export")) << 7),
        (0x2AB, g[".vgt_esgs_ring_itemsize"] & 0x7fff),
        (0x2E4, 0),  # No API geometry-shader instancing.
        (0x2CE, g[".vgt_gs_max_vert_out"] & 0x7ff),
        (0x291, (onchip[".es_verts_per_subgroup"] & 0x7ff) |
                  ((onchip[".gs_prims_per_subgroup"] & 0x7ff) << 11) |
                  ((onchip[".gs_inst_prims_per_subgrp"] & 0x3ff) << 22)),
    ]
    db_value = (b(db.get(".z_export_enable")) |
                (b(db.get(".stencil_test_val_export_enable")) << 1) |
                ((db[".z_order"] & 3) << 4) |
                (b(db.get(".kill_enable")) << 6) |
                (b(db.get(".mask_export_enable")) << 8) |
                (b(db.get(".exec_on_hier_fail")) << 9) |
                (b(db.get(".exec_on_noop")) << 10) |
                (b(db.get(".alpha_to_mask_disable")) << 11) |
                (b(db.get(".depth_before_shader")) << 12) |
                ((db[".conservative_z_export"] & 3) << 13) |
                (b(db.get(".primitive_ordered_pixel_shader")) << 16) |
                (b(db.get(".pre_shader_depth_coverage_enable")) << 23))
    pixel_cx = [
        (0x08F, pack_array(list(g[".cb_shader_mask"].values()), 4)),
        (0x203, db_value),
        (0x310, (g[".pa_sc_shader_control"][".wave_break_region_size"] & 3) << 5),
        (0x1B8, ((bary[".pos_float_location"] & 3) << 16) |
                  (b(bary[".front_face_all_bits"]) << 24)),
        (0x1B4, ps_inputs(ps_addr)),
        (0x1B3, ps_inputs(ps_ena)),
        (0x1B6, (g[".spi_ps_in_control"][".num_interps"] & 0x3f) |
                  (b(ps["wavefront_size"] == 32) << 15)),
        (0x1C5, pack_array(list(g[".spi_shader_col_format"].values()), 4)),
        (0x1C4, 0),  # No depth/stencil/sample-mask export.
    ]

    def rsrc1(stage: dict[str, object], wave32: bool, comp: int, gs_stage: bool) -> int:
        vgprs = 0 if stage["vgpr_count"] == 0 else (stage["vgpr_count"] - 1) // (8 if wave32 else 4)
        sgprs = (stage["sgpr_count"] - 1) // 8
        value = vgprs | (sgprs << 6) | (192 << 12) | (1 << 21) | (1 << 25)
        if gs_stage:
            value |= b(stage.get("wgp_mode")) << 27 | ((comp & 3) << 29)
        return value

    gs_rsrc1 = rsrc1(gs, True, g[".gs_vgpr_comp_cnt"], True)
    gs_rsrc2 = (gs["user_sgprs"] & 0x1f) << 1 | ((g[".es_vgpr_comp_cnt"] & 3) << 16)
    ps_rsrc1 = rsrc1(ps, False, 0, False)
    ps_rsrc2 = (ps["user_sgprs"] & 0x1f) << 1
    ge_cntl = ((onchip[".gs_prims_per_subgroup"] & 0x1ff) |
               ((onchip[".es_verts_per_subgroup"] & 0x1ff) << 9))
    stages_en = ((stages.get(".es_stage_en", 0) & 3) << 3 |
                 (b(stages.get(".gs_stage_en")) << 5) |
                 ((stages.get(".vs_stage_en", 0) & 3) << 6) |
                 (b(stages.get(".primgen_en")) << 13) |
                 ((stages.get(".max_primgroup_in_wave", 0) & 0xf) << 15) |
                 (b(stages.get(".gs_w32_en")) << 22) |
                 (b(stages.get(".vs_w32_en")) << 23) |
                 (b(stages.get(".primgen_passthru_en")) << 25))

    def rows(name: str, registers: list[tuple[int, int]]) -> str:
        body = ",\n".join(f"    {{{offset:#05x}u, {value:#010x}u}}" for offset, value in registers)
        return f"static const AgcShaderRegister {name}[] = {{\n{body}\n}};"

    rendered = f"""#ifndef PS5_AGC_STAGE_E_COMPILED_METADATA_H
#define PS5_AGC_STAGE_E_COMPILED_METADATA_H
#include "../../include/agc_create_shader_contract.h"
/* Generated solely from our gfx1013 LLPC/PAL ELF. Do not hand-edit. */
#define STAGE_E_GS_ISA_BYTES {source['code_bytes']['pre_raster_gs']}u
#define STAGE_E_PS_ISA_BYTES {source['code_bytes']['ps']}u
#define STAGE_E_GS_RSRC1 {gs_rsrc1:#010x}u
#define STAGE_E_GS_RSRC2 {gs_rsrc2:#010x}u
#define STAGE_E_PS_RSRC1 {ps_rsrc1:#010x}u
#define STAGE_E_PS_RSRC2 {ps_rsrc2:#010x}u
#define STAGE_E_GE_CNTL {ge_cntl:#010x}u
#define STAGE_E_VGT_SHADER_STAGES_EN {stages_en:#010x}u
#define STAGE_E_VGT_GS_OUT_PRIM_TYPE 0x00000002u
#define STAGE_E_DRAW_MODIFIER {draw_modifier:#018x}ull
#define STAGE_E_DRAW_MODIFIER_DERIVED 1
{rows('stage_e_pre_raster_cx_template', pre_cx)}
{rows('stage_e_pixel_cx_template', pixel_cx)}
#endif
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    capture.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered)
    capture.write_text(json.dumps({
        "schema": 1, "source_sha256": source["sha256"], "target": "gfx1013",
        "pipeline_type": "Ngg", "pre_raster_cx_count": len(pre_cx),
        "pixel_cx_count": len(pixel_cx), "sh_count_each": 6,
        "vertex_index_abi": {
            "base_vertex": base_vertex,
            "base_instance": base_instance,
            "draw_index": draw_index,
            "draw_index_auto": True,
        },
        "draw_modifier": draw_modifier,
        "draw_modifier_derived": True, "private_values_used": False,
        "submit_authorized": False,
    }, indent=2, sort_keys=True) + "\n")
    print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
