/* Static Stage-A mapping experiment only: no AGC load, queue, or submit. */
#include "stage_a_batch_mapping.h"

#include <string.h>

_Static_assert(sizeof(struct stage_a_batch_entry) == 0x20,
               "BatchMap entry ABI size");
_Static_assert(offsetof(struct stage_a_batch_entry, protection) == 0x18,
               "BatchMap protection ABI offset");
_Static_assert(offsetof(struct stage_a_batch_entry, operation) == 0x1c,
               "BatchMap operation ABI offset");

static int valid_api(const struct stage_a_batch_api *api)
{
    return api && api->reserve && api->allocate && api->batch_map &&
           api->release_va && api->release_physical;
}

int stage_a_batch_open(struct stage_a_batch_mapping *mapping,
                       const struct stage_a_batch_api *api)
{
    struct stage_a_batch_entry entry;
    int processed = -1;
    if (!mapping || !valid_api(api) || mapping->state != STAGE_A_BATCH_CLEAN)
        return -1;
    memset(&entry, 0, sizeof(entry));
    if (api->reserve(&mapping->virtual_address, STAGE_A_BATCH_REGION_SIZE, 0,
                     STAGE_A_BATCH_ALIGNMENT) || !mapping->virtual_address)
        return -2;
    mapping->state = STAGE_A_BATCH_RESERVED;
    if (api->allocate(STAGE_A_BATCH_REGION_SIZE, STAGE_A_BATCH_ALIGNMENT,
                      STAGE_A_BATCH_MEMORY_TYPE, &mapping->physical_offset))
        return -3;
    mapping->state = STAGE_A_BATCH_ALLOCATED;
    entry.virtual_address = mapping->virtual_address;
    entry.physical_offset = mapping->physical_offset;
    entry.length = STAGE_A_BATCH_REGION_SIZE;
    entry.protection = STAGE_A_BATCH_PROTECTION;
    entry.operation = 0;
    if (api->batch_map(&entry, 1, &processed) || processed != 1) {
        if (processed != 0)
            mapping->state = STAGE_A_BATCH_RETAIN_UNKNOWN;
        return -4;
    }
    mapping->state = STAGE_A_BATCH_MAPPED;
    return 0;
}

int stage_a_batch_close(struct stage_a_batch_mapping *mapping,
                        const struct stage_a_batch_api *api)
{
    struct stage_a_batch_entry entry;
    int processed = -1;
    if (!mapping || !valid_api(api) ||
        mapping->state == STAGE_A_BATCH_RETAIN_UNKNOWN)
        return -1;
    if (mapping->state == STAGE_A_BATCH_MAPPED) {
        memset(&entry, 0, sizeof(entry));
        entry.virtual_address = mapping->virtual_address;
        entry.length = STAGE_A_BATCH_REGION_SIZE;
        entry.protection = STAGE_A_BATCH_PROTECTION;
        entry.operation = 1;
        if (api->batch_map(&entry, 1, &processed) || processed != 1) {
            mapping->state = STAGE_A_BATCH_RETAIN_UNKNOWN;
            return -2;
        }
        mapping->state = STAGE_A_BATCH_ALLOCATED;
    }
    if (mapping->state == STAGE_A_BATCH_ALLOCATED) {
        if (api->release_physical(mapping->physical_offset,
                                  STAGE_A_BATCH_REGION_SIZE))
            return -3;
        mapping->state = STAGE_A_BATCH_RESERVED;
    }
    if (mapping->state == STAGE_A_BATCH_RESERVED) {
        if (api->release_va(mapping->virtual_address, STAGE_A_BATCH_REGION_SIZE))
            return -4;
    }
    memset(mapping, 0, sizeof(*mapping));
    return 0;
}
