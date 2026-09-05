#ifndef HOMEBREW_PS5_AGC_LINK_SHADERS_CONTRACT_H
#define HOMEBREW_PS5_AGC_LINK_SHADERS_CONTRACT_H

#include <stddef.h>
#include <stdint.h>

/* Host-side documentation types for FW 12.02. These are not Sony SDK headers. */
typedef struct AgcRegister1202 {
    uint32_t offset;
    uint32_t value;
} AgcRegister1202;

typedef struct AgcLinkedCx1202 {
    AgcRegister1202 spi_ps_input_cntl[32];
    AgcRegister1202 vgt_shader_stages_en;
    AgcRegister1202 vgt_gs_out_prim_type;
} AgcLinkedCx1202;

typedef struct AgcLinkedUc1202 {
    AgcRegister1202 ge_cntl;
    AgcRegister1202 ge_user_vgpr_en;
    AgcRegister1202 vgt_primitive_type;
} AgcLinkedUc1202;

typedef int32_t (*AgcLinkShaders1202Fn)(
    AgcLinkedCx1202 *cx,
    AgcLinkedUc1202 *uc,
    const void *optional_aux_pre_raster_shader,
    const void *primary_pre_raster_shader,
    const void *pixel_shader,
    uint32_t primitive_type);

#if defined(__cplusplus)
static_assert(sizeof(AgcLinkedCx1202) == 0x110, "FW 12.02 CX size");
static_assert(sizeof(AgcLinkedUc1202) == 0x18, "FW 12.02 UC size");
static_assert(offsetof(AgcLinkedCx1202, vgt_shader_stages_en) == 0x100, "CX stage offset");
static_assert(offsetof(AgcLinkedCx1202, vgt_gs_out_prim_type) == 0x108, "CX primitive offset");
static_assert(offsetof(AgcLinkedUc1202, vgt_primitive_type) == 0x10, "UC primitive offset");
#else
_Static_assert(sizeof(AgcLinkedCx1202) == 0x110, "FW 12.02 CX size");
_Static_assert(sizeof(AgcLinkedUc1202) == 0x18, "FW 12.02 UC size");
_Static_assert(offsetof(AgcLinkedCx1202, vgt_shader_stages_en) == 0x100, "CX stage offset");
_Static_assert(offsetof(AgcLinkedCx1202, vgt_gs_out_prim_type) == 0x108, "CX primitive offset");
_Static_assert(offsetof(AgcLinkedUc1202, vgt_primitive_type) == 0x10, "UC primitive offset");
#endif

#endif
