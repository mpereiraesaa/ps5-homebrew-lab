#ifndef PS5_AGC_STAGE_E_COMPILED_METADATA_H
#define PS5_AGC_STAGE_E_COMPILED_METADATA_H
#include "../../../include/agc_create_shader_contract.h"
/* Generated solely from our gfx1013 LLPC/PAL ELF. Do not hand-edit. */
#define STAGE_E_GS_ISA_BYTES 264u
#define STAGE_E_PS_ISA_BYTES 140u
#define STAGE_E_GS_RSRC1 0x2a2c0101u
#define STAGE_E_GS_RSRC2 0x00000028u
#define STAGE_E_PS_RSRC1 0x022c0001u
#define STAGE_E_PS_RSRC2 0x00000002u
#define STAGE_E_GE_CNTL 0x0000fc80u
#define STAGE_E_VGT_SHADER_STAGES_EN 0x02412010u
#define STAGE_E_VGT_GS_OUT_PRIM_TYPE 0x00000002u
#define STAGE_E_DRAW_MODIFIER 0x0000000000000005ull
#define STAGE_E_DRAW_MODIFIER_DERIVED 1
static const AgcShaderRegister stage_e_pre_raster_cx_template[] = {
    {0x1ffu, 0x00000080u},
    {0x2d3u, 0x00020001u},
    {0x207u, 0x00000000u},
    {0x1c2u, 0x00000001u},
    {0x1c3u, 0x00000004u},
    {0x1b1u, 0x00000000u},
    {0x2abu, 0x00000001u},
    {0x2e4u, 0x00000000u},
    {0x2ceu, 0x00000001u},
    {0x291u, 0x2004007eu}
};
static const AgcShaderRegister stage_e_pixel_cx_template[] = {
    {0x08fu, 0x0000000fu},
    {0x203u, 0x00000810u},
    {0x310u, 0x00000000u},
    {0x1b8u, 0x01000000u},
    {0x1b4u, 0x00000002u},
    {0x1b3u, 0x00000002u},
    {0x1b6u, 0x00000001u},
    {0x1c5u, 0x00000004u},
    {0x1c4u, 0x00000000u}
};
#endif
