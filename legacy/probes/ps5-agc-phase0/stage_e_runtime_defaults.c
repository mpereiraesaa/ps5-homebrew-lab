#include "stage_e_runtime_defaults.h"

#include <string.h>

enum {
    STAGE_E_MRT0_DEFAULT_KEY = 0x38e92c91u,
};

static const uint32_t color_offsets[STAGE_E_COLOR_REGISTER_COUNT] = {
    0x318, 0x31b, 0x31c, 0x31d, 0x31e, 0x31f, 0x321, 0x323,
    0x324, 0x325, 0x390, 0x398, 0x3a0, 0x3a8, 0x3b0, 0x3b8,
};

int stage_e_find_runtime_color_default_index(const AgcRegisterDefaults *root,
                                             uint32_t *index_out)
{
    uint32_t match = UINT32_MAX;
    uint32_t matches = 0;
    if (!index_out || !root || !root->table_cx || !root->type_index_pairs ||
        root->table_3 || root->count != STAGE_E_FW_1202_DEFAULT_COUNT)
        return -1;

    for (uint32_t i = 0; i < root->count; ++i) {
        const AgcTypeIndexPair *record = &root->type_index_pairs[i];
        if (record->key != STAGE_E_MRT0_DEFAULT_KEY) continue;
        if (agc_type_index_bank(record) != 0u) return -2;
        match = agc_type_index_value(record);
        ++matches;
    }
    if (matches != 1u || match >= STAGE_E_FW_1202_CX_COUNT ||
        !root->table_cx[match])
        return -3;

    *index_out = match;
    return 0;
}

int stage_e_select_runtime_color_defaults(
    AgcRegister1202 out[STAGE_E_COLOR_REGISTER_COUNT],
    const AgcRegisterDefaults *root)
{
    uint32_t match = 0;
    int result;
    if (!out) return -1;
    result = stage_e_find_runtime_color_default_index(root, &match);
    if (result != 0) return result;

    for (uint32_t i = 0; i < STAGE_E_COLOR_REGISTER_COUNT; ++i)
        if (root->table_cx[match][i].offset != color_offsets[i]) return -4;
    memcpy(out, root->table_cx[match], sizeof(*out) * STAGE_E_COLOR_REGISTER_COUNT);
    return 0;
}
