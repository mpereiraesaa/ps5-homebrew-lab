#ifndef PS5_AGC_STAGE_E_COLOR_TARGET_H
#define PS5_AGC_STAGE_E_COLOR_TARGET_H

#include <stdint.h>

#include "../../../include/agc_link_shaders_contract.h"

enum { STAGE_E_COLOR_REGISTER_COUNT = 16 };

/* Builds the MRT0 SDR descriptor from the matching FW register defaults.
 * Defaults are an explicit caller input and are never embedded here. */
int stage_e_build_color_target(
    AgcRegister1202 out[STAGE_E_COLOR_REGISTER_COUNT],
    const AgcRegister1202 defaults[STAGE_E_COLOR_REGISTER_COUNT],
    uintptr_t address, uint32_t width, uint32_t height);

#endif
