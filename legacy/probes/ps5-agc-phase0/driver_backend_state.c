/* AGC phase 0P: exact module-geometry gate, then bounded backend-state read. */
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0p-backend-state.log"
#define AGC_DRIVER_SYSMODULE_ID 0x80000080u
#define STATE_OFFSET UINT64_C(0x22908)
#define READY_OFFSET (STATE_OFFSET + UINT64_C(0x08))
#define CALLBACK_OFFSET (STATE_OFFSET + UINT64_C(0x50))
#define SELECTOR_OFFSET (STATE_OFFSET + UINT64_C(0x120))
#define GRAPHICS_BACKEND_OFFSET UINT64_C(0x1100)

int sceSysmoduleLoadModuleInternal(unsigned int id);
int sceSysmoduleUnloadModuleInternal(unsigned int id);
int sceKernelGetModuleList(int *handles, int capacity, int *count);
int sceKernelGetModuleInfo(int handle, void *info);

struct module_segment_info { void *address; uint32_t size; int32_t prot; };
struct module_info {
    size_t size;
    char name[256];
    struct module_segment_info segments[4];
    uint32_t segment_count;
    uint8_t fingerprint[20];
};
struct expected_segment { uintptr_t relative; uint32_t size; int32_t prot; };
static const struct expected_segment expected_segments[4] = {
    {0x00000, 0xc000, 4}, {0x0c000, 0x8000, 1},
    {0x14000, 0x4000, 1}, {0x18000, 0xc000, 3},
};

_Static_assert(sizeof(struct module_segment_info) == 0x10, "segment ABI");
_Static_assert(sizeof(struct module_info) == 0x160, "module ABI");
_Static_assert(offsetof(struct module_info, segments) == 0x108, "segments ABI");
_Static_assert(offsetof(struct module_info, segment_count) == 0x148, "count ABI");

static int log_fd = -1;
static void probe_log(const char *fmt, ...)
{
    char line[512]; va_list ap; va_start(ap, fmt);
    int n = vsnprintf(line, sizeof(line), fmt, ap); va_end(ap);
    if (n < 0) return;
    if ((size_t)n >= sizeof(line) - 1) n = (int)sizeof(line) - 2;
    line[n++] = '\n';
    if (log_fd >= 0) { (void)write(log_fd, line, (size_t)n); (void)fsync(log_fd); }
    (void)write(STDOUT_FILENO, line, (size_t)n);
}
static void watchdog(int sig)
{
    static const char msg[] = "watchdog timeout; forcing process exit\n";
    (void)sig; if (log_fd >= 0) (void)write(log_fd, msg, sizeof(msg)-1); _exit(124);
}
static uint32_t load_u32(const void *p) { uint32_t v; memcpy(&v,p,4); return v; }
static uint64_t load_u64(const void *p) { uint64_t v; memcpy(&v,p,8); return v; }

int main(void)
{
    int handles[256], count = 0, matches = 0, result = 10, unload_rc = -1;
    struct module_info agc_info; uintptr_t base = 0;
    memset(&agc_info, 0, sizeof(agc_info));
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog); alarm(10);
    probe_log("AGC phase 0P start; bounded backend-state read; no code reads, dlsym, queue calls, writes or submit");
    int load_rc = sceSysmoduleLoadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("LoadModuleInternal rc=0x%08x", (unsigned)load_rc);
    if (load_rc != 0) goto out;
    if (sceKernelGetModuleList(handles, 256, &count) != 0 || count < 1 || count > 256) {
        result = 11; goto unload;
    }
    for (int i=0; i<count; ++i) {
        struct module_info info; memset(&info,0,sizeof(info)); info.size=sizeof(info);
        if (sceKernelGetModuleInfo(handles[i], &info) != 0) continue;
        info.name[sizeof(info.name)-1] = '\0';
        if (strcmp(info.name,"libSceAgcDriver.sprx") && strcmp(info.name,"libSceAgcDriver")) continue;
        ++matches; if (matches == 1) agc_info = info;
    }
    if (matches != 1 || agc_info.segment_count != 4 || !agc_info.segments[0].address) {
        result = 12; goto unload;
    }
    base = (uintptr_t)agc_info.segments[0].address;
    if (base & UINT64_C(0x3fff)) { result = 13; goto unload; }
    for (uint32_t i=0; i<4; ++i) {
        if ((uintptr_t)agc_info.segments[i].address != base+expected_segments[i].relative ||
            agc_info.segments[i].size != expected_segments[i].size ||
            agc_info.segments[i].prot != expected_segments[i].prot) {
            result = 14; goto unload;
        }
    }
    if (READY_OFFSET < 0x18000 || SELECTOR_OFFSET+4 > 0x24000) { result=15; goto unload; }
    {
        uint32_t ready = load_u32((const void *)(base + READY_OFFSET));
        uint64_t callback = load_u64((const void *)(base + CALLBACK_OFFSET));
        uint32_t selector = load_u32((const void *)(base + SELECTOR_OFFSET));
        int callback_matches = callback == (uint64_t)(base + GRAPHICS_BACKEND_OFFSET);
        probe_log("backend state ready=%u callback_is_base_plus_1100=%s selector=%u",
                  ready, callback_matches ? "yes" : "no", selector);
        if (!callback_matches) { result = 16; goto unload; }
        result = 0;
    }
unload:
    unload_rc = sceSysmoduleUnloadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("UnloadModuleInternal rc=0x%08x", (unsigned)unload_rc);
    if (unload_rc != 0 && result == 0) result = 17;
out:
    alarm(0);
    probe_log("AGC phase 0P exit result=%d; data_bytes_read=16; writes=0; submitted=no", result);
    if (log_fd >= 0) close(log_fd);
    return result;
}
