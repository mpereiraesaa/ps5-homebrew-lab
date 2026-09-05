#ifndef HOMEBREW_PS5_STAGE_GPU_VISIBILITY_H
#define HOMEBREW_PS5_STAGE_GPU_VISIBILITY_H

#include <stddef.h>

/* Return non-zero only when the complete non-empty span [pointer, pointer +
 * bytes) is contained in the declared GPU-visible mapping. */
int stage_gpu_span_visible(const void *mapping, size_t mapping_bytes,
                           const void *pointer, size_t bytes);

#endif
