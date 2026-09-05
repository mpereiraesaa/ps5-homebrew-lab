#include "stage_e_shader_header.h"
#ifdef STAGE_H_GEARS_METADATA
#include "stage_h_compiled_metadata.h"
#elif defined(STAGE_F_CUBE_METADATA)
#include "stage_f_compiled_metadata.h"
#else
#include "stage_e_compiled_metadata.h"
#endif

#include <string.h>

_Static_assert(sizeof(StageEShaderSpecials) == 0x30, "specials ABI");
_Static_assert(offsetof(StageEShaderArena, user_data) == STAGE_E_USER_DATA_OFFSET,
               "user-data placement");
_Static_assert(offsetof(StageEShaderArena, specials) == STAGE_E_SPECIALS_OFFSET,
               "specials placement");
_Static_assert(offsetof(StageEShaderArena, cx) == STAGE_E_CX_OFFSET,
               "CX placement");
_Static_assert(offsetof(StageEShaderArena, sh) == STAGE_E_SH_OFFSET,
               "SH placement");
_Static_assert(sizeof(StageEShaderArena) == STAGE_E_HEADER_BYTES,
               "arena size");

enum {
    SPI_SHADER_PGM_CHKSUM_PS = 0x006,
    SPI_SHADER_PGM_LO_PS = 0x008,
    SPI_SHADER_PGM_RSRC1_PS = 0x00a,
    SPI_SHADER_PGM_RSRC2_PS = 0x00b,
    SPI_SHADER_PGM_CHKSUM_GS = 0x080,
    SPI_SHADER_PGM_RSRC1_GS = 0x08a,
    SPI_SHADER_PGM_RSRC2_GS = 0x08b,
    SPI_SHADER_PGM_LO_ES = 0x0c8,
    GE_CNTL = 0x25b,
    VGT_SHADER_STAGES_EN = 0x2d5,
    VGT_GS_OUT_PRIM_TYPE = 0x2ce,
    GE_USER_VGPR_EN = 0x25c,
};

static void *self_relative(void *field, void *target)
{
    return (void *)((uintptr_t)target - (uintptr_t)field);
}

int stage_e_build_shader_header(StageEShaderArena *arena, uint8_t type,
                                uint32_t shader_bytes)
{
    if (!arena || shader_bytes < 0x30u || (shader_bytes & 3u) != 0 ||
        (type != STAGE_E_SHADER_PRE_RASTER && type != STAGE_E_SHADER_PIXEL))
        return -1;
    memset(arena, 0, sizeof(*arena));
    arena->header.file_header = UINT32_C(0x34333231);
    arena->header.version = UINT32_C(0x18);
    /* FW 12.02 unconditionally dereferences this structure after relocating
     * header+0x08. Its nested arrays may be absent when their counts are zero. */
    arena->header.user_data = (AgcShaderUserData *)self_relative(
        &arena->header.user_data, &arena->user_data);
    arena->header.sh_registers = (AgcShaderRegister *)self_relative(
        &arena->header.sh_registers, arena->sh);
    arena->header.cx_registers = (AgcShaderRegister *)self_relative(
        &arena->header.cx_registers, arena->cx);
    arena->header.specials = self_relative(&arena->header.specials,
                                           &arena->specials);
    arena->header.header_size = sizeof(*arena);
    arena->header.shader_size = shader_bytes;
    arena->header.target = 5;
    arena->header.special_sizes_bytes = sizeof(arena->specials);
    arena->header.type = type;
    arena->header.num_sh_registers = 6;
    arena->specials.ge_cntl = (AgcShaderRegister){GE_CNTL,
        type == STAGE_E_SHADER_PRE_RASTER ? STAGE_E_GE_CNTL : 0};
    arena->specials.vgt_shader_stages_en = (AgcShaderRegister){VGT_SHADER_STAGES_EN,
        type == STAGE_E_SHADER_PRE_RASTER ? STAGE_E_VGT_SHADER_STAGES_EN : 0};
    arena->specials.vgt_gs_out_prim_type = (AgcShaderRegister){VGT_GS_OUT_PRIM_TYPE,
        type == STAGE_E_SHADER_PRE_RASTER ? STAGE_E_VGT_GS_OUT_PRIM_TYPE : 0};
    arena->specials.ge_user_vgpr_en.offset = GE_USER_VGPR_EN;
    arena->specials.draw_modifier = STAGE_E_DRAW_MODIFIER;
    if (type == STAGE_E_SHADER_PIXEL) {
        arena->header.num_cx_registers =
            sizeof(stage_e_pixel_cx_template) / sizeof(stage_e_pixel_cx_template[0]);
        memcpy(arena->cx, stage_e_pixel_cx_template,
               sizeof(stage_e_pixel_cx_template));
        arena->sh[0].offset = SPI_SHADER_PGM_CHKSUM_PS;
        arena->sh[1].offset = SPI_SHADER_PGM_CHKSUM_PS;
        arena->sh[2].offset = SPI_SHADER_PGM_LO_PS;
        arena->sh[3].offset = SPI_SHADER_PGM_LO_PS + 1u;
        arena->sh[4] = (AgcShaderRegister){SPI_SHADER_PGM_RSRC1_PS,
                                          STAGE_E_PS_RSRC1};
        arena->sh[5] = (AgcShaderRegister){SPI_SHADER_PGM_RSRC2_PS,
                                          STAGE_E_PS_RSRC2};
    } else {
        arena->header.num_cx_registers =
            sizeof(stage_e_pre_raster_cx_template) /
            sizeof(stage_e_pre_raster_cx_template[0]);
        memcpy(arena->cx, stage_e_pre_raster_cx_template,
               sizeof(stage_e_pre_raster_cx_template));
        arena->sh[0].offset = SPI_SHADER_PGM_CHKSUM_GS;
        arena->sh[1].offset = SPI_SHADER_PGM_CHKSUM_GS;
        arena->sh[2] = (AgcShaderRegister){SPI_SHADER_PGM_RSRC1_GS,
                                          STAGE_E_GS_RSRC1};
        arena->sh[3] = (AgcShaderRegister){SPI_SHADER_PGM_RSRC2_GS,
                                          STAGE_E_GS_RSRC2};
        arena->sh[4].offset = SPI_SHADER_PGM_LO_ES;
        arena->sh[5].offset = SPI_SHADER_PGM_LO_ES + 1u;
    }
    return 0;
}

int stage_e_validate_unrelocated_header(const StageEShaderArena *arena,
                                        uint8_t type, uint32_t shader_bytes)
{
    if (!arena || arena->header.file_header != UINT32_C(0x34333231) ||
        arena->header.version != UINT32_C(0x18) || arena->header.code ||
        arena->header.type != type || arena->header.target != 5 ||
        arena->header.header_size != sizeof(*arena) ||
        arena->header.shader_size != shader_bytes ||
        arena->header.num_sh_registers != 6 ||
        arena->header.special_sizes_bytes != sizeof(arena->specials) ||
        arena->specials.draw_modifier != STAGE_E_DRAW_MODIFIER)
        return -1;
    uintptr_t sh = (uintptr_t)&arena->header.sh_registers +
                   (uintptr_t)arena->header.sh_registers;
    uintptr_t specials = (uintptr_t)&arena->header.specials +
                         (uintptr_t)arena->header.specials;
    if (sh != (uintptr_t)arena->sh || specials != (uintptr_t)&arena->specials)
        return -2;
    uintptr_t user_data = (uintptr_t)&arena->header.user_data +
                          (uintptr_t)arena->header.user_data;
    uintptr_t cx = (uintptr_t)&arena->header.cx_registers +
                   (uintptr_t)arena->header.cx_registers;
    if (user_data != (uintptr_t)&arena->user_data || cx != (uintptr_t)arena->cx ||
        arena->header.input_semantics || arena->header.output_semantics ||
        arena->header.num_input_semantics || arena->header.num_output_semantics ||
        arena->header.num_cx_registers !=
            (type == STAGE_E_SHADER_PIXEL ? 9u : 10u))
        return -3;
    if (arena->user_data.direct_resource_offsets ||
        arena->user_data.sharp_resource_offsets[0] ||
        arena->user_data.sharp_resource_offsets[1] ||
        arena->user_data.sharp_resource_offsets[2] ||
        arena->user_data.sharp_resource_offsets[3] ||
        arena->user_data.direct_resource_count ||
        arena->user_data.sharp_resource_count[0] ||
        arena->user_data.sharp_resource_count[1] ||
        arena->user_data.sharp_resource_count[2] ||
        arena->user_data.sharp_resource_count[3])
        return -7;
    if (type == STAGE_E_SHADER_PIXEL &&
        (arena->sh[0].offset != SPI_SHADER_PGM_CHKSUM_PS ||
         arena->sh[1].offset != SPI_SHADER_PGM_CHKSUM_PS ||
         arena->sh[2].offset != SPI_SHADER_PGM_LO_PS ||
         arena->sh[3].offset != SPI_SHADER_PGM_LO_PS + 1u ||
         arena->sh[4].offset != SPI_SHADER_PGM_RSRC1_PS ||
         arena->sh[4].value != STAGE_E_PS_RSRC1 ||
         arena->sh[5].offset != SPI_SHADER_PGM_RSRC2_PS ||
         arena->sh[5].value != STAGE_E_PS_RSRC2 ||
         memcmp(arena->cx, stage_e_pixel_cx_template,
                sizeof(stage_e_pixel_cx_template)) != 0))
        return -5;
    if (type == STAGE_E_SHADER_PRE_RASTER &&
        (arena->sh[0].offset != SPI_SHADER_PGM_CHKSUM_GS ||
         arena->sh[1].offset != SPI_SHADER_PGM_CHKSUM_GS ||
         arena->sh[2].offset != SPI_SHADER_PGM_RSRC1_GS ||
         arena->sh[2].value != STAGE_E_GS_RSRC1 ||
         arena->sh[3].offset != SPI_SHADER_PGM_RSRC2_GS ||
         arena->sh[3].value != STAGE_E_GS_RSRC2 ||
         arena->sh[4].offset != SPI_SHADER_PGM_LO_ES ||
         arena->sh[5].offset != SPI_SHADER_PGM_LO_ES + 1u ||
         memcmp(arena->cx, stage_e_pre_raster_cx_template,
                sizeof(stage_e_pre_raster_cx_template)) != 0))
        return -6;
    return 0;
}
