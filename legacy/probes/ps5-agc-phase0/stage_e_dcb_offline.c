#include "stage_e_dcb_offline.h"

#include <string.h>

enum {
    IT_NOP = 0x10,
    R_SH_REGS_INDIRECT = 0x11,
    R_CX_REGS_INDIRECT = 0x12,
    R_UC_REGS_INDIRECT = 0x13,
};

static uint32_t packet3(uint32_t dwords, uint32_t opcode, uint32_t subop)
{
    return UINT32_C(0xc0000000) | ((dwords - 2u) << 16u) |
           (opcode << 8u) | (subop << 2u);
}

static void emit_indirect(uint32_t **cursor, uint32_t subop,
                          StageEDcbRegisterSpan span)
{
    uintptr_t address = (uintptr_t)span.registers;
    uint32_t *p = *cursor;
    p[0] = packet3(STAGE_E_DCB_INDIRECT_DWORDS, IT_NOP, subop);
    p[1] = span.count;
    p[2] = (uint32_t)address;
    p[3] = (uint32_t)(address >> 32);
    p[4] = 0;
    *cursor = p + STAGE_E_DCB_INDIRECT_DWORDS;
}

int stage_e_append_indirect(uint32_t **cursor, size_t capacity_dwords,
                            enum StageEDcbIndirectKind kind,
                            StageEDcbRegisterSpan span)
{
    if (!cursor || !*cursor || !span.registers || span.count == 0 ||
        ((uintptr_t)span.registers & 7u) ||
        capacity_dwords < STAGE_E_DCB_INDIRECT_DWORDS ||
        (kind != STAGE_E_DCB_INDIRECT_CX &&
         kind != STAGE_E_DCB_INDIRECT_UC &&
         kind != STAGE_E_DCB_INDIRECT_SH))
        return STAGE_E_DCB_PRECONDITION;
    emit_indirect(cursor, (uint32_t)kind, span);
    return STAGE_E_DCB_OK;
}

static int span_bounds(StageEDcbRegisterSpan span, uint32_t expected,
                       uintptr_t *begin, uintptr_t *end)
{
    uintptr_t address = (uintptr_t)span.registers;
    size_t bytes = (size_t)span.count * 8u;
    if (!span.registers || span.count != expected || (address & 7u) ||
        address > UINTPTR_MAX - bytes) return 0;
    *begin = address;
    *end = address + bytes;
    return 1;
}

static int disjoint(uintptr_t a0, uintptr_t a1, uintptr_t b0, uintptr_t b1)
{
    return a1 <= b0 || b1 <= a0;
}

static void emit_release_fence(uint32_t **cursor, uintptr_t address)
{
    const uint32_t release[STAGE_E_DCB_RELEASE_DWORDS] = {
        UINT32_C(0xc0064900), UINT32_C(0x06000528), UINT32_C(0x42010000),
        (uint32_t)address, (uint32_t)(address >> 32), 0, 0, 0,
    };
    memcpy(*cursor, release, sizeof(release));
    *cursor += STAGE_E_DCB_RELEASE_DWORDS;
}

int stage_e_compose_dcb_offline(uint32_t *words, size_t capacity_dwords,
                                const StageEDcbOfflineInput *input,
                                StageEDcbOfflineOutput *output)
{
    uintptr_t cx0, cx1, sh0, sh1, uc0, uc1;
    if (!words || !input || !output ||
        !span_bounds(input->cx, STAGE_E_DCB_CX_REGISTERS, &cx0, &cx1) ||
        !span_bounds(input->sh, STAGE_E_DCB_SH_REGISTERS, &sh0, &sh1) ||
        !span_bounds(input->uc, STAGE_E_DCB_UC_REGISTERS, &uc0, &uc1) ||
        !input->wait_rendering || !input->set_cx_indirect ||
        !input->set_uc_indirect || !input->set_sh_indirect ||
        !input->draw_index_auto || !input->set_flip ||
        input->videoout_handle < 0 || input->buffer_index < 0 ||
        input->flip_mode == 0 || !input->flip_arg ||
        !input->post_wait_fence_address || (input->post_wait_fence_address & 7u) ||
        !input->pre_draw_fence_address || (input->pre_draw_fence_address & 7u) ||
        !input->fence_address || (input->fence_address & 7u))
        return STAGE_E_DCB_PRECONDITION;
    if (capacity_dwords < STAGE_E_DCB_FIXED_DWORDS +
                          STAGE_E_DCB_SET_FLIP_MAX_DWORDS)
        return STAGE_E_DCB_NO_SPACE;
    uintptr_t command0 = (uintptr_t)words;
    if (capacity_dwords > (UINTPTR_MAX - command0) / sizeof(uint32_t))
        return STAGE_E_DCB_PRECONDITION;
    uintptr_t command1 = command0 + capacity_dwords * sizeof(uint32_t);
    if (!disjoint(cx0, cx1, sh0, sh1) || !disjoint(cx0, cx1, uc0, uc1) ||
        !disjoint(sh0, sh1, uc0, uc1) ||
        !disjoint(command0, command1, cx0, cx1) ||
        !disjoint(command0, command1, sh0, sh1) ||
        !disjoint(command0, command1, uc0, uc1))
        return STAGE_E_DCB_PRECONDITION;

    memset(output, 0, sizeof(*output));
    output->begin = words;
    uint32_t *cursor = words;
    if (!input->bootstrap_skip_wait) {
        const size_t reserved_after_wait =
            3u * STAGE_E_DCB_INDIRECT_DWORDS +
            STAGE_E_DCB_DRAW_MAX_DWORDS +
            STAGE_E_DCB_SET_FLIP_MAX_DWORDS + STAGE_E_DCB_RELEASE_DWORDS;
        const size_t wait_capacity = capacity_dwords - reserved_after_wait;
        uint32_t *after_wait = cursor;
        int rc = input->wait_rendering(&after_wait, (uint32_t)wait_capacity, 0,
                                       input->videoout_handle,
                                       input->buffer_index);
        if (rc != 0 || after_wait <= cursor ||
            (size_t)(after_wait - cursor) > wait_capacity)
            return STAGE_E_DCB_WAIT_ERROR;
        cursor = after_wait;
    }
    {
        stage_e_register_indirect_fn emitters[3] = {
            input->set_cx_indirect, input->set_uc_indirect,
            input->set_sh_indirect};
        StageEDcbRegisterSpan spans[3] = {input->cx, input->uc, input->sh};
        for (uint32_t index = 0; index < 3; ++index) {
            uint32_t *after = cursor;
            int rc = emitters[index](&after, STAGE_E_DCB_INDIRECT_DWORDS,
                                     spans[index].registers,
                                     spans[index].count);
            if (rc != 0 || after <= cursor ||
                after > cursor + STAGE_E_DCB_INDIRECT_DWORDS)
                return STAGE_E_DCB_INDIRECT_ERROR;
            cursor = after;
        }
    }

    {
        uint32_t *after_draw = cursor;
        int rc = input->draw_index_auto(&after_draw,
                                        STAGE_E_DCB_DRAW_MAX_DWORDS, 3,
                                        input->draw_modifier);
        if (rc != 0 || after_draw <= cursor ||
            after_draw > cursor + STAGE_E_DCB_DRAW_MAX_DWORDS)
            return STAGE_E_DCB_DRAW_ERROR;
        cursor = after_draw;
    }

    output->transaction_started = 1;
    output->set_flip_begin = cursor;
    uint32_t *after_flip = cursor;
    int rc = input->set_flip(&after_flip, STAGE_E_DCB_SET_FLIP_MAX_DWORDS, 0,
                             input->videoout_handle, input->buffer_index,
                             input->flip_mode, input->flip_arg);
    if (rc != 0) return STAGE_E_DCB_SET_FLIP_ERROR;
    uintptr_t flip0 = (uintptr_t)cursor;
    uintptr_t after = (uintptr_t)after_flip;
    uintptr_t flip_limit = flip0 + STAGE_E_DCB_SET_FLIP_MAX_DWORDS * sizeof(uint32_t);
    if ((after & 3u) || after < flip0 || after > flip_limit || after > command1 ||
        command1 - after < STAGE_E_DCB_RELEASE_DWORDS * sizeof(uint32_t))
        return STAGE_E_DCB_SET_FLIP_CURSOR_INVALID;
    output->set_flip_end = after_flip;

    cursor = after_flip;
    emit_release_fence(&cursor, input->fence_address);
    output->end = cursor;
    return STAGE_E_DCB_OK;
}
