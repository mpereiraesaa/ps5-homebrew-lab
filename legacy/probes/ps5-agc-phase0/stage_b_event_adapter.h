#ifndef PS5_AGC_STAGE_B_EVENT_ADAPTER_H
#define PS5_AGC_STAGE_B_EVENT_ADAPTER_H

#include "stage_b_completion.h"

#include <stdint.h>

struct stage_b_event_poll {
    void *equeue;
    void *event_storage;
    volatile uint64_t *gpu_fence;
    unsigned int wait_timeout_us;
    int fence_deadline_expired;
    int videoout_deadline_expired;
    struct stage_b_event_diagnostics *diagnostics;
};

struct stage_b_event_diagnostics {
    uint32_t wait_calls;
    int last_wait_rc;
    int last_event_count;
    uint32_t decode_calls;
    int last_decode_rc;
    int64_t last_flip_arg;
};

enum stage_b_event_adapter_result {
    STAGE_B_EVENT_ADAPTER_PRECONDITION = -30,
    STAGE_B_EVENT_ADAPTER_INVALID_EVENT = -31,
};

int stage_b_poll_videoout_completion(
    struct stage_b_completion_state *state,
    const struct stage_b_event_poll *poll);

#endif
