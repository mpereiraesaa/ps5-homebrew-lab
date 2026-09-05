#ifndef PS5_AGC_STAGE_E_PIPELINE_REGISTERS_H
#define PS5_AGC_STAGE_E_PIPELINE_REGISTERS_H

#include <stdint.h>

#include "../../../include/agc_link_shaders_contract.h"

enum {
    STAGE_E_RT_REGISTER_COUNT = 16,
    STAGE_E_VIEWPORT_REGISTER_COUNT = 15,
    STAGE_E_LINKED_CX_REGISTER_COUNT = 34,
    STAGE_E_PRE_RASTER_CX_REGISTER_COUNT = 10,
    STAGE_E_PIXEL_CX_REGISTER_COUNT = 9,
    STAGE_E_CX_REGISTER_COUNT = 84,
    STAGE_E_SH_REGISTER_COUNT = 12,
    STAGE_E_UC_REGISTER_COUNT = 3,
};

typedef struct StageEPipelineRegisters {
    AgcRegister1202 cx[STAGE_E_CX_REGISTER_COUNT];
    AgcRegister1202 sh[STAGE_E_SH_REGISTER_COUNT];
    AgcRegister1202 uc[STAGE_E_UC_REGISTER_COUNT];
} StageEPipelineRegisters;

int stage_e_build_pipeline_registers(
    StageEPipelineRegisters *out,
    const AgcRegister1202 render_target[STAGE_E_RT_REGISTER_COUNT],
    const AgcLinkedCx1202 *linked_cx,
    const AgcLinkedUc1202 *linked_uc,
    const AgcRegister1202 pre_raster_cx[STAGE_E_PRE_RASTER_CX_REGISTER_COUNT],
    const AgcRegister1202 pixel_cx[STAGE_E_PIXEL_CX_REGISTER_COUNT],
    const AgcRegister1202 pre_raster_sh[6],
    const AgcRegister1202 pixel_sh[6],
    uint32_t width, uint32_t height);

#endif
