#include "legacy/probes/ps5-agc-phase0/stage_e_runtime_defaults.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

int main(void)
{
    static const uint32_t offsets[STAGE_E_COLOR_REGISTER_COUNT] = {
        0x318, 0x31b, 0x31c, 0x31d, 0x31e, 0x31f, 0x321, 0x323,
        0x324, 0x325, 0x390, 0x398, 0x3a0, 0x3a8, 0x3b0, 0x3b8,
    };
    AgcRegisterPair block[STAGE_E_COLOR_REGISTER_COUNT];
    AgcRegisterPair *cx[STAGE_E_FW_1202_CX_COUNT] = {0};
    AgcTypeIndexPair types[STAGE_E_FW_1202_DEFAULT_COUNT] = {0};
    struct Guarded {
        uint64_t before;
        AgcRegister1202 data[STAGE_E_COLOR_REGISTER_COUNT];
        uint64_t after;
    } result = {0};
    AgcRegisterDefaults root = {0};

    for (uint32_t i = 0; i < STAGE_E_COLOR_REGISTER_COUNT; ++i) {
        block[i].offset = offsets[i];
        block[i].value = UINT32_C(0x12020000) | i;
    }
    cx[72] = block;
    types[31].key = UINT32_C(0x38e92c91);
    types[31].encoded_index = 72u << 2;
    root.table_cx = cx;
    root.type_index_pairs = types;
    root.count = STAGE_E_FW_1202_DEFAULT_COUNT;
    result.before = UINT64_C(0xc3c3c3c3c3c3c3c3);
    result.after = UINT64_C(0x3c3c3c3c3c3c3c3c);

    {
        uint32_t index = UINT32_MAX;
        assert(stage_e_find_runtime_color_default_index(&root, &index) == 0);
        assert(index == 72);
    }
    assert(stage_e_select_runtime_color_defaults(result.data, &root) == 0);
    assert(memcmp(result.data, block, sizeof(block)) == 0);
    assert(result.before == UINT64_C(0xc3c3c3c3c3c3c3c3));
    assert(result.after == UINT64_C(0x3c3c3c3c3c3c3c3c));

    root.count--;
    assert(stage_e_select_runtime_color_defaults(result.data, &root) == -1);
    root.count++;
    types[31].encoded_index |= 1u;
    assert(stage_e_select_runtime_color_defaults(result.data, &root) == -2);
    cx[71] = block;
    types[31].encoded_index = 71u << 2;
    assert(stage_e_select_runtime_color_defaults(result.data, &root) == 0);
    cx[71] = 0;
    assert(stage_e_select_runtime_color_defaults(result.data, &root) == -3);
    types[31].encoded_index = 72u << 2;
    types[32] = types[31];
    assert(stage_e_select_runtime_color_defaults(result.data, &root) == -3);
    types[32] = (AgcTypeIndexPair){0, 0};
    block[15].offset++;
    assert(stage_e_select_runtime_color_defaults(result.data, &root) == -4);
    return 0;
}
