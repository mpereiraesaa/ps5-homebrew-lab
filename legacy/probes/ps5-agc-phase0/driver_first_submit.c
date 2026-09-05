/* AGC phase 0M draft: one 4-byte DMA plus fence; NOT approved for deployment. */
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

#define LOG_PATH "/data/ps5-agc-phase0m-first-submit.log"
#define DRIVER_ID 0x80000080u
#define DRIVER_NAME "libSceAgcDriver.sprx"
#define SUBMIT_NID "UglJIZjGssM"
#define QUEUE_OFFSET UINT64_C(0x228b8)
#define DRIVER_STATE_OFFSET UINT64_C(0x22908)
#define CLASS0_CALLBACK_OFFSET UINT64_C(0x1100)
#define REGION_SIZE ((size_t)0x20000)
#define REGION_ALIGN ((size_t)0x10000)
#define TARGET_OFFSET ((size_t)0x1000)
#define FENCE_OFFSET ((size_t)0x1008)
#define DEADLINE_NS UINT64_C(2000000000)

_Static_assert((15u * sizeof(uint32_t)) <= TARGET_OFFSET,
               "command stream must not overlap target");
_Static_assert((TARGET_OFFSET % _Alignof(uint32_t)) == 0,
               "target alignment");
_Static_assert((FENCE_OFFSET % _Alignof(uint64_t)) == 0,
               "fence alignment");
_Static_assert(TARGET_OFFSET + sizeof(uint32_t) <= FENCE_OFFSET,
               "target must not overlap fence");
_Static_assert(FENCE_OFFSET + sizeof(uint64_t) <= REGION_SIZE,
               "fence must remain inside direct-memory mapping");

int sceSysmoduleLoadModuleInternal(unsigned int);
int sceSysmoduleUnloadModuleInternal(unsigned int);
int sceKernelGetModuleList(int *, int, int *);
int sceKernelGetModuleInfo(int, void *);
int sceKernelReserveVirtualRange(void **, size_t, int, size_t);
int sceKernelAllocateMainDirectMemory(size_t, size_t, int, intptr_t *);
int sceKernelMapDirectMemory(void **, size_t, int, int, intptr_t, size_t);
int sceKernelReleaseDirectMemory(intptr_t, size_t);

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

_Static_assert(sizeof(struct segment) == 0x10, "segment ABI");
_Static_assert(sizeof(struct module_info) == 0x160, "module ABI");
_Static_assert(offsetof(struct module_info, segments) == 0x108,
               "segments ABI offset");
_Static_assert(offsetof(struct module_info, segment_count) == 0x148,
               "count ABI offset");
_Static_assert(sizeof(struct submit_info) == 0x10, "submit ABI");

static int log_fd = -1;
static volatile sig_atomic_t submit_started;

static void log_line(const char *fmt, ...)
{
    char line[512];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if ((size_t)n >= sizeof(line) - 1) n = (int)sizeof(line) - 2;
    line[n++] = '\n';
    if (log_fd >= 0) { (void)write(log_fd, line, (size_t)n); (void)fsync(log_fd); }
    (void)write(STDOUT_FILENO, line, (size_t)n);
}

static void park_forever(const char *message, size_t length)
{
    if (log_fd >= 0) { (void)write(log_fd, message, length); (void)fsync(log_fd); }
    for (;;) (void)pause();
}

static void watchdog(int sig)
{
    static const char before[] = "watchdog before submit; exiting\n";
    static const char after[] =
        "PARKED_AFTER_SUBMIT; resources retained; DO_NOT_CLOSE_FAKE00000\n";
    (void)sig;
    if (submit_started) park_forever(after, sizeof(after) - 1);
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
           read32(state + 0x120) == 0 &&
           read32(state + 0x1cc) == 0;
}

int main(void)
{
    static const char parked[] =
        "PARKED_FENCE_TIMEOUT; resources retained; DO_NOT_CLOSE_FAKE00000\n";
    intptr_t physical = 0;
    void *reserved = NULL, *mapping = NULL, *module = NULL;
    int loaded = 0, reserved_ok = 0, allocated = 0, mapped = 0, result = 10;
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog); alarm(10);
    log_line("AGC phase 0M DRAFT start; one private 4-byte DMA plus fence; no VideoOut");
    if (sceSysmoduleLoadModuleInternal(DRIVER_ID)) goto cleanup;
    loaded = 1;
    if (!validated_queue()) { result = 11; goto cleanup; }
    log_line("exact queue and pristine class-0 lazy-registration gate accepted");
    if (sceKernelReserveVirtualRange(&reserved, REGION_SIZE, 0, REGION_ALIGN) ||
        !reserved) {
        result = 12; goto cleanup;
    }
    reserved_ok = 1;
    if (sceKernelAllocateMainDirectMemory(REGION_SIZE, REGION_ALIGN, 0x0c,
                                          &physical)) {
        result = 13; goto cleanup;
    }
    allocated = 1;
    mapping = reserved;
    if (sceKernelMapDirectMemory(&mapping, REGION_SIZE, 0x0f2, 0x10,
                                 physical, 0) || mapping != reserved) {
        result = 14; goto cleanup;
    }
    mapped = 1;
    if ((uintptr_t)mapping & (REGION_ALIGN - 1)) { result = 15; goto cleanup; }
    uint8_t *b = mapping;
    volatile uint32_t *target = (volatile uint32_t *)(b + TARGET_OFFSET);
    volatile uint64_t *fence = (volatile uint64_t *)(b + FENCE_OFFSET);
    uintptr_t ta = (uintptr_t)target, fa = (uintptr_t)fence;
    const uint32_t stream[15] = {
        0xc0055000, 0xc0300000, 0, 0, (uint32_t)ta, (uint32_t)(ta >> 32), 4,
        0xc0064900, 0x06000528, 0x42010000,
        (uint32_t)fa, (uint32_t)(fa >> 32), 0, 0, 0,
    };
    memcpy(b, stream, sizeof(stream));
    __atomic_store_n(target, UINT32_C(0xa5a55a5a), __ATOMIC_RELEASE);
    __atomic_store_n(fence, UINT64_C(1), __ATOMIC_RELEASE);
    struct submit_info info = {(const uint32_t *)b, 15, 0, {0, 0, 0}};
    module = dlopen(DRIVER_NAME, RTLD_NOW);
    submit_dcb_fn submit = module ? (submit_dcb_fn)dlsym(module, SUBMIT_NID) : NULL;
    if (!submit) { result = 16; goto cleanup; }
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    submit_started = 1;
    int submit_rc = submit(&info);
    alarm(0);
    log_line("SubmitDcb returned rc=0x%08x", (unsigned)submit_rc);
    if (submit_rc) {
        static const char rejected[] =
            "PARKED_SUBMIT_ERROR; enqueue state unknown; DO_NOT_CLOSE_FAKE00000\n";
        park_forever(rejected, sizeof(rejected) - 1);
    }
    uint64_t deadline = monotonic_ns() + DEADLINE_NS;
    while (__atomic_load_n(fence, __ATOMIC_ACQUIRE) != 0 &&
           monotonic_ns() < deadline) {
        struct timespec delay = {0, 1000000};
        (void)nanosleep(&delay, NULL);
    }
    if (__atomic_load_n(fence, __ATOMIC_ACQUIRE) != 0)
        park_forever(parked, sizeof(parked) - 1);
    submit_started = 0;
    if (__atomic_load_n(target, __ATOMIC_ACQUIRE) != 0) {
        result = 17; goto cleanup;
    }
    log_line("GPU completion verified target=0 fence=0");
    result = 0;

cleanup:
    alarm(0);
    if (module) (void)dlclose(module);
    if (reserved_ok) (void)munmap(mapped ? mapping : reserved, REGION_SIZE);
    if (allocated) (void)sceKernelReleaseDirectMemory(physical, REGION_SIZE);
    if (loaded) (void)sceSysmoduleUnloadModuleInternal(DRIVER_ID);
    log_line("AGC phase 0M exit result=%d", result);
    if (log_fd >= 0) close(log_fd);
    return result;
}
