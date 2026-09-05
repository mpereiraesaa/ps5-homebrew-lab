#include "../../../legacy/probes/ps5-agc-phase0/stage_b_surface.h"

#include <assert.h>

int main(void)
{
    struct stage_b_surface_plan plan;
    assert(stage_b_make_surface_plan(2, &plan) == STAGE_B_SURFACE_OK);
    assert(plan.width == 3840 && plan.height == 2160);
    assert(plan.pitch_width == 3840 && plan.pitch_height == 2176);
    assert(plan.tiled_footprint == UINT64_C(0x02000000));
    assert(plan.buffer_offsets[0] == 0);
    assert(plan.buffer_offsets[1] == UINT64_C(0x04000000));
    assert(plan.buffer_offsets[1] + plan.tiled_footprint <= plan.allocation_bytes);
    assert(plan.format_word == STAGE_B_FORMAT_WORD);
    assert(plan.register_start_index == 0 && plan.register_count == 2);
    assert(plan.flip_mode == 1 && plan.flip_rate == 0);

    assert(stage_b_make_surface_plan(0, &plan) == STAGE_B_SURFACE_OK);
    assert(plan.width == 1920 && plan.height == 1080);
    assert(plan.pitch_width == 1920 && plan.pitch_height == 1088);
    assert(plan.tiled_footprint == UINT64_C(0x00880000));
    assert(stage_b_make_surface_plan(2, 0) == STAGE_B_SURFACE_INVALID);
    return 0;
}
