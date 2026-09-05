#include "../../../legacy/probes/ps5-agc-phase0/stage_b_event_adapter.h"

#include <assert.h>
#include <stdint.h>

static int mock_wait_rc;
static int mock_out;
static int mock_decode_rc;
static int64_t mock_flip_arg;
static int wait_calls;
static int decode_calls;

int sceKernelWaitEqueue(void *queue, void *event, int count, int *out,
                        unsigned int *timeout_us)
{
    assert(queue && event && count == 1 && out && timeout_us);
    ++wait_calls;
    *out = mock_out;
    return mock_wait_rc;
}

int sceVideoOutGetEventData(const void *event, int64_t *flip_arg)
{
    assert(event && flip_arg);
    ++decode_calls;
    *flip_arg = mock_flip_arg;
    return mock_decode_rc;
}

static void reset_mocks(void)
{
    mock_wait_rc = mock_out = mock_decode_rc = 0;
    mock_flip_arg = 0;
    wait_calls = decode_calls = 0;
}

int main(void)
{
    uint64_t fence = 1;
    uint8_t queue, event[64];
    struct stage_b_completion_state state;
    struct stage_b_event_diagnostics diagnostics = {0};
    struct stage_b_event_poll poll = {
        .equeue = &queue,
        .event_storage = event,
        .gpu_fence = &fence,
        .wait_timeout_us = 1000,
        .diagnostics = &diagnostics,
    };
    assert(stage_b_completion_begin(&state, 42, 1) == 0);

    reset_mocks();
    mock_wait_rc = -1;
    assert(stage_b_poll_videoout_completion(&state, &poll) ==
           STAGE_B_COMPLETION_WAITING);
    assert(wait_calls == 1 && decode_calls == 0 && state.retain_all_resources);
    assert(diagnostics.wait_calls == 1 && diagnostics.last_wait_rc == -1 &&
           diagnostics.last_event_count == 0 && diagnostics.decode_calls == 0);

    reset_mocks();
    fence = 0;
    assert(stage_b_poll_videoout_completion(&state, &poll) ==
           STAGE_B_COMPLETION_WAITING);
    reset_mocks();
    mock_out = 1;
    mock_flip_arg = 42;
    assert(stage_b_poll_videoout_completion(&state, &poll) ==
           STAGE_B_COMPLETION_DONE);
    assert(state.cleanup_allowed && !state.retain_all_resources);
    assert(diagnostics.decode_calls == 1 && diagnostics.last_decode_rc == 0 &&
           diagnostics.last_flip_arg == 42);

    fence = 1;
    assert(stage_b_completion_begin(&state, 8, 1) == 0);
    reset_mocks();
    mock_out = 1;
    mock_flip_arg = 8;
    assert(stage_b_poll_videoout_completion(&state, &poll) ==
           STAGE_B_COMPLETION_EVENT_BEFORE_FENCE);
    assert(state.parked && state.retain_all_resources);

    fence = 0;
    assert(stage_b_completion_begin(&state, 12, 1) == 0);
    reset_mocks();
    mock_out = 1;
    mock_flip_arg = 13;
    assert(stage_b_poll_videoout_completion(&state, &poll) ==
           STAGE_B_COMPLETION_UNEXPECTED_FLIP_ARG);
    assert(state.parked && state.retain_all_resources);

    assert(stage_b_completion_begin(&state, 9, 1) == 0);
    reset_mocks();
    mock_out = 1;
    mock_decode_rc = -1;
    assert(stage_b_poll_videoout_completion(&state, &poll) ==
           STAGE_B_EVENT_ADAPTER_INVALID_EVENT);
    assert(state.parked && state.retain_all_resources);

    assert(stage_b_completion_begin(&state, 10, 1) == 0);
    reset_mocks();
    mock_wait_rc = -1;
    mock_out = 1;
    assert(stage_b_poll_videoout_completion(&state, &poll) ==
           STAGE_B_EVENT_ADAPTER_INVALID_EVENT);
    assert(state.parked && state.retain_all_resources);
    return 0;
}
