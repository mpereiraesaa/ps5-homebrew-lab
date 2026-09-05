#ifndef HOMEBREW_PS5_STAGE_G_DEPTH_STATE_H
#define HOMEBREW_PS5_STAGE_G_DEPTH_STATE_H

#include <stddef.h>
#include <stdint.h>

#include "../../../include/agc_link_shaders_contract.h"

enum {
    STAGE_G_DSV_REGISTER_COUNT = 21,
    STAGE_G_DEPTH_REGISTER_COUNT = 22,
};

/* Entries before DSV_REGISTER_COUNT bind the complete view while depth testing
 * stays disabled. The final entry enables D32 read/write with LESS_EQUAL. */
int stage_g_build_d32_no_htile(
    AgcRegister1202 out[STAGE_G_DEPTH_REGISTER_COUNT], uintptr_t depth_address,
    uint32_t width, uint32_t height);

#endif
