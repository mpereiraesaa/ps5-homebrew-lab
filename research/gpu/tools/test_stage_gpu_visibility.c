#include <stdint.h>
#include <stdlib.h>

#include "legacy/probes/ps5-agc-phase0/stage_gpu_visibility.h"

#define CHECK(condition) do { if (!(condition)) return __LINE__; } while (0)

int main(void)
{
    const uintptr_t base = (uintptr_t)0x100000u;

    CHECK(stage_gpu_span_visible((void *)base, 0x4000,
                                 (void *)(base + 0x3e00), 22 * 8));
    CHECK(stage_gpu_span_visible((void *)base, 0x4000,
                                 (void *)base, 1));
    CHECK(stage_gpu_span_visible((void *)base, 0x4000,
                                 (void *)(base + 0x3fff), 1));
    CHECK(!stage_gpu_span_visible((void *)base, 0x4000,
                                  (void *)(base - 8), 8));
    CHECK(!stage_gpu_span_visible((void *)base, 0x4000,
                                  (void *)(base + 0x3ff8), 16));
    CHECK(!stage_gpu_span_visible((void *)base, 0x4000,
                                  (void *)(UINTPTR_MAX - 3), 8));
    CHECK(!stage_gpu_span_visible(NULL, 0x4000, (void *)base, 8));
    CHECK(!stage_gpu_span_visible((void *)base, 0x4000, NULL, 8));
    CHECK(!stage_gpu_span_visible((void *)base, 0x4000, (void *)base, 0));
    return 0;
}
