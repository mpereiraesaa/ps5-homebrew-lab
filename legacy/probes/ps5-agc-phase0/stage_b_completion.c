#include "stage_b_completion.h"

#include <string.h>

int stage_b_completion_begin(struct stage_b_completion_state *state,
                             uint64_t expected_flip_arg,
                             int transaction_submitted)
{
    if (!state || !transaction_submitted)
        return STAGE_B_COMPLETION_PRECONDITION;
    memset(state, 0, sizeof(*state));
    state->expected_flip_arg = expected_flip_arg;
    state->transaction_submitted = 1;
    state->retain_all_resources = 1;
    return STAGE_B_COMPLETION_WAITING;
}

int stage_b_completion_observe(
    struct stage_b_completion_state *state,
    const struct stage_b_completion_observation *observation)
{
    if (!state || !observation || !state->transaction_submitted ||
        state->cleanup_allowed || state->parked)
        return STAGE_B_COMPLETION_PRECONDITION;

    if (observation->videoout_event_observed &&
        observation->fence_value != 0) {
        state->parked = 1;
        state->retain_all_resources = 1;
        return STAGE_B_COMPLETION_EVENT_BEFORE_FENCE;
    }
    if (observation->videoout_event_observed &&
        observation->videoout_event_flip_arg != state->expected_flip_arg) {
        state->parked = 1;
        state->retain_all_resources = 1;
        return STAGE_B_COMPLETION_UNEXPECTED_FLIP_ARG;
    }
    if (observation->fence_value == 0)
        state->fence_zero_seen = 1;
    if (observation->videoout_event_observed)
        state->matching_videoout_event_seen = 1;

    if (state->fence_zero_seen && state->matching_videoout_event_seen) {
        state->cleanup_allowed = 1;
        state->retain_all_resources = 0;
        return STAGE_B_COMPLETION_DONE;
    }
    if (!state->fence_zero_seen && observation->fence_deadline_expired) {
        state->parked = 1;
        return STAGE_B_COMPLETION_FENCE_TIMEOUT;
    }
    if (state->fence_zero_seen && !state->matching_videoout_event_seen &&
        observation->videoout_deadline_expired) {
        state->parked = 1;
        return STAGE_B_COMPLETION_VIDEOOUT_TIMEOUT;
    }
    return STAGE_B_COMPLETION_WAITING;
}
