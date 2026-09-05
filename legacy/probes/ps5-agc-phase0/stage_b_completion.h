#ifndef PS5_AGC_STAGE_B_COMPLETION_H
#define PS5_AGC_STAGE_B_COMPLETION_H

#include <stdint.h>

struct stage_b_completion_observation {
    uint64_t fence_value;
    int videoout_event_observed;
    uint64_t videoout_event_flip_arg;
    int fence_deadline_expired;
    int videoout_deadline_expired;
};

struct stage_b_completion_state {
    uint64_t expected_flip_arg;
    int transaction_submitted;
    int fence_zero_seen;
    int matching_videoout_event_seen;
    int retain_all_resources;
    int cleanup_allowed;
    int parked;
};

enum stage_b_completion_result {
    STAGE_B_COMPLETION_WAITING = 0,
    STAGE_B_COMPLETION_DONE = 1,
    STAGE_B_COMPLETION_PRECONDITION = -20,
    STAGE_B_COMPLETION_FENCE_TIMEOUT = -21,
    STAGE_B_COMPLETION_VIDEOOUT_TIMEOUT = -22,
    STAGE_B_COMPLETION_EVENT_BEFORE_FENCE = -23,
    STAGE_B_COMPLETION_UNEXPECTED_FLIP_ARG = -24,
};

int stage_b_completion_begin(struct stage_b_completion_state *state,
                             uint64_t expected_flip_arg,
                             int transaction_submitted);
int stage_b_completion_observe(
    struct stage_b_completion_state *state,
    const struct stage_b_completion_observation *observation);

#endif
