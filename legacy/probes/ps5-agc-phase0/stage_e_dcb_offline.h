#ifndef PS5_AGC_STAGE_E_DCB_OFFLINE_H
#define PS5_AGC_STAGE_E_DCB_OFFLINE_H

#include <stddef.h>
#include <stdint.h>

#include "stage_e_pipeline_registers.h"

enum {
    STAGE_E_DCB_WAIT_DWORDS = 7,
    STAGE_E_DCB_INDIRECT_DWORDS = 5,
    STAGE_E_DCB_DRAW_MAX_DWORDS = 64,
    STAGE_E_DCB_SET_FLIP_MAX_DWORDS = 64,
    STAGE_E_DCB_RELEASE_DWORDS = 8,
    STAGE_E_DCB_FIXED_DWORDS = STAGE_E_DCB_WAIT_DWORDS +
                               3 * STAGE_E_DCB_INDIRECT_DWORDS +
                               STAGE_E_DCB_DRAW_MAX_DWORDS +
                               3 * STAGE_E_DCB_RELEASE_DWORDS,
    STAGE_E_DCB_CX_REGISTERS = STAGE_E_CX_REGISTER_COUNT,
    STAGE_E_DCB_SH_REGISTERS = STAGE_E_SH_REGISTER_COUNT,
    STAGE_E_DCB_UC_REGISTERS = STAGE_E_UC_REGISTER_COUNT,
};

typedef int (*stage_e_set_flip_fn)(uint32_t **cursor, uint32_t capacity_dwords,
                                   uint32_t driver_mode, int32_t videoout_handle,
                                   int32_t buffer_index, uint32_t flip_mode,
                                   uint64_t flip_arg);
typedef int (*stage_e_wait_rendering_fn)(uint32_t **cursor,
                                         uint32_t capacity_dwords,
                                         uint32_t driver_mode,
                                         int32_t videoout_handle,
                                         int32_t buffer_index);
typedef int (*stage_e_draw_index_auto_fn)(uint32_t **cursor,
                                          uint32_t capacity_dwords,
                                          uint32_t vertex_count,
                                          uint64_t modifier);
typedef int (*stage_e_register_indirect_fn)(uint32_t **cursor,
                                             uint32_t capacity_dwords,
                                             const void *registers,
                                             uint32_t count);

typedef struct StageEDcbRegisterSpan {
    const void *registers;
    uint32_t count;
} StageEDcbRegisterSpan;

typedef struct StageEDcbOfflineInput {
    StageEDcbRegisterSpan cx;
    StageEDcbRegisterSpan sh;
    StageEDcbRegisterSpan uc;
    uint64_t draw_modifier;
    uint32_t bootstrap_skip_wait;
    stage_e_wait_rendering_fn wait_rendering;
    stage_e_register_indirect_fn set_cx_indirect;
    stage_e_register_indirect_fn set_uc_indirect;
    stage_e_register_indirect_fn set_sh_indirect;
    stage_e_draw_index_auto_fn draw_index_auto;
    stage_e_set_flip_fn set_flip;
    int32_t videoout_handle;
    int32_t buffer_index;
    uint32_t flip_mode;
    uint64_t flip_arg;
    uintptr_t post_wait_fence_address;
    uintptr_t pre_draw_fence_address;
    uintptr_t fence_address;
} StageEDcbOfflineInput;

typedef struct StageEDcbOfflineOutput {
    uint32_t *begin;
    uint32_t *end;
    uint32_t *set_flip_begin;
    uint32_t *set_flip_end;
    uint32_t transaction_started;
} StageEDcbOfflineOutput;

enum StageEDcbOfflineResult {
    STAGE_E_DCB_OK = 0,
    STAGE_E_DCB_PRECONDITION = -1,
    STAGE_E_DCB_NO_SPACE = -2,
    STAGE_E_DCB_SET_FLIP_ERROR = -3,
    STAGE_E_DCB_SET_FLIP_CURSOR_INVALID = -4,
    STAGE_E_DCB_WAIT_ERROR = -5,
    STAGE_E_DCB_DRAW_ERROR = -6,
    STAGE_E_DCB_INDIRECT_ERROR = -7,
};

enum StageEDcbIndirectKind {
    STAGE_E_DCB_INDIRECT_SH = 0x11,
    STAGE_E_DCB_INDIRECT_CX = 0x12,
    STAGE_E_DCB_INDIRECT_UC = 0x13,
};

int stage_e_append_indirect(uint32_t **cursor, size_t capacity_dwords,
                            enum StageEDcbIndirectKind kind,
                            StageEDcbRegisterSpan span);

int stage_e_compose_dcb_offline(uint32_t *words, size_t capacity_dwords,
                                const StageEDcbOfflineInput *input,
                                StageEDcbOfflineOutput *output);

#endif
