/* AGC phase 0K: exact module-geometry gate, then bounded queue metadata read. */
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0k-queue-metadata.log"
#define AGC_DRIVER_SYSMODULE_ID 0x80000080u
#define QUEUE_OFFSET UINT64_C(0x228b8)
#define QUEUE_END_OFFSET (QUEUE_OFFSET + UINT64_C(0x49))

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

int main(void)
{
    int handles[256];
    int count = 0;
    int matches = 0;
    struct module_info agc_info;
    uintptr_t base = 0;
    int load_rc;
    int unload_rc = -1;
    int result = 10;

    memset(&agc_info, 0, sizeof(agc_info));
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    alarm(10);
    probe_log("AGC phase 0K start; exact segment gate then bounded queue metadata; no code reads, dlsym, attach, writes, queue calls or submit");

    load_rc = sceSysmoduleLoadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("LoadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)load_rc);
    if (load_rc != 0)
        goto out;

    {
        int list_rc = sceKernelGetModuleList(handles, 256, &count);
        probe_log("GetModuleList rc=0x%08x count=%d", (unsigned)list_rc, count);
        if (list_rc != 0 || count < 1 || count > 256) {
            result = 11;
            goto unload;
        }
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
        ++matches;
        if (matches == 1)
            agc_info = info;
    }
    probe_log("AgcDriver exact-name matches=%d", matches);
    if (matches != 1 || agc_info.segment_count != 4 ||
        agc_info.segments[0].address == NULL) {
        result = 12;
        goto unload;
    }

    base = (uintptr_t)agc_info.segments[0].address;
    if ((base & UINT64_C(0x3fff)) != 0) {
        result = 13;
        goto unload;
    }
    for (uint32_t i = 0; i < 4; ++i) {
        uintptr_t address = (uintptr_t)agc_info.segments[i].address;
        if (address != base + expected_segments[i].relative ||
            agc_info.segments[i].size != expected_segments[i].size ||
            agc_info.segments[i].prot != expected_segments[i].prot) {
            result = 14;
            goto unload;
        }
    }
    if (QUEUE_OFFSET < expected_segments[3].relative ||
        QUEUE_END_OFFSET > expected_segments[3].relative +
                           expected_segments[3].size) {
        result = 15;
        goto unload;
    }
    probe_log("exact four-segment geometry accepted; queue range contained in raw-prot-3 segment");

    {
        const uint8_t *queue = (const uint8_t *)(base + QUEUE_OFFSET);
        uint32_t size = load_u32(queue + 0x00);
        uint32_t type = load_u32(queue + 0x04);
        int token = load_u64(queue + 0x08) != 0;
        int lock = load_u64(queue + 0x38) != 0;
        unsigned sentinel = queue[0x48];
        probe_log("queue state size=0x%02x type=%u token=%s lock=%s sentinel=%u",
                  size, type, token ? "yes" : "no",
                  lock ? "yes" : "no", sentinel);
        if (size != 0x38u || type != 0u || !token || !lock || sentinel != 1u) {
            result = 16;
            goto unload;
        }
    }
    result = 0;

unload:
    unload_rc = sceSysmoduleUnloadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("UnloadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)unload_rc);
    if (unload_rc != 0 && result == 0)
        result = 17;
out:
    alarm(0);
    probe_log("AGC phase 0K exit result=%d; code_reads=0; queue_bytes_read=25; writes=0; submitted=no",
              result);
    if (log_fd >= 0)
        close(log_fd);
    return result;
}
