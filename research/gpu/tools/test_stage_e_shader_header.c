#include "legacy/probes/ps5-agc-phase0/stage_e_shader_header.h"
#include "legacy/probes/ps5-agc-phase0/stage_e_compiled_metadata.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static void relocate(void **field)
{
    if (*field) *field = (void *)((uintptr_t)field + (uintptr_t)*field);
}

static void test_one(uint8_t type, uint32_t bytes, uint32_t expected_lo,
                     uint32_t expected_rsrc1)
{
    StageEShaderArena arena;
    assert(stage_e_build_shader_header(&arena, type, bytes) == 0);
    assert(stage_e_validate_unrelocated_header(&arena, type, bytes) == 0);
    const unsigned lo_index = type == STAGE_E_SHADER_PIXEL ? 2u : 4u;
    const unsigned rsrc1_index = type == STAGE_E_SHADER_PIXEL ? 4u : 2u;
    assert(arena.sh[lo_index].offset == expected_lo);
    assert(arena.sh[lo_index + 1].offset == expected_lo + 1);
    assert(arena.sh[rsrc1_index].value == expected_rsrc1);
    assert(arena.specials.draw_modifier == STAGE_E_DRAW_MODIFIER);
    relocate((void **)&arena.header.user_data);
    relocate((void **)&arena.header.cx_registers);
    relocate((void **)&arena.header.sh_registers);
    relocate(&arena.header.specials);
    assert(arena.header.sh_registers == arena.sh);
    assert(arena.header.cx_registers == arena.cx);
    assert(arena.header.user_data == &arena.user_data);
    assert(arena.header.specials == &arena.specials);
    assert((uintptr_t)arena.header.sh_registers >= (uintptr_t)&arena);
    assert((uintptr_t)(arena.header.sh_registers + 6) <=
           (uintptr_t)&arena + sizeof(arena));
}

int main(void)
{
    test_one(STAGE_E_SHADER_PRE_RASTER, STAGE_E_GS_ISA_BYTES + 48u, 0x0c8,
             STAGE_E_GS_RSRC1);
    test_one(STAGE_E_SHADER_PIXEL, STAGE_E_PS_ISA_BYTES + 48u, 0x008,
             STAGE_E_PS_RSRC1);
    StageEShaderArena arena;
    memset(&arena, 0xa5, sizeof(arena));
    assert(stage_e_build_shader_header(&arena, 0, 28) == -1);
    assert(stage_e_build_shader_header(&arena, 1, 0) == -1);
    assert(stage_e_build_shader_header(&arena, 1, 44) == -1);
    return 0;
}
