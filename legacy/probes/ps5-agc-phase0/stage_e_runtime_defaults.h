#ifndef PS5_AGC_STAGE_E_RUNTIME_DEFAULTS_H
#define PS5_AGC_STAGE_E_RUNTIME_DEFAULTS_H

#include "../../../include/agc_register_defaults_layout.h"
#include "stage_e_color_target.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    STAGE_E_FW_1202_DEFAULT_COUNT = 137,
    STAGE_E_FW_1202_CX_COUNT = 84,
};

int stage_e_find_runtime_color_default_index(const AgcRegisterDefaults *root,
                                             uint32_t *index_out);

/* Resolve the public MRT0 default block by semantic key from the table
 * returned to this process by sceAgcGetRegisterDefaults(). */
int stage_e_select_runtime_color_defaults(
    AgcRegister1202 out[STAGE_E_COLOR_REGISTER_COUNT],
    const AgcRegisterDefaults *root);

#ifdef __cplusplus
}
#endif

#endif
