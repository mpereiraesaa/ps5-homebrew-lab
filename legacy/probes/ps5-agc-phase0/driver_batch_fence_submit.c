/* Phase 0R draft: first ownership-fenced submit over proven BatchMap 0xcf2. */
#include "stage_a_batch_mapping.h"

#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0s-batch-fence-submit.log"
#define PHASE_PARKED "PARKED_PHASE0S"
#define DRIVER_ID 0x80000080u
#define DRIVER_NAME "libSceAgcDriver.sprx"
#define SUBMIT_NID "UglJIZjGssM"
#define QUEUE_OFFSET UINT64_C(0x228b8)
#define DRIVER_STATE_OFFSET UINT64_C(0x22908)
#define CLASS0_CALLBACK_OFFSET UINT64_C(0x1100)
#define TARGET_OFFSET ((size_t)0x1000)
#define FENCE_OFFSET ((size_t)0x1008)
#define DEADLINE_NS UINT64_C(2000000000)

int sceSysmoduleLoadModuleInternal(unsigned int);
int sceSysmoduleUnloadModuleInternal(unsigned int);
int sceKernelGetModuleList(int *, int, int *);
int sceKernelGetModuleInfo(int, void *);
int sceKernelReserveVirtualRange(void **, size_t, int, size_t);
int sceKernelAllocateMainDirectMemory(size_t, size_t, int, int64_t *);
int sceKernelBatchMap(struct stage_a_batch_entry *, int, int *);
int sceKernelReleaseDirectMemory(int64_t, size_t);

struct segment { void *address; uint32_t size; int32_t prot; };
struct module_info {
    size_t size;
    char name[256];
    struct segment segments[4];
    uint32_t segment_count;
    uint8_t fingerprint[20];
};
struct submit_info {
    const uint32_t *command_buffer;
    uint32_t size_dwords;
    uint8_t field_0c;
    uint8_t padding[3];
};
typedef int (*submit_dcb_fn)(const struct submit_info *);

_Static_assert(sizeof(struct module_info) == 0x160, "module ABI");
_Static_assert(sizeof(struct submit_info) == 0x10, "submit ABI");
_Static_assert(15u * sizeof(uint32_t) <= TARGET_OFFSET, "stream overlap");
_Static_assert(TARGET_OFFSET + 4 <= FENCE_OFFSET, "target/fence overlap");
_Static_assert(FENCE_OFFSET + 8 <= STAGE_A_BATCH_REGION_SIZE, "fence range");

static int log_fd = -1;
static volatile sig_atomic_t submit_started;

static void log_line(const char *format, ...)
{
    char line[512];
    va_list ap;
    va_start(ap, format);
    int n = vsnprintf(line, sizeof(line), format, ap);
    va_end(ap);
    if (n < 0) return;
    if ((size_t)n >= sizeof(line) - 1) n = (int)sizeof(line) - 2;
    line[n++] = '\n';
    if (log_fd >= 0) { (void)write(log_fd, line, (size_t)n); (void)fsync(log_fd); }
    (void)write(STDOUT_FILENO, line, (size_t)n);
}

static void park(const char *reason)
{
    log_line(PHASE_PARKED " reason=%s; retain driver, process and mapping; DO_NOT_CLOSE_FAKE00000",
             reason);
    alarm(0);
    for (;;) (void)pause();
}

static void watchdog(int signal_number)
{
    static const char before[] = "watchdog before submit; exit=124 submitted=no\n";
    static const char after[] = PHASE_PARKED
        " watchdog after submit; retain all; DO_NOT_CLOSE_FAKE00000\n";
    (void)signal_number;
    if (submit_started) {
        if (log_fd >= 0) { (void)write(log_fd, after, sizeof(after) - 1); (void)fsync(log_fd); }
        for (;;) (void)pause();
    }
    if (log_fd >= 0) (void)write(log_fd, before, sizeof(before) - 1);
    _exit(124);
}

static uint64_t monotonic_ns(void)
{
    struct timespec ts;
    (void)clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}
static uint32_t read32(const void *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static uint64_t read64(const void *p) { uint64_t v; memcpy(&v, p, 8); return v; }

static int validated_queue(void)
{
    static const uintptr_t rel[4] = {0, 0xc000, 0x14000, 0x18000};
    static const uint32_t size[4] = {0xc000, 0x8000, 0x4000, 0xc000};
    static const int32_t prot[4] = {4, 1, 1, 3};
    int handles[256], count = 0, matches = 0;
    struct module_info found;
    memset(&found, 0, sizeof(found));
    if (sceKernelGetModuleList(handles, 256, &count) || count < 1 || count > 256)
        return 0;
    for (int i = 0; i < count; ++i) {
        struct module_info info;
        memset(&info, 0, sizeof(info)); info.size = sizeof(info);
        if (sceKernelGetModuleInfo(handles[i], &info)) continue;
        info.name[255] = '\0';
        if (strcmp(info.name, DRIVER_NAME) && strcmp(info.name, "libSceAgcDriver"))
            continue;
        if (++matches == 1) found = info;
    }
    if (matches != 1 || found.segment_count != 4 || !found.segments[0].address)
        return 0;
    uintptr_t base = (uintptr_t)found.segments[0].address;
    if (base & 0x3fff) return 0;
    for (unsigned i = 0; i < 4; ++i)
        if ((uintptr_t)found.segments[i].address != base + rel[i] ||
            found.segments[i].size != size[i] || found.segments[i].prot != prot[i])
            return 0;
    const uint8_t *q = (const uint8_t *)(base + QUEUE_OFFSET);
    const uint8_t *state = (const uint8_t *)(base + DRIVER_STATE_OFFSET);
    return read32(q) == 0x38 && read32(q + 4) == 0 && read64(q + 8) != 0 &&
           read64(q + 0x38) != 0 && q[0x48] == 1 &&
           read32(state + 0x08) == 0 &&
           read64(state + 0x50) == base + CLASS0_CALLBACK_OFFSET &&
           read32(state + 0x120) == 0 && read32(state + 0x1cc) == 0;
}

static int reserve_cb(void **p, size_t n, int f, size_t a)
{ return sceKernelReserveVirtualRange(p, n, f, a); }
static int allocate_cb(size_t n, size_t a, int t, int64_t *p)
{ return sceKernelAllocateMainDirectMemory(n, a, t, p); }
static int batch_cb(struct stage_a_batch_entry *e, int n, int *p)
{ return sceKernelBatchMap(e, n, p); }
static int release_va_cb(void *p, size_t n) { return munmap(p, n); }
static int release_physical_cb(int64_t p, size_t n)
{ return sceKernelReleaseDirectMemory(p, n); }

int main(void)
{
    static const struct stage_a_batch_api api = {
        reserve_cb, allocate_cb, batch_cb, release_va_cb, release_physical_cb
    };
    struct stage_a_batch_mapping mapping;
    memset(&mapping, 0, sizeof(mapping));
    void *module = NULL;
    int loaded = 0, result = 10;
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog); (void)signal(SIGSEGV, watchdog);
    (void)signal(SIGBUS, watchdog); alarm(12);
    log_line("phase0S start; BatchMap 0xcf2; ownership RELEASE_MEM only; no VideoOut");
    if (sceSysmoduleLoadModuleInternal(DRIVER_ID)) goto cleanup;
    loaded = 1;
    if (!validated_queue()) { result = 11; goto cleanup; }
    if (stage_a_batch_open(&mapping, &api)) { result = 12; goto cleanup; }
    log_line("queue pristine and BatchMap accepted state=3");

    uint8_t *b = mapping.virtual_address;
    volatile uint64_t *fence = (volatile uint64_t *)(b + FENCE_OFFSET);
    uintptr_t fa = (uintptr_t)fence;
    const uint32_t stream[8] = {
        0xc0064900, 0x06000528, 0x42010000,
        (uint32_t)fa, (uint32_t)(fa >> 32), 0, 0, 0,
    };
    memcpy(b, stream, sizeof(stream));
    __atomic_store_n(fence, UINT64_C(1), __ATOMIC_RELEASE);
    module = dlopen(DRIVER_NAME, RTLD_NOW);
    submit_dcb_fn submit = module ? (submit_dcb_fn)dlsym(module, SUBMIT_NID) : NULL;
    if (!submit) { result = 13; goto cleanup; }
    struct submit_info info = {(const uint32_t *)b, 8, 0, {0, 0, 0}};
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    submit_started = 1;
    int submit_rc = submit(&info);
    log_line("SubmitDcb returned rc=0x%08x", (unsigned)submit_rc);
    if (submit_rc) park("submit return is not completion evidence");

    uint64_t deadline = monotonic_ns() + DEADLINE_NS;
    while (__atomic_load_n(fence, __ATOMIC_ACQUIRE) != 0 &&
           monotonic_ns() < deadline) {
        struct timespec delay = {0, 1000000};
        (void)nanosleep(&delay, NULL);
    }
    if (__atomic_load_n(fence, __ATOMIC_ACQUIRE) != 0) park("fence timeout");
    submit_started = 0;
    log_line("GPU ownership complete fence=0");
    result = 0;

cleanup:
    alarm(0);
    if (mapping.state != STAGE_A_BATCH_CLEAN && stage_a_batch_close(&mapping, &api))
        park("pre-submit or completed cleanup ambiguous");
    if (module) (void)dlclose(module);
    if (loaded) (void)sceSysmoduleUnloadModuleInternal(DRIVER_ID);
    log_line("phase0S exit result=%d submitted=%s", result,
             result == 0 ? "yes-complete" : "no");
    if (log_fd >= 0) close(log_fd);
    return result;
}
