#include "stage_b_compose.h"

#include <string.h>

_Static_assert(sizeof(uintptr_t) == 8, "stage B requires 64-bit GPU addresses");

int stage_b_compose_setflip_then_fence(
    struct stage_b_stream *stream,
    stage_b_set_flip_fn set_flip,
    int32_t videoout_handle,
    int32_t buffer_index,
    uint32_t flip_mode,
    uint64_t flip_arg,
    uintptr_t fence_address)
{
    uintptr_t start_address = stream ? (uintptr_t)stream->start : 0;
    uintptr_t end_address = stream ? (uintptr_t)stream->end : 0;
    size_t required_bytes =
        (STAGE_B_SET_FLIP_MAX_DWORDS + STAGE_B_RELEASE_DWORDS) * sizeof(uint32_t);
    if (!stream || !set_flip || !stream->start || !stream->end ||
        start_address > end_address || end_address - start_address < required_bytes ||
        ((end_address - start_address) % sizeof(uint32_t)) != 0 ||
        (fence_address & 7u) != 0) {
        return STAGE_B_COMPOSE_PRECONDITION;
    }

    uint32_t *cursor = stream->start;
    /* Irreversible boundary: the builder reserves VideoOut EOP state before
     * it emits the packet. Every return after this store requires retention. */
    stream->transaction_started = 1;
    int rc = set_flip(&cursor, STAGE_B_SET_FLIP_MAX_DWORDS, 0,
                      videoout_handle, buffer_index, flip_mode, flip_arg);
    if (rc != 0) return STAGE_B_COMPOSE_BUILDER_ERROR;
    uintptr_t cursor_address = (uintptr_t)cursor;
    uintptr_t builder_limit = start_address +
        STAGE_B_SET_FLIP_MAX_DWORDS * sizeof(uint32_t);
    if (builder_limit < start_address || cursor_address < start_address ||
        cursor_address > builder_limit || cursor_address > end_address ||
        (cursor_address - start_address) % sizeof(uint32_t) != 0 ||
        end_address - cursor_address < STAGE_B_RELEASE_DWORDS * sizeof(uint32_t)) {
        return STAGE_B_COMPOSE_CURSOR_INVALID;
    }

    const uint32_t release[STAGE_B_RELEASE_DWORDS] = {
        UINT32_C(0xc0064900), UINT32_C(0x06000528), UINT32_C(0x42010000),
        (uint32_t)fence_address, (uint32_t)(fence_address >> 32),
        0, 0, 0,
    };
    memcpy(cursor, release, sizeof(release));
    stream->cursor = cursor + STAGE_B_RELEASE_DWORDS;
    return STAGE_B_COMPOSE_OK;
}
