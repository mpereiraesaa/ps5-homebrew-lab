#include "../../../legacy/probes/ps5-agc-phase0/stage_b_compose.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

enum mock_mode { MOCK_OK, MOCK_ERROR, MOCK_OVERFLOW, MOCK_WILD };
static enum mock_mode mode;

static int mock_set_flip(uint32_t **cursor, uint32_t capacity, uint32_t driver_mode,
                         int32_t handle, int32_t index, uint32_t flip_mode,
                         uint64_t flip_arg)
{
    assert(capacity == 64);
    assert(driver_mode == 0);
    assert(handle == 7 && index == 0 && flip_mode == 1 && flip_arg == 9);
    if (mode == MOCK_ERROR) return -99;
    if (mode == MOCK_OVERFLOW) { *cursor += 65; return 0; }
    if (mode == MOCK_WILD) { *cursor = (uint32_t *)(uintptr_t)1; return 0; }
    const uint32_t fake_flip[6] = {0xc0041000, 7, 0, 1, 9, 0};
    memcpy(*cursor, fake_flip, sizeof(fake_flip));
    *cursor += 6;
    return 0;
}

int main(void)
{
    uint32_t words[80];
    struct stage_b_stream stream;

    memset(words, 0xcc, sizeof(words));
    stream = (struct stage_b_stream){words, words + 71, NULL, 0};
    assert(stage_b_compose_setflip_then_fence(&stream, mock_set_flip, 7, 0, 1,
                                               9, UINT64_C(0x1000)) ==
           STAGE_B_COMPOSE_PRECONDITION);
    assert(stream.transaction_started == 0);

    stream = (struct stage_b_stream){words, words + 80, NULL, 0};
    mode = MOCK_ERROR;
    assert(stage_b_compose_setflip_then_fence(&stream, mock_set_flip, 7, 0, 1,
                                               9, UINT64_C(0x1000)) ==
           STAGE_B_COMPOSE_BUILDER_ERROR);
    assert(stream.transaction_started == 1);

    stream = (struct stage_b_stream){words, words + 80, NULL, 0};
    mode = MOCK_WILD;
    assert(stage_b_compose_setflip_then_fence(&stream, mock_set_flip, 7, 0, 1,
                                               9, UINT64_C(0x1000)) ==
           STAGE_B_COMPOSE_CURSOR_INVALID);
    assert(stream.transaction_started == 1);

    stream = (struct stage_b_stream){words, words + 80, NULL, 0};
    mode = MOCK_OVERFLOW;
    assert(stage_b_compose_setflip_then_fence(&stream, mock_set_flip, 7, 0, 1,
                                               9, UINT64_C(0x1000)) ==
           STAGE_B_COMPOSE_CURSOR_INVALID);
    assert(stream.transaction_started == 1);

    memset(words, 0, sizeof(words));
    stream = (struct stage_b_stream){words, words + 80, NULL, 0};
    mode = MOCK_OK;
    assert(stage_b_compose_setflip_then_fence(
               &stream, mock_set_flip, 7, 0, 1, 9,
               UINT64_C(0x1122334455667800)) == STAGE_B_COMPOSE_OK);
    assert(stream.transaction_started == 1);
    assert(stream.cursor == words + 14);
    const uint32_t expected[8] = {
        0xc0064900, 0x06000528, 0x42010000, 0x55667800,
        0x11223344, 0, 0, 0,
    };
    assert(memcmp(words + 6, expected, sizeof(expected)) == 0);
    return 0;
}
