/* AGC phase 0I: locate our own AgcDriver via kernel module metadata and read
 * bounded queue state. No dlsym/dladdr, debugger attach, writes, queue calls,
 * PM4, or submit. */
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0i-module-queue-state.log"
#define AGC_DRIVER_SYSMODULE_ID 0x80000080u
#define SUBMIT_DCB_OFFSET UINT64_C(0x2960)
#define DEFAULT_GRAPHICS_QUEUE_OFFSET UINT64_C(0x228b8)

int sceSysmoduleLoadModuleInternal(unsigned int id);
int sceSysmoduleUnloadModuleInternal(unsigned int id);
int sceKernelGetModuleList(int *handles, int capacity, int *count);
int sceKernelGetModuleInfo(int handle, void *info);

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

_Static_assert(sizeof(struct module_segment_info) == 0x10,
               "module segment ABI size");
_Static_assert(sizeof(struct module_info) == 0x160, "module info ABI size");
_Static_assert(offsetof(struct module_info, segments) == 0x108,
               "module segments ABI offset");
_Static_assert(offsetof(struct module_info, segment_count) == 0x148,
               "module segment count ABI offset");

static const uint8_t submit_dcb_expected[15] = {
    0x48, 0x89, 0xfe, 0x48, 0x8d, 0x3d, 0x4e, 0xff,
    0x01, 0x00, 0xe9, 0x41, 0xf0, 0xff, 0xff,
};
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

int main(void)
{
    int handles[256];
    int count = 0;
    int matching_handle = -1;
    uintptr_t module_base = 0;
    struct module_info agc_info;
    int load_rc;
    int list_rc = -1;
    int unload_rc = -1;
    int result = 10;

    memset(&agc_info, 0, sizeof(agc_info));
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    alarm(10);
    probe_log("AGC phase 0I start; own module metadata and bounded queue read; no dlsym, attach, writes, queue calls or submit");

    load_rc = sceSysmoduleLoadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("LoadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)load_rc);
    if (load_rc != 0)
        goto out;

    list_rc = sceKernelGetModuleList(handles, 256, &count);
    probe_log("GetModuleList rc=0x%08x count=%d", (unsigned)list_rc, count);
    if (list_rc != 0 || count < 1 || count > 256) {
        result = 11;
        goto unload;
    }

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
        if (matching_handle != -1) {
            result = 12;
            goto unload;
        }
        matching_handle = handles[i];
        agc_info = info;
        module_base = (uintptr_t)info.segments[0].address;
    }

    probe_log("AgcDriver exact-name matches=%d", matching_handle == -1 ? 0 : 1);
    if (matching_handle == -1 || module_base == 0 ||
        (module_base & UINT64_C(0x3fff)) != 0 ||
        agc_info.segment_count < 1 || agc_info.segment_count > 4) {
        result = 13;
        goto unload;
    }

    {
        uintptr_t wrapper = module_base + SUBMIT_DCB_OFFSET;
        uintptr_t queue = module_base + DEFAULT_GRAPHICS_QUEUE_OFFSET;
        int wrapper_rx = 0;
        int queue_readable = 0;
        for (uint32_t i = 0; i < agc_info.segment_count; ++i) {
            uintptr_t start = (uintptr_t)agc_info.segments[i].address;
            uintptr_t end = start + agc_info.segments[i].size;
            if (end < start)
                continue;
            if (wrapper >= start && wrapper + sizeof(submit_dcb_expected) <= end &&
                (agc_info.segments[i].prot & 5) == 5)
                wrapper_rx = 1;
            if (queue >= start && queue + 0x50 <= end &&
                (agc_info.segments[i].prot & 1) != 0)
                queue_readable = 1;
        }
        probe_log("module segment gates wrapper_rx=%s queue_readable=%s",
                  wrapper_rx ? "yes" : "no",
                  queue_readable ? "yes" : "no");
        if (!wrapper_rx || !queue_readable) {
            result = 13;
            goto unload;
        }
    }

    if (memcmp((const void *)(module_base + SUBMIT_DCB_OFFSET),
               submit_dcb_expected, sizeof(submit_dcb_expected)) != 0) {
        result = 14;
        goto unload;
    }
    probe_log("module base/range validated; SubmitDcb wrapper matches firmware 12.02");

    {
        const uint8_t *queue =
            (const uint8_t *)(module_base + DEFAULT_GRAPHICS_QUEUE_OFFSET);
        uint32_t size = load_u32(queue);
        uint32_t type = load_u32(queue + 4);
        int token = load_u64(queue + 8) != 0;
        int lock = load_u64(queue + 0x38) != 0;
        unsigned sentinel = queue[0x48];
        probe_log("queue state size=0x%02x type=%u token=%s lock=%s sentinel=%u",
                  size, type, token ? "yes" : "no",
                  lock ? "yes" : "no", sentinel);
        if (size != 0x38u || type != 0u || !token || !lock || sentinel != 1u) {
            result = 15;
            goto unload;
        }
    }
    result = 0;

unload:
    unload_rc = sceSysmoduleUnloadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("UnloadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)unload_rc);
    if (unload_rc != 0 && result == 0)
        result = 16;
out:
    alarm(0);
    probe_log("AGC phase 0I exit result=%d; called_create_queue=no; writes=0; submitted=no",
              result);
    if (log_fd >= 0)
        close(log_fd);
    return result;
}
