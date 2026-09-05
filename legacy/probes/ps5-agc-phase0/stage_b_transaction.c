#include "stage_b_transaction.h"

#include <string.h>

int stage_b_build_and_submit(const struct stage_b_transaction_input *input,
                             struct stage_b_transaction_state *state)
{
    if (!state) return STAGE_B_TRANSACTION_PRECONDITION;
    memset(state, 0, sizeof(*state));
    uintptr_t stream_start = input && input->stream ?
        (uintptr_t)input->stream->start : 0;
    uintptr_t stream_end = input && input->stream ?
        (uintptr_t)input->stream->end : 0;
    uintptr_t fence_start = input ? (uintptr_t)input->gpu_fence : 0;
    uintptr_t fence_end = fence_start + sizeof(uint64_t);
    if (!input || !input->stream || !input->set_flip || !input->submit ||
        !input->gpu_fence || input->videoout_handle < 0 ||
        input->buffer_index < 0 || input->buffer_index >= 2 ||
        !input->surface_registered || !input->buffer_prefilled ||
        !input->videoout_event_armed ||
        (fence_start & 7u) != 0 || stream_start >= stream_end ||
        fence_end < fence_start ||
        (fence_start < stream_end && fence_end > stream_start))
        return STAGE_B_TRANSACTION_PRECONDITION;

    /* CPU owns the submission until RELEASE_MEM changes this exact value. */
    *input->gpu_fence = UINT64_C(1);
    input->stream->transaction_started = 0;
    state->builder_result = stage_b_compose_setflip_then_fence(
        input->stream, input->set_flip, input->videoout_handle,
        input->buffer_index, input->flip_mode, input->flip_arg,
        (uintptr_t)input->gpu_fence);
    state->transaction_started = input->stream->transaction_started;
    if (state->transaction_started) state->retain_all_resources = 1;
    if (state->builder_result != STAGE_B_COMPOSE_OK)
        return STAGE_B_TRANSACTION_COMPOSE_FAILED;

    state->command_dwords = (uint32_t)(input->stream->cursor -
                                       input->stream->start);
    /* The submit itself is another irreversible boundary. Mark it first. */
    state->submit_called = 1;
    state->retain_all_resources = 1;
    state->submit_result = input->submit(input->stream->start,
                                         state->command_dwords,
                                         input->submit_opaque);
    if (state->submit_result != 0)
        return STAGE_B_TRANSACTION_SUBMIT_FAILED;
    return STAGE_B_TRANSACTION_OK;
}
