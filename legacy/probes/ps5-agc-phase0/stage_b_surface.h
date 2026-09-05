#ifndef PS5_AGC_STAGE_B_SURFACE_H
#define PS5_AGC_STAGE_B_SURFACE_H

#include <stddef.h>
#include <stdint.h>

#define STAGE_B_BUFFER_COUNT 2u
#define STAGE_B_DIRECT_BYTES UINT64_C(0x08000000)
#define STAGE_B_BUFFER_STRIDE UINT64_C(0x04000000)
#define STAGE_B_DIRECT_ALIGNMENT UINT64_C(0x00020000)
#define STAGE_B_MEMORY_TYPE 3
#define STAGE_B_MAP_PROTECTION 0x33
#define STAGE_B_FORMAT_WORD UINT64_C(0x8000000022000000)

struct stage_b_surface_plan {
    uint32_t width;
    uint32_t height;
    uint32_t pitch_width;
    uint32_t pitch_height;
    uint64_t tiled_footprint;
    uint64_t allocation_bytes;
    uint64_t buffer_offsets[STAGE_B_BUFFER_COUNT];
    uint64_t format_word;
    uint32_t register_start_index;
    uint32_t register_count;
    uint32_t flip_mode;
    uint32_t flip_rate;
};

enum stage_b_surface_result {
    STAGE_B_SURFACE_OK = 0,
    STAGE_B_SURFACE_INVALID = -1,
};

int stage_b_make_surface_plan(uint32_t videoout_resolution,
                              struct stage_b_surface_plan *plan);

#endif
