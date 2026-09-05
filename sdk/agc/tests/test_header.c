#include "ps5_agc.h"

#include <assert.h>

static uint32_t *fake_dma(void *writer, uint32_t a2, uint32_t dst_select,
                          uint32_t a4, uint64_t destination,
                          uint32_t src_select, uint32_t a7,
                          uint64_t source, uint32_t bytes,
                          uint32_t raw_wait, uint32_t dis_wc,
                          uint32_t cp_sync)
{
    (void)writer; (void)a2; (void)a4; (void)destination; (void)a7;
    assert(dst_select == 3 && src_select == 2);
    assert(source == 0x3f800000u && bytes == 0x870000u);
    assert(raw_wait == 0 && dis_wc == 0 && cp_sync == 1);
    return (uint32_t *)(uintptr_t)1;
}

/* Compile-time ABI checks plus the semantic constants consumed by Gears. */
int main(void)
{
    uint32_t *(*draw)(void *, uint32_t, const void *, uint64_t) = sceAgcDcbDrawIndex;
    uint32_t *(*dma)(void *, uint32_t, uint32_t, uint32_t, uint64_t,
                     uint32_t, uint32_t, uint64_t, uint32_t,
                     uint32_t, uint32_t, uint32_t) = fake_dma;
    (void)draw; (void)dma;
    assert(PS5_AGC_SH_USER_DATA_GS_0 == 0x8c);
    assert(PS5_AGC_GEARS_PARAMETER_OFFSET == 0x8d);
    assert(PS5_AGC_GEARS_DRAW_WORDS == 25);
    fake_dma(0, 0, 3, 0, 0, 2, 0, 0x3f800000u, 0x870000u, 0, 0, 1);
    return 0;
}
