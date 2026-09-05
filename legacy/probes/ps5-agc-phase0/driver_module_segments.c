/* AGC phase 0J: inventory only AgcDriver module segment geometry/protection. */
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0j-module-segments.log"
#define AGC_DRIVER_SYSMODULE_ID 0x80000080u

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

int main(void)
{
    int handles[256];
    int count = 0;
    int matches = 0;
    struct module_info agc_info;
    int load_rc;
    int list_rc = -1;
    int unload_rc = -1;
    int result = 10;

    memset(&agc_info, 0, sizeof(agc_info));
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    alarm(10);
    probe_log("AGC phase 0J start; module segment metadata only; no code/data reads, dlsym, attach, writes, queue calls or submit");

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
        ++matches;
        if (matches == 1)
            agc_info = info;
    }
    probe_log("AgcDriver exact-name matches=%d", matches);
    if (matches != 1 || agc_info.segment_count < 1 ||
        agc_info.segment_count > 4 || agc_info.segments[0].address == NULL) {
        result = 12;
        goto unload;
    }

    {
        uintptr_t base = (uintptr_t)agc_info.segments[0].address;
        if ((base & UINT64_C(0x3fff)) != 0) {
            result = 13;
            goto unload;
        }
        probe_log("segment_count=%u base_alignment=0x4000",
                  agc_info.segment_count);
        for (uint32_t i = 0; i < agc_info.segment_count; ++i) {
            uintptr_t address = (uintptr_t)agc_info.segments[i].address;
            if (address < base) {
                result = 14;
                goto unload;
            }
            probe_log("segment[%u] relative=0x%llx size=0x%x prot=0x%08x",
                      i, (unsigned long long)(address - base),
                      agc_info.segments[i].size,
                      (unsigned)agc_info.segments[i].prot);
        }
    }
    result = 0;

unload:
    unload_rc = sceSysmoduleUnloadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("UnloadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)unload_rc);
    if (unload_rc != 0 && result == 0)
        result = 15;
out:
    alarm(0);
    probe_log("AGC phase 0J exit result=%d; code_reads=0; data_reads=0; writes=0; submitted=no",
              result);
    if (log_fd >= 0)
        close(log_fd);
    return result;
}
