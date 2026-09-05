#include <assert.h>
#include <stdint.h>

#include "legacy/probes/ps5-agc-phase0/stage_g_depth_state.h"

int main(void)
{
    AgcRegister1202 regs[STAGE_G_DEPTH_REGISTER_COUNT];
    const uintptr_t address = UINT64_C(0x0000123456000000);
    assert(stage_g_build_d32_no_htile(regs, address, 1920, 1080) == 0);
    assert(STAGE_G_DSV_REGISTER_COUNT == 21);
    assert(STAGE_G_DEPTH_REGISTER_COUNT == 22);
    assert(regs[0].offset == 0x000 && regs[0].value == 0x60);
    assert(regs[5].offset == 0x007 && regs[5].value == 0x0437077f);
    assert(regs[6].offset == 0x011 && regs[6].value == 0x20000180);
    assert(regs[7].value == (uint32_t)(address >> 8));
    assert(regs[8].value == 0 && regs[10].value == 0);
    assert(regs[12].offset == 0x2de && regs[12].value == 0x1e9);
    assert(regs[14].value == ((address >> 40) & 0xff));
    assert(regs[19].offset == 0x003 && regs[19].value == 0x2a);
    assert(regs[20].offset == 0x010 && regs[20].value == 0x183);
    assert(regs[21].offset == 0x200 && regs[21].value == 0xb6);
    assert(stage_g_build_d32_no_htile(regs, address + 1, 1920, 1080) == -1);
    assert(stage_g_build_d32_no_htile(regs, address, 0, 1080) == -1);
    return 0;
}
