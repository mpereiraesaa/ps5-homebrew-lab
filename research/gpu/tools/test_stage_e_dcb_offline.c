#include "legacy/probes/ps5-agc-phase0/stage_e_dcb_offline.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static int mock_flip(uint32_t **cursor, uint32_t capacity, uint32_t driver_mode,
                     int32_t handle, int32_t index, uint32_t mode, uint64_t arg)
{
    assert(capacity == 64 && driver_mode == 0 && handle == 7 && index == 1);
    assert(mode == 1 && arg == UINT64_C(0x1234));
    (*cursor)[0] = UINT32_C(0xc0021000);
    (*cursor)[1] = 7;
    (*cursor)[2] = 1;
    (*cursor)[3] = 0x1234;
    *cursor += 4;
    return 0;
}

static int mock_wait(uint32_t **cursor, uint32_t capacity, uint32_t driver_mode,
                     int32_t handle, int32_t index)
{
    assert(capacity == 105 && driver_mode == 0 && handle == 7 && index == 1);
    (*cursor)[0] = UINT32_C(0xc0053c00);
    memset(*cursor + 1, 0, 6 * sizeof(uint32_t));
    *cursor += 7;
    return 0;
}

static int mock_draw(uint32_t **cursor, uint32_t capacity, uint32_t count,
                     uint64_t modifier)
{
    assert(capacity == 64 && count == 3);
    assert(modifier == UINT64_C(0x8877665544332211));
    (*cursor)[0] = UINT32_C(0xc0051010);
    (*cursor)[1] = count;
    (*cursor)[2] = (uint32_t)modifier;
    (*cursor)[3] = (uint32_t)(modifier >> 32);
    (*cursor)[4] = (*cursor)[5] = (*cursor)[6] = 0;
    *cursor += 7;
    return 0;
}

static int mock_indirect(uint32_t **cursor, uint32_t capacity,
                         const void *registers, uint32_t count)
{
    assert(capacity == STAGE_E_DCB_INDIRECT_DWORDS);
    uintptr_t address = (uintptr_t)registers;
    (*cursor)[0] = UINT32_C(0xc0031048);
    (*cursor)[1] = count;
    (*cursor)[2] = (uint32_t)address;
    (*cursor)[3] = (uint32_t)(address >> 32);
    (*cursor)[4] = 0;
    *cursor += 5;
    return 0;
}

static StageEDcbOfflineInput good(void)
{
    StageEDcbOfflineInput input = {
        {(const void *)(uintptr_t)UINT64_C(0x5000002000), 84},
        {(const void *)(uintptr_t)UINT64_C(0x5000003000),
         STAGE_E_SH_REGISTER_COUNT},
        {(const void *)(uintptr_t)UINT64_C(0x5000004000), 3},
        UINT64_C(0x8877665544332211),
        0, mock_wait, mock_indirect, mock_indirect, mock_indirect,
        mock_draw, mock_flip, 7, 1, 1, UINT64_C(0x1234),
        UINT64_C(0x5000001200), UINT64_C(0x5000001080),
        UINT64_C(0x5000001100),
    };
    return input;
}

static uint64_t fnv1a64(const uint32_t *words, size_t count)
{
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < count; ++i) {
        uint32_t value = words[i];
        for (unsigned byte = 0; byte < 4; ++byte) {
            hash ^= (uint8_t)value;
            hash *= UINT64_C(1099511628211);
            value >>= 8;
        }
    }
    return hash;
}

int main(void)
{
    uint32_t guarded[2 + 256 + 2];
    for (size_t i = 0; i < sizeof(guarded) / sizeof(guarded[0]); ++i)
        guarded[i] = UINT32_C(0xa5a5a5a5);
    StageEDcbOfflineInput input = good();
    StageEDcbOfflineOutput out;
    {
        uint32_t prefix[5] = {0};
        uint32_t *cursor = prefix;
        assert(stage_e_append_indirect(&cursor, 5, STAGE_E_DCB_INDIRECT_CX,
                                       input.cx) == STAGE_E_DCB_OK);
        assert(cursor == prefix + 5);
        assert(prefix[1] == STAGE_E_CX_REGISTER_COUNT);
        assert(prefix[2] == UINT32_C(0x00002000));
        assert(prefix[3] == UINT32_C(0x00000050));
    }
    assert(stage_e_compose_dcb_offline(guarded + 2, 256, &input, &out) == 0);
    assert(out.begin == guarded + 2 && out.transaction_started == 1);
    assert(out.set_flip_begin == guarded + 2 + 29);
    assert(out.set_flip_end == out.set_flip_begin + 4);
    assert(out.end == out.set_flip_end + 8);
    assert(guarded[0] == UINT32_C(0xa5a5a5a5) && guarded[1] == UINT32_C(0xa5a5a5a5));
    assert(guarded[258] == UINT32_C(0xa5a5a5a5) && guarded[259] == UINT32_C(0xa5a5a5a5));
    assert(out.begin[0] == UINT32_C(0xc0053c00));
    assert(out.begin[8] == STAGE_E_CX_REGISTER_COUNT &&
           out.begin[13] == STAGE_E_UC_REGISTER_COUNT &&
           out.begin[18] == STAGE_E_SH_REGISTER_COUNT);
    assert(out.begin[23] == 3);
    assert(out.end[-8] == UINT32_C(0xc0064900));
    assert(out.end[-5] == UINT32_C(0x00001100));
    assert(out.end[-4] == UINT32_C(0x00000050));
    assert(fnv1a64(out.begin, (size_t)(out.end - out.begin)) != 0);

    input.fence_address++;
    assert(stage_e_compose_dcb_offline(guarded + 2, 256, &input, &out) ==
           STAGE_E_DCB_PRECONDITION);
    input = good();
    assert(stage_e_compose_dcb_offline(guarded + 2,
           STAGE_E_DCB_FIXED_DWORDS + 63, &input, &out) == STAGE_E_DCB_NO_SPACE);
    input = good();
    input.cx.count = 64;
    assert(stage_e_compose_dcb_offline(guarded + 2, 256, &input, &out) ==
           STAGE_E_DCB_PRECONDITION);
    input = good();
    input.sh.count = 4;
    assert(stage_e_compose_dcb_offline(guarded + 2, 256, &input, &out) ==
           STAGE_E_DCB_PRECONDITION);
    input = good();
    input.cx.registers = guarded + 2;
    assert(stage_e_compose_dcb_offline(guarded + 2, 256, &input, &out) ==
           STAGE_E_DCB_PRECONDITION);
    return 0;
}
