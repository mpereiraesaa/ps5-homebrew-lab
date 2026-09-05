#ifndef PS5_AGC_STAGE_B_COMPOSE_H
#define PS5_AGC_STAGE_B_COMPOSE_H

#include <stddef.h>
#include <stdint.h>

#define STAGE_B_SET_FLIP_MAX_DWORDS 64u
#define STAGE_B_RELEASE_DWORDS 8u

typedef int (*stage_b_set_flip_fn)(uint32_t **cursor, uint32_t capacity_dwords,
                                   uint32_t driver_mode, int32_t videoout_handle,
                                   int32_t buffer_index, uint32_t flip_mode,
                                   uint64_t flip_arg);

struct stage_b_stream {
    uint32_t *start;
    uint32_t *end;
    uint32_t *cursor;
    int transaction_started;
};

enum stage_b_compose_result {
    STAGE_B_COMPOSE_OK = 0,
    STAGE_B_COMPOSE_PRECONDITION = -1,
    STAGE_B_COMPOSE_BUILDER_ERROR = -2,
    STAGE_B_COMPOSE_CURSOR_INVALID = -3,
};

int stage_b_compose_setflip_then_fence(
    struct stage_b_stream *stream,
    stage_b_set_flip_fn set_flip,
    int32_t videoout_handle,
    int32_t buffer_index,
    uint32_t flip_mode,
    uint64_t flip_arg,
    uintptr_t fence_address);

#endif
