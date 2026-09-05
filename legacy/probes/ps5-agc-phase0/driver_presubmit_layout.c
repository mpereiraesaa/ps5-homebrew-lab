/* AGC phase 0L: own direct-memory layout plus initialized queue, no submit. */
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0l-presubmit-layout.log"
#define AGC_DRIVER_SYSMODULE_ID 0x80000080u
#define QUEUE_OFFSET UINT64_C(0x228b8)
#define REGION_SIZE ((size_t)0x20000)
#define REGION_ALIGN ((size_t)0x20000)
#define TARGET_OFFSET ((size_t)0x1000)
#define FENCE_OFFSET ((size_t)0x1008)

int sceSysmoduleLoadModuleInternal(unsigned int id);
int sceSysmoduleUnloadModuleInternal(unsigned int id);
int sceKernelGetModuleList(int *handles, int capacity, int *count);
int sceKernelGetModuleInfo(int handle, void *info);
int sceKernelAllocateMainDirectMemory(size_t size, size_t alignment, int type,
                                      intptr_t *physical_offset);
int sceKernelMapDirectMemory(void **address, size_t size, int protection,
                             int flags, intptr_t physical_offset,
                             size_t alignment);
int sceKernelReleaseDirectMemory(intptr_t physical_offset, size_t size);

struct module_segment_info {
    void *address;
    uint32_t size;
    int32_t prot;
};

struct module_info {
    size_t size;
    char name[256];
    struct module_segment_info segments[4];
    uint32_t segment_count;
    uint8_t fingerprint[20];
};

struct expected_segment {
    uintptr_t relative;
    uint32_t size;
    int32_t prot;
};

static const struct expected_segment expected_segments[4] = {
    {0x00000, 0xc000, 4},
    {0x0c000, 0x8000, 1},
    {0x14000, 0x4000, 1},
    {0x18000, 0xc000, 3},
};

_Static_assert(sizeof(struct module_segment_info) == 0x10,
               "module segment ABI size");
_Static_assert(sizeof(struct module_info) == 0x160, "module info ABI size");
_Static_assert(offsetof(struct module_info, segments) == 0x108,
               "module segments ABI offset");
_Static_assert(offsetof(struct module_info, segment_count) == 0x148,
               "module segment count ABI offset");

static int log_fd = -1;

static void probe_log(const char *fmt, ...)
{
    char line[512];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    if (n < 0)
        return;
    if ((size_t)n >= sizeof(line) - 1)
        n = (int)sizeof(line) - 2;
    line[n++] = '\n';
    if (log_fd >= 0) {
        (void)write(log_fd, line, (size_t)n);
        (void)fsync(log_fd);
    }
    (void)write(STDOUT_FILENO, line, (size_t)n);
}

static void watchdog(int signal_number)
{
    static const char message[] = "watchdog timeout; forcing process exit\n";
    (void)signal_number;
    if (log_fd >= 0)
        (void)write(log_fd, message, sizeof(message) - 1);
    _exit(124);
}

static uint32_t load_u32(const uint8_t *p)
{
    uint32_t value;
    memcpy(&value, p, sizeof(value));
    return value;
}

static uint64_t load_u64(const uint8_t *p)
{
    uint64_t value;
    memcpy(&value, p, sizeof(value));
    return value;
}

static int find_validated_driver(uintptr_t *base_out)
{
    int handles[256];
    int count = 0;
    int matches = 0;
    struct module_info agc_info;
    memset(&agc_info, 0, sizeof(agc_info));

    int rc = sceKernelGetModuleList(handles, 256, &count);
    probe_log("GetModuleList rc=0x%08x count=%d", (unsigned)rc, count);
    if (rc != 0 || count < 1 || count > 256)
        return 11;
    for (int i = 0; i < count; ++i) {
        struct module_info info;
        memset(&info, 0, sizeof(info));
        info.size = sizeof(info);
        if (sceKernelGetModuleInfo(handles[i], &info) != 0)
            continue;
        info.name[sizeof(info.name) - 1] = '\0';
        if (strcmp(info.name, "libSceAgcDriver.sprx") != 0 &&
            strcmp(info.name, "libSceAgcDriver") != 0)
            continue;
        ++matches;
        if (matches == 1)
            agc_info = info;
    }
    probe_log("AgcDriver exact-name matches=%d", matches);
    if (matches != 1 || agc_info.segment_count != 4 ||
        agc_info.segments[0].address == NULL)
        return 12;

    uintptr_t base = (uintptr_t)agc_info.segments[0].address;
    if ((base & UINT64_C(0x3fff)) != 0)
        return 13;
    for (uint32_t i = 0; i < 4; ++i) {
        if ((uintptr_t)agc_info.segments[i].address !=
                base + expected_segments[i].relative ||
            agc_info.segments[i].size != expected_segments[i].size ||
            agc_info.segments[i].prot != expected_segments[i].prot)
            return 14;
    }
    *base_out = base;
    return 0;
}

int main(void)
{
    intptr_t physical_offset = 0;
    void *mapping = NULL;
    int allocated = 0;
    int mapped = 0;
    int driver_loaded = 0;
    int result = 10;

    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    alarm(10);
    probe_log("AGC phase 0L start; queue gate plus own presubmit layout; no dlsym, code reads, queue calls or submit");

    int rc = sceSysmoduleLoadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("LoadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)rc);
    if (rc != 0)
        goto out;
    driver_loaded = 1;

    uintptr_t base = 0;
    result = find_validated_driver(&base);
    if (result != 0)
        goto cleanup;
    {
        const uint8_t *queue = (const uint8_t *)(base + QUEUE_OFFSET);
        uint32_t size = load_u32(queue + 0x00);
        uint32_t type = load_u32(queue + 0x04);
        int token = load_u64(queue + 0x08) != 0;
        int lock = load_u64(queue + 0x38) != 0;
        unsigned sentinel = queue[0x48];
        probe_log("queue gate size=0x%02x type=%u token=%s lock=%s sentinel=%u",
                  size, type, token ? "yes" : "no",
                  lock ? "yes" : "no", sentinel);
        if (size != 0x38u || type != 0u || !token || !lock || sentinel != 1u) {
            result = 15;
            goto cleanup;
        }
    }

    rc = sceKernelAllocateMainDirectMemory(REGION_SIZE, REGION_ALIGN, 3,
                                            &physical_offset);
    probe_log("AllocateMainDirectMemory size=0x%zx align=0x%zx type=3 rc=0x%08x",
              REGION_SIZE, REGION_ALIGN, (unsigned)rc);
    if (rc != 0) {
        result = 16;
        goto cleanup;
    }
    allocated = 1;
    rc = sceKernelMapDirectMemory(&mapping, REGION_SIZE, 0x33, 0,
                                  physical_offset, REGION_ALIGN);
    probe_log("MapDirectMemory size=0x%zx prot=0x33 flags=0 align=0x%zx rc=0x%08x",
              REGION_SIZE, REGION_ALIGN, (unsigned)rc);
    if (rc != 0 || mapping == NULL) {
        result = 17;
        goto cleanup;
    }
    mapped = 1;
    if (((uintptr_t)mapping & (REGION_ALIGN - 1)) != 0) {
        result = 18;
        goto cleanup;
    }

    uint8_t *bytes = (uint8_t *)mapping;
    volatile uint32_t *target = (volatile uint32_t *)(bytes + TARGET_OFFSET);
    volatile uint64_t *fence = (volatile uint64_t *)(bytes + FENCE_OFFSET);
    uint32_t *dcb = (uint32_t *)bytes;
    uintptr_t target_address = (uintptr_t)target;
    uintptr_t fence_address = (uintptr_t)fence;
    const uint32_t expected[15] = {
        0xc0055000, 0xc0300000, 0, 0,
        (uint32_t)target_address, (uint32_t)(target_address >> 32), 4,
        0xc0064900, 0x06000528, 0x42010000,
        (uint32_t)fence_address, (uint32_t)(fence_address >> 32), 0, 0, 0,
    };
    memcpy(dcb, expected, sizeof(expected));
    *target = UINT32_C(0xa5a55a5a);
    *fence = UINT64_C(1);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    if (memcmp(dcb, expected, sizeof(expected)) != 0 ||
        *target != UINT32_C(0xa5a55a5a) || *fence != UINT64_C(1)) {
        result = 19;
        goto cleanup;
    }
    probe_log("presubmit layout verified region=0x20000 dcb=60 target_offset=0x1000 fence_offset=0x1008 target_canary=yes fence_one=yes");
    result = 0;

cleanup:
    if (mapped) {
        rc = munmap(mapping, REGION_SIZE);
        probe_log("munmap rc=0x%08x", (unsigned)rc);
        if (rc != 0 && result == 0)
            result = 20;
    }
    if (allocated) {
        rc = sceKernelReleaseDirectMemory(physical_offset, REGION_SIZE);
        probe_log("ReleaseDirectMemory rc=0x%08x", (unsigned)rc);
        if (rc != 0 && result == 0)
            result = 21;
    }
    if (driver_loaded) {
        rc = sceSysmoduleUnloadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
        probe_log("UnloadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
                  AGC_DRIVER_SYSMODULE_ID, (unsigned)rc);
        if (rc != 0 && result == 0)
            result = 22;
    }
out:
    alarm(0);
    probe_log("AGC phase 0L exit result=%d; own_bytes_written=72; queue_bytes_read=25; code_reads=0; queue_calls=0; submitted=no",
              result);
    if (log_fd >= 0)
        close(log_fd);
    return result;
}
