#ifndef PS5_AGC_STAGE_B_TRANSACTION_H
#define PS5_AGC_STAGE_B_TRANSACTION_H

#include "stage_b_compose.h"

#include <stddef.h>
#include <stdint.h>

typedef int (*stage_b_submit_fn)(const uint32_t *commands,
                                 uint32_t command_dwords,
                                 void *opaque);

struct stage_b_transaction_input {
    struct stage_b_stream *stream;
    stage_b_set_flip_fn set_flip;
    stage_b_submit_fn submit;
    void *submit_opaque;
    volatile uint64_t *gpu_fence;
    int32_t videoout_handle;
    int32_t buffer_index;
    uint32_t flip_mode;
    uint64_t flip_arg;
    int surface_registered;
    int buffer_prefilled;
    int videoout_event_armed;
};

struct stage_b_transaction_state {
    int transaction_started;
    int submit_called;
    int retain_all_resources;
    uint32_t command_dwords;
    int builder_result;
    int submit_result;
};

enum stage_b_transaction_result {
    STAGE_B_TRANSACTION_OK = 0,
    STAGE_B_TRANSACTION_PRECONDITION = -10,
    STAGE_B_TRANSACTION_COMPOSE_FAILED = -11,
    STAGE_B_TRANSACTION_SUBMIT_FAILED = -12,
};

int stage_b_build_and_submit(const struct stage_b_transaction_input *input,
                             struct stage_b_transaction_state *state);

#endif
