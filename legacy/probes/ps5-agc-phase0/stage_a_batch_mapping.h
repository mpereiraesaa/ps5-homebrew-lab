#ifndef STAGE_A_BATCH_MAPPING_H
#define STAGE_A_BATCH_MAPPING_H

#include <stddef.h>
#include <stdint.h>

#define STAGE_A_BATCH_REGION_SIZE ((size_t)0x20000)
#define STAGE_A_BATCH_ALIGNMENT ((size_t)0x10000)
#define STAGE_A_BATCH_MEMORY_TYPE 0x0c
#define STAGE_A_BATCH_PROTECTION 0x0cf2

struct stage_a_batch_entry {
    void *virtual_address;
    int64_t physical_offset;
    size_t length;
    uint16_t protection;
    uint16_t reserved;
    uint32_t operation;
};

struct stage_a_batch_api {
    int (*reserve)(void **address, size_t length, int flags, size_t alignment);
    int (*allocate)(size_t length, size_t alignment, int memory_type,
                    int64_t *physical_offset);
    int (*batch_map)(struct stage_a_batch_entry *entries, int count,
                     int *processed);
    int (*release_va)(void *address, size_t length);
    int (*release_physical)(int64_t physical_offset, size_t length);
};

enum stage_a_batch_state {
    STAGE_A_BATCH_CLEAN = 0,
    STAGE_A_BATCH_RESERVED,
    STAGE_A_BATCH_ALLOCATED,
    STAGE_A_BATCH_MAPPED,
    STAGE_A_BATCH_RETAIN_UNKNOWN,
};

struct stage_a_batch_mapping {
    enum stage_a_batch_state state;
    void *virtual_address;
    int64_t physical_offset;
};

int stage_a_batch_open(struct stage_a_batch_mapping *mapping,
                       const struct stage_a_batch_api *api);
int stage_a_batch_close(struct stage_a_batch_mapping *mapping,
                        const struct stage_a_batch_api *api);

#endif
