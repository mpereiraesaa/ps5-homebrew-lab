#include "stage_b_event_adapter.h"

#include <stddef.h>

int sceKernelWaitEqueue(void *queue, void *event, int count, int *out,
                        unsigned int *timeout_us);
int sceVideoOutGetEventData(const void *event, int64_t *flip_arg);

int stage_b_poll_videoout_completion(
    struct stage_b_completion_state *state,
    const struct stage_b_event_poll *poll)
{
    if (!state || !poll || !poll->equeue || !poll->event_storage ||
        !poll->gpu_fence || !state->transaction_submitted ||
        state->cleanup_allowed || state->parked)
        return STAGE_B_EVENT_ADAPTER_PRECONDITION;

    struct stage_b_completion_observation observation = {
        .fence_value = *poll->gpu_fence,
        .videoout_event_observed = 0,
        .videoout_event_flip_arg = 0,
        .fence_deadline_expired = poll->fence_deadline_expired,
        .videoout_deadline_expired = poll->videoout_deadline_expired,
    };
    unsigned int timeout = poll->wait_timeout_us;
    int out = 0;
    int wait_rc = sceKernelWaitEqueue(poll->equeue, poll->event_storage,
                                      1, &out, &timeout);
    if (poll->diagnostics) {
        ++poll->diagnostics->wait_calls;
        poll->diagnostics->last_wait_rc = wait_rc;
        poll->diagnostics->last_event_count = out;
    }
    if (out < 0 || out > 1 || (wait_rc != 0 && out != 0)) {
        state->parked = 1;
        state->retain_all_resources = 1;
        return STAGE_B_EVENT_ADAPTER_INVALID_EVENT;
    }
    if (wait_rc == 0 && out == 1) {
        int64_t flip_arg = 0;
        int decode_rc = sceVideoOutGetEventData(poll->event_storage, &flip_arg);
        if (poll->diagnostics) {
            ++poll->diagnostics->decode_calls;
            poll->diagnostics->last_decode_rc = decode_rc;
            poll->diagnostics->last_flip_arg = flip_arg;
        }
        if (decode_rc != 0) {
            state->parked = 1;
            state->retain_all_resources = 1;
            return STAGE_B_EVENT_ADAPTER_INVALID_EVENT;
        }
        observation.videoout_event_observed = 1;
        observation.videoout_event_flip_arg = (uint64_t)flip_arg;
    }
    /* A nonzero wait result with no event is treated as no observation until
     * the caller's absolute deadline expires; no errno value is guessed. */
    return stage_b_completion_observe(state, &observation);
}
