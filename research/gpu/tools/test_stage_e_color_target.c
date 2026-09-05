#include "legacy/probes/ps5-agc-phase0/stage_e_color_target.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

int main(void)
{
    static const uint32_t offsets[16] = {
        0x318, 0x31b, 0x31c, 0x31d, 0x31e, 0x31f, 0x321, 0x323,
        0x324, 0x325, 0x390, 0x398, 0x3a0, 0x3a8, 0x3b0, 0x3b8,
    };
    struct Guarded {
        uint64_t before;
        AgcRegister1202 data[16];
        uint64_t after;
    } ga = {0}, gb = {0};
    AgcRegister1202 defaults[16];
#define a ga.data
#define b gb.data
    ga.before = gb.before = UINT64_C(0xc3c3c3c3c3c3c3c3);
    ga.after = gb.after = UINT64_C(0x3c3c3c3c3c3c3c3c);
    for (uint32_t i = 0; i < 16; ++i)
        defaults[i] = (AgcRegister1202){offsets[i], UINT32_C(0xa5a5a5a5)};
    uintptr_t address = (uintptr_t)UINT64_C(0x0000005000200000);
    assert(stage_e_build_color_target(a, defaults, address, 1920, 1080) == 0);
    assert(stage_e_build_color_target(b, defaults, address, 1920, 1080) == 0);
    assert(memcmp(a, b, sizeof(a)) == 0);
    assert(ga.before == UINT64_C(0xc3c3c3c3c3c3c3c3) &&
           ga.after == UINT64_C(0x3c3c3c3c3c3c3c3c));
    assert(a[0].value == UINT32_C(0x50002000));
    assert((a[10].value & 0xffu) == 0);
    assert(a[5].value == 0 && a[6].value == 0 && a[9].value == 0);
    assert(a[14].value == (1079u | (1919u << 14u)));
    assert(stage_e_build_color_target(a, defaults, address + 0x100, 1920, 1080) == -1);
    defaults[7].offset++;
    assert(stage_e_build_color_target(a, defaults, address, 1920, 1080) == -2);
#undef a
#undef b
    return 0;
}
