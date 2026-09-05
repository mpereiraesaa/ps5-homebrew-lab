#include "../../../legacy/probes/ps5-agc-phase0/stage_a_batch_mapping.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static int calls[8], call_count, map_rc, map_processed = 1, unmap_processed = 1;
static int64_t fake_physical = 0x200000;
static void *fake_va = (void *)(uintptr_t)0x1000000000ULL;

static int reserve_cb(void **p, size_t n, int f, size_t a) {
    assert(n == 0x20000 && f == 0 && a == 0x10000); calls[call_count++] = 1;
    *p = fake_va; return 0;
}
static int allocate_cb(size_t n, size_t a, int t, int64_t *p) {
    assert(n == 0x20000 && a == 0x10000 && t == 0x0c); calls[call_count++] = 2;
    *p = fake_physical; return 0;
}
static int batch_cb(struct stage_a_batch_entry *e, int count, int *processed) {
    assert(count == 1 && e->virtual_address == fake_va && e->length == 0x20000);
    assert(e->protection == 0x0cf2 && e->reserved == 0);
    if (e->operation == 0) {
        assert(e->physical_offset == fake_physical); calls[call_count++] = 3;
        *processed = map_processed; return map_rc;
    }
    assert(e->operation == 1 && e->physical_offset == 0); calls[call_count++] = 4;
    *processed = unmap_processed; return 0;
}
static int release_physical_cb(int64_t p, size_t n) {
    assert(p == fake_physical && n == 0x20000); calls[call_count++] = 5; return 0;
}
static int release_va_cb(void *p, size_t n) {
    assert(p == fake_va && n == 0x20000); calls[call_count++] = 6; return 0;
}
static const struct stage_a_batch_api api = {
    reserve_cb, allocate_cb, batch_cb, release_va_cb, release_physical_cb
};
static void reset(void) { memset(calls, 0, sizeof(calls)); call_count = 0;
    map_rc = 0; map_processed = 1; unmap_processed = 1; }

int main(void) {
    struct stage_a_batch_mapping m = {0};
    reset(); assert(stage_a_batch_open(&m, &api) == 0);
    assert(m.state == STAGE_A_BATCH_MAPPED);
    assert(stage_a_batch_close(&m, &api) == 0);
    assert(m.state == STAGE_A_BATCH_CLEAN);
    { const int expected[] = {1,2,3,4,5,6};
      assert(call_count == 6 && !memcmp(calls, expected, sizeof(expected))); }

    reset(); map_rc = -9; map_processed = 0;
    assert(stage_a_batch_open(&m, &api) == -4);
    assert(m.state == STAGE_A_BATCH_ALLOCATED);
    assert(stage_a_batch_close(&m, &api) == 0);

    reset(); map_rc = -9; map_processed = -1;
    assert(stage_a_batch_open(&m, &api) == -4);
    assert(m.state == STAGE_A_BATCH_RETAIN_UNKNOWN);
    assert(stage_a_batch_close(&m, &api) == -1);

    reset(); m.state = STAGE_A_BATCH_MAPPED; m.virtual_address = fake_va;
    m.physical_offset = fake_physical; unmap_processed = 0;
    assert(stage_a_batch_close(&m, &api) == -2);
    assert(m.state == STAGE_A_BATCH_RETAIN_UNKNOWN);
    return 0;
}
