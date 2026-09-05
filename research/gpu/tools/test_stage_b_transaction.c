#include "../../../legacy/probes/ps5-agc-phase0/stage_b_transaction.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static int sequence;
static int builder_rc;
static int submit_rc;

static int mock_builder(uint32_t **cursor, uint32_t capacity, uint32_t mode,
                        int32_t handle, int32_t index, uint32_t flip_mode,
                        uint64_t flip_arg)
{
    assert(++sequence == 1);
    assert(capacity == 64 && mode == 0 && handle == 7 && index == 1);
    assert(flip_mode == 1 && flip_arg == 42);
    if (builder_rc) return builder_rc;
    (*cursor)[0] = 0xc0041000;
    *cursor += 6;
    return 0;
}

static int mock_submit(const uint32_t *commands, uint32_t dwords, void *opaque)
{
    assert(++sequence == 2);
    assert(commands == opaque);
    assert(dwords == 14);
    assert(commands[6] == 0xc0064900);
    return submit_rc;
}

static struct stage_b_transaction_input make_input(
    struct stage_b_stream *stream, volatile uint64_t *fence)
{
    struct stage_b_transaction_input input = {
        .stream = stream,
        .set_flip = mock_builder,
        .submit = mock_submit,
        .submit_opaque = stream->start,
        .gpu_fence = fence,
        .videoout_handle = 7,
        .buffer_index = 1,
        .flip_mode = 1,
        .flip_arg = 42,
        .surface_registered = 1,
        .buffer_prefilled = 1,
        .videoout_event_armed = 1,
    };
    return input;
}

int main(void)
{
    uint32_t commands[80];
    volatile uint64_t fence = 99;
    struct stage_b_stream stream = {commands, commands + 80, 0, 0};
    struct stage_b_transaction_state state;
    struct stage_b_transaction_input input = make_input(&stream, &fence);

    sequence = builder_rc = submit_rc = 0;
    memset(commands, 0, sizeof(commands));
    assert(stage_b_build_and_submit(&input, &state) == STAGE_B_TRANSACTION_OK);
    assert(sequence == 2 && fence == 1);
    assert(state.transaction_started && state.submit_called);
    assert(state.retain_all_resources && state.command_dwords == 14);

    sequence = submit_rc = 0;
    builder_rc = -7;
    stream.cursor = 0;
    assert(stage_b_build_and_submit(&input, &state) ==
           STAGE_B_TRANSACTION_COMPOSE_FAILED);
    assert(sequence == 1 && state.transaction_started);
    assert(!state.submit_called && state.retain_all_resources);

    sequence = builder_rc = 0;
    submit_rc = -8;
    stream.cursor = 0;
    assert(stage_b_build_and_submit(&input, &state) ==
           STAGE_B_TRANSACTION_SUBMIT_FAILED);
    assert(sequence == 2 && state.submit_called && state.retain_all_resources);

    input.surface_registered = 0;
    sequence = builder_rc = submit_rc = 0;
    fence = 99;
    assert(stage_b_build_and_submit(&input, &state) ==
           STAGE_B_TRANSACTION_PRECONDITION);
    assert(sequence == 0 && fence == 99 && !state.transaction_started);

    input.surface_registered = 1;
    input.gpu_fence = (volatile uint64_t *)(void *)&commands[8];
    sequence = 0;
    assert(stage_b_build_and_submit(&input, &state) ==
           STAGE_B_TRANSACTION_PRECONDITION);
    assert(sequence == 0 && !state.transaction_started);
    return 0;
}
