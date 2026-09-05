#include "stage_e_pipeline_registers.h"

#include <string.h>

_Static_assert(sizeof(StageEPipelineRegisters) == 0x318,
               "Stage E register plan ABI");
_Static_assert(sizeof(AgcLinkedCx1202) ==
               STAGE_E_LINKED_CX_REGISTER_COUNT * sizeof(AgcRegister1202),
               "linked CX count");
_Static_assert(sizeof(AgcLinkedUc1202) ==
               STAGE_E_UC_REGISTER_COUNT * sizeof(AgcRegister1202),
               "linked UC count");

static const uint32_t rt_offsets[STAGE_E_RT_REGISTER_COUNT] = {
    0x318, 0x31b, 0x31c, 0x31d, 0x31e, 0x31f, 0x321, 0x323,
    0x324, 0x325, 0x390, 0x398, 0x3a0, 0x3a8, 0x3b0, 0x3b8,
};

static uint32_t float_bits(float value)
{
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

int stage_e_build_pipeline_registers(
    StageEPipelineRegisters *out,
    const AgcRegister1202 render_target[STAGE_E_RT_REGISTER_COUNT],
    const AgcLinkedCx1202 *linked_cx,
    const AgcLinkedUc1202 *linked_uc,
    const AgcRegister1202 pre_raster_cx[STAGE_E_PRE_RASTER_CX_REGISTER_COUNT],
    const AgcRegister1202 pixel_cx[STAGE_E_PIXEL_CX_REGISTER_COUNT],
    const AgcRegister1202 pre_raster_sh[6],
    const AgcRegister1202 pixel_sh[6],
    uint32_t width, uint32_t height)
{
    if (!out || !render_target || !linked_cx || !linked_uc ||
        !pre_raster_cx || !pixel_cx || !pre_raster_sh || !pixel_sh ||
        !width || !height ||
        width > UINT16_MAX || height > UINT16_MAX)
        return -1;
    for (uint32_t i = 0; i < STAGE_E_RT_REGISTER_COUNT; ++i)
        if (render_target[i].offset != rt_offsets[i]) return -2;

    memset(out, 0, sizeof(*out));
    memcpy(out->cx, render_target,
           STAGE_E_RT_REGISTER_COUNT * sizeof(AgcRegister1202));
    AgcRegister1202 viewport[STAGE_E_VIEWPORT_REGISTER_COUNT] = {
        {0x10f, float_bits((float)width * 0.5f)},
        {0x110, float_bits((float)width * 0.5f)},
        {0x111, float_bits((float)height * -0.5f)},
        {0x112, float_bits((float)height * 0.5f)},
        {0x113, float_bits(1.0f)}, {0x114, 0},
        {0x0b4, 0}, {0x0b5, float_bits(1.0f)},
        {0x2fa, float_bits(1.0f)}, {0x2fb, float_bits(1.0f)},
        {0x2fc, float_bits(1.0f)}, {0x2fd, float_bits(1.0f)},
        {0x090, UINT32_C(0x80000000)},
        {0x091, width | (height << 16)},
        {0x08e, UINT32_C(0x0000000f)},
    };
    memcpy(out->cx + STAGE_E_RT_REGISTER_COUNT, viewport, sizeof(viewport));
    memcpy(out->cx + STAGE_E_RT_REGISTER_COUNT + STAGE_E_VIEWPORT_REGISTER_COUNT,
           linked_cx, sizeof(*linked_cx));
    const uint32_t shader_cx_base = STAGE_E_RT_REGISTER_COUNT +
                                    STAGE_E_VIEWPORT_REGISTER_COUNT +
                                    STAGE_E_LINKED_CX_REGISTER_COUNT;
    memcpy(out->cx + shader_cx_base, pre_raster_cx,
           STAGE_E_PRE_RASTER_CX_REGISTER_COUNT * sizeof(AgcRegister1202));
    memcpy(out->cx + shader_cx_base + STAGE_E_PRE_RASTER_CX_REGISTER_COUNT,
           pixel_cx,
           STAGE_E_PIXEL_CX_REGISTER_COUNT * sizeof(AgcRegister1202));
    memcpy(out->sh, pre_raster_sh, 6 * sizeof(AgcRegister1202));
    memcpy(out->sh + 6, pixel_sh, 6 * sizeof(AgcRegister1202));
    memcpy(out->uc, linked_uc, sizeof(*linked_uc));
    return 0;
}
