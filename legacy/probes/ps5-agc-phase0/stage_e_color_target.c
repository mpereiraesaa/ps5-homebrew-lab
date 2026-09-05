#include "stage_e_color_target.h"

#include <string.h>

_Static_assert(sizeof(AgcRegister1202) == 8, "color register ABI");

static const uint32_t offsets[STAGE_E_COLOR_REGISTER_COUNT] = {
    0x318, 0x31b, 0x31c, 0x31d, 0x31e, 0x31f, 0x321, 0x323,
    0x324, 0x325, 0x390, 0x398, 0x3a0, 0x3a8, 0x3b0, 0x3b8,
};

int stage_e_build_color_target(
    AgcRegister1202 out[STAGE_E_COLOR_REGISTER_COUNT],
    const AgcRegister1202 defaults[STAGE_E_COLOR_REGISTER_COUNT],
    uintptr_t address, uint32_t width, uint32_t height)
{
    if (!out || !defaults || !address || (address & UINT32_C(0x1ffff)) ||
        !width || !height || width > 0x3fffu || height > 0x3fffu)
        return -1;
    for (uint32_t i = 0; i < STAGE_E_COLOR_REGISTER_COUNT; ++i)
        if (defaults[i].offset != offsets[i]) return -2;
    memcpy(out, defaults, sizeof(AgcRegister1202) * STAGE_E_COLOR_REGISTER_COUNT);

    out[0].value = (uint32_t)(address >> 8);
    out[1].value &= UINT32_C(0xfc001fff);
    out[2].value = (out[2].value &
        ~UINT32_C(0x1005df7c)) | UINT32_C(0x00008028);
    out[3].value &= ~UINT32_C(0x0001f000);
    out[4].value = (out[4].value &
        ~UINT32_C(0x0018026c)) | UINT32_C(0x00000048);
    out[5].value = 0;
    out[6].value = 0;
    out[9].value = 0;
    out[10].value = (out[10].value & UINT32_C(0xffffff00)) |
                    (uint32_t)((address >> 40) & 0xffu);
    out[11].value &= UINT32_C(0xffffff00);
    out[12].value &= UINT32_C(0xffffff00);
    out[13].value &= UINT32_C(0xffffff00);
    out[14].value = (height - 1u) | ((width - 1u) << 14u);
    out[15].value = (out[15].value &
        ~UINT32_C(0x4707dfff)) | UINT32_C(0x4506c000);
    return 0;
}
