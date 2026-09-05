#ifndef PS5_AGC_STAGE_E_SHADER_HEADER_H
#define PS5_AGC_STAGE_E_SHADER_HEADER_H

#include <stddef.h>
#include <stdint.h>

#include "../../../include/agc_create_shader_contract.h"

enum {
    STAGE_E_SHADER_PRE_RASTER = 2,
    STAGE_E_SHADER_PIXEL = 1,
    STAGE_E_HEADER_BYTES = 0x148,
    STAGE_E_USER_DATA_OFFSET = 0x60,
    STAGE_E_SPECIALS_OFFSET = 0x98,
    STAGE_E_CX_OFFSET = 0xc8,
    STAGE_E_SH_OFFSET = 0x118,
    STAGE_E_MAX_CX_REGISTERS = 10,
};

typedef struct StageEShaderSpecials {
    AgcShaderRegister ge_cntl;
    AgcShaderRegister vgt_shader_stages_en;
    uint32_t dispatch_modifier;
    uint16_t user_data_range_start;
    uint16_t user_data_range_end;
    uint64_t draw_modifier;
    AgcShaderRegister vgt_gs_out_prim_type;
    AgcShaderRegister ge_user_vgpr_en;
} StageEShaderSpecials;

typedef struct StageEShaderArena {
    AgcShaderHeader header;
    AgcShaderUserData user_data;
    StageEShaderSpecials specials;
    AgcShaderRegister cx[STAGE_E_MAX_CX_REGISTERS];
    AgcShaderRegister sh[6];
} StageEShaderArena;

int stage_e_build_shader_header(StageEShaderArena *arena, uint8_t type,
                                uint32_t shader_bytes);
int stage_e_validate_unrelocated_header(const StageEShaderArena *arena,
                                        uint8_t type, uint32_t shader_bytes);

#endif
