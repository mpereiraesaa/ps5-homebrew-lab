#ifndef HOMEBREW_PS5_AGC_COMPAT_H
#define HOMEBREW_PS5_AGC_COMPAT_H

/* Historical lab compatibility layer. The public project owns the canonical
 * sanitized ABI; do not duplicate common declarations here. */
#include "../../../projects/ps5-agc-gears/include/ps5_agc.h"

typedef ps5_agc_register Ps5AgcShaderRegister;

/* Experimental historical imports that are not part of the public demo ABI. */
uint32_t *sceAgcDcbDrawIndex(
    void *writer, uint32_t index_count, const void *gpu_index_address,
    uint64_t modifier);
int32_t sceAgcSuspendPoint(void);

static inline uint32_t *ps5AgcDcbFillL2Sync(
    void *writer, void *gpu_destination, uint32_t repeated_word,
    uint32_t byte_count)
{
    return ps5_agc_dcb_fill_l2_sync(
        writer, gpu_destination, repeated_word, byte_count);
}

#endif
