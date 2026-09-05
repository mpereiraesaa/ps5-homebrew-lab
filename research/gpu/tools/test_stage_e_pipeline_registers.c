#include "legacy/probes/ps5-agc-phase0/stage_e_pipeline_registers.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static uint64_t fnv1a64(const void *data, size_t size)
{
    const uint8_t *bytes = (const uint8_t *)data;
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < size; ++i) {
        hash ^= bytes[i];
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}

int main(void)
{
    static const uint32_t offsets[16] = {
        0x318, 0x31b, 0x31c, 0x31d, 0x31e, 0x31f, 0x321, 0x323,
        0x324, 0x325, 0x390, 0x398, 0x3a0, 0x3a8, 0x3b0, 0x3b8,
    };
    AgcRegister1202 rt[16], pre[6] = {
        {0x80, 0}, {0x80, 0}, {0x8a, 0x002c0000},
        {0x8b, 0}, {0xc8, 1}, {0xc9, 2},
    };
    AgcRegister1202 pixel[6] = {
        {6, 0}, {6, 0}, {8, 3}, {9, 4},
        {0xa, 0x002c0000}, {0xb, 0},
    };
    AgcRegister1202 pre_cx[STAGE_E_PRE_RASTER_CX_REGISTER_COUNT];
    AgcRegister1202 pixel_cx[STAGE_E_PIXEL_CX_REGISTER_COUNT];
    AgcLinkedCx1202 cx;
    AgcLinkedUc1202 uc;
    struct Guarded {
        uint64_t before;
        StageEPipelineRegisters data;
        uint64_t after;
    } ga = {0}, gb = {0};
#define a ga.data
#define b gb.data
    ga.before = gb.before = UINT64_C(0xc3c3c3c3c3c3c3c3);
    ga.after = gb.after = UINT64_C(0x3c3c3c3c3c3c3c3c);
    memset(&cx, 0x12, sizeof(cx));
    memset(&uc, 0x34, sizeof(uc));
    for (uint32_t i = 0; i < STAGE_E_PRE_RASTER_CX_REGISTER_COUNT; ++i)
        pre_cx[i] = (AgcRegister1202){0x200u + i, 0x5000u + i};
    for (uint32_t i = 0; i < STAGE_E_PIXEL_CX_REGISTER_COUNT; ++i)
        pixel_cx[i] = (AgcRegister1202){0x300u + i, 0x6000u + i};
    for (uint32_t i = 0; i < 16; ++i) rt[i] = (AgcRegister1202){offsets[i], i};
    assert(stage_e_build_pipeline_registers(&a, rt, &cx, &uc, pre_cx, pixel_cx,
                                             pre, pixel,
                                             1920, 1080) == 0);
    assert(stage_e_build_pipeline_registers(&b, rt, &cx, &uc, pre_cx, pixel_cx,
                                             pre, pixel,
                                             1920, 1080) == 0);
    assert(memcmp(&a, &b, sizeof(a)) == 0);
    assert(fnv1a64(&a, sizeof(a)) == UINT64_C(0x46d786bedc9961b3));
    assert(ga.before == UINT64_C(0xc3c3c3c3c3c3c3c3) &&
           ga.after == UINT64_C(0x3c3c3c3c3c3c3c3c));
    assert(a.cx[0].offset == 0x318 && a.cx[15].offset == 0x3b8);
    assert(a.cx[16].offset == 0x10f && a.cx[29].offset == 0x091);
    assert(a.cx[30].offset == 0x08e);
    assert(memcmp(&a.cx[31], &cx, sizeof(cx)) == 0);
    assert(memcmp(&a.cx[65], pre_cx, sizeof(pre_cx)) == 0);
    assert(memcmp(&a.cx[75], pixel_cx, sizeof(pixel_cx)) == 0);
    assert(memcmp(a.sh, pre, sizeof(pre)) == 0);
    assert(memcmp(a.sh + 6, pixel, sizeof(pixel)) == 0);
    assert(memcmp(a.uc, &uc, sizeof(uc)) == 0);
    rt[3].offset++;
    assert(stage_e_build_pipeline_registers(&a, rt, &cx, &uc, pre_cx, pixel_cx,
                                             pre, pixel,
                                             1920, 1080) == -2);
#undef a
#undef b
    return 0;
}
