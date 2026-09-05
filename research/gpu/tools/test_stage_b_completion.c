#include "../../../legacy/probes/ps5-agc-phase0/stage_b_completion.h"

#include <assert.h>

int main(void)
{
    struct stage_b_completion_state state;
    struct stage_b_completion_observation observation = {1, 0, 0, 0, 0};
    assert(stage_b_completion_begin(&state, 42, 1) ==
           STAGE_B_COMPLETION_WAITING);
    assert(state.retain_all_resources && !state.cleanup_allowed);
    assert(stage_b_completion_observe(&state, &observation) ==
           STAGE_B_COMPLETION_WAITING);

    observation.fence_value = 0;
    assert(stage_b_completion_observe(&state, &observation) ==
           STAGE_B_COMPLETION_WAITING);
    assert(state.fence_zero_seen && !state.matching_videoout_event_seen);
    observation.videoout_event_observed = 1;
    observation.videoout_event_flip_arg = 42;
    assert(stage_b_completion_observe(&state, &observation) ==
           STAGE_B_COMPLETION_DONE);
    assert(state.fence_zero_seen && state.matching_videoout_event_seen);
    assert(state.cleanup_allowed && !state.retain_all_resources);

    assert(stage_b_completion_begin(&state, 7, 1) ==
           STAGE_B_COMPLETION_WAITING);
    observation = (struct stage_b_completion_observation){1, 0, 0, 1, 0};
    assert(stage_b_completion_observe(&state, &observation) ==
           STAGE_B_COMPLETION_FENCE_TIMEOUT);
    assert(state.parked && state.retain_all_resources && !state.cleanup_allowed);

    assert(stage_b_completion_begin(&state, 12, 1) ==
           STAGE_B_COMPLETION_WAITING);
    observation = (struct stage_b_completion_observation){0, 1, 13, 0, 0};
    assert(stage_b_completion_observe(&state, &observation) ==
           STAGE_B_COMPLETION_UNEXPECTED_FLIP_ARG);
    assert(state.parked && state.retain_all_resources && !state.cleanup_allowed);

    assert(stage_b_completion_begin(&state, 11, 1) ==
           STAGE_B_COMPLETION_WAITING);
    observation = (struct stage_b_completion_observation){1, 1, 11, 0, 0};
    assert(stage_b_completion_observe(&state, &observation) ==
           STAGE_B_COMPLETION_EVENT_BEFORE_FENCE);
    assert(state.parked && state.retain_all_resources && !state.cleanup_allowed);

    assert(stage_b_completion_begin(&state, 8, 1) ==
           STAGE_B_COMPLETION_WAITING);
    observation = (struct stage_b_completion_observation){0, 0, 0, 0, 1};
    assert(stage_b_completion_observe(&state, &observation) ==
           STAGE_B_COMPLETION_VIDEOOUT_TIMEOUT);
    assert(state.parked && state.retain_all_resources && !state.cleanup_allowed);

    assert(stage_b_completion_begin(&state, 9, 0) ==
           STAGE_B_COMPLETION_PRECONDITION);
    return 0;
}
