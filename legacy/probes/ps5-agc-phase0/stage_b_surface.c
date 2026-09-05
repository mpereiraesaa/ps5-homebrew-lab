#include "stage_b_surface.h"

#include <string.h>

#define TILE_WIDTH 512u
#define TILE_HEIGHT 128u
#define BYTES_PER_PIXEL 4u

static uint64_t tiled_footprint(uint32_t width, uint32_t height)
{
    uint64_t tile_pixels = (uint64_t)TILE_WIDTH * TILE_HEIGHT;
    uint64_t last_band = ((uint64_t)(height - 1) / TILE_HEIGHT) *
                         width * TILE_HEIGHT;
    uint64_t last_tile = ((uint64_t)(width - 1) / TILE_WIDTH) * tile_pixels;
    return (last_band + last_tile + tile_pixels) * BYTES_PER_PIXEL;
}

int stage_b_make_surface_plan(uint32_t videoout_resolution,
                              struct stage_b_surface_plan *plan)
{
    if (!plan) return STAGE_B_SURFACE_INVALID;
    memset(plan, 0, sizeof(*plan));
    plan->width = videoout_resolution == 2 ? 3840u : 1920u;
    plan->height = videoout_resolution == 2 ? 2160u : 1080u;
    plan->pitch_width = (plan->width + 0x3fu) & ~0x3fu;
    plan->pitch_height = (plan->height + 0x3fu) & ~0x3fu;
    plan->tiled_footprint = tiled_footprint(plan->width, plan->height);
    plan->allocation_bytes = STAGE_B_DIRECT_BYTES;
    plan->buffer_offsets[0] = 0;
    plan->buffer_offsets[1] = STAGE_B_BUFFER_STRIDE;
    plan->format_word = STAGE_B_FORMAT_WORD;
    plan->register_start_index = 0;
    plan->register_count = STAGE_B_BUFFER_COUNT;
    plan->flip_mode = 1;
    plan->flip_rate = 0;
    if (plan->tiled_footprint > STAGE_B_BUFFER_STRIDE ||
        plan->buffer_offsets[1] + plan->tiled_footprint >
            plan->allocation_bytes)
        return STAGE_B_SURFACE_INVALID;
    return STAGE_B_SURFACE_OK;
}
