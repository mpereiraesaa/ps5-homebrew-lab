/* AGC phase 0C: query the already-used AgcDriver DMEM getter only. */
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0c-driver-dmem.log"
#define AGC_DRIVER_SYSMODULE_ID 0x80000080u
#define AGC_DRIVER_MODULE_NAME "libSceAgcDriver.sprx"
#define AGC_DRIVER_GET_DMEM_NID "Um-jkyDy9rI"
#define EXPECTED_FS_TABLE_BASE UINT64_C(0xfe0040000)

int sceSysmoduleLoadModuleInternal(unsigned int id);
int sceSysmoduleUnloadModuleInternal(unsigned int id);
typedef uint64_t (*agc_driver_get_dmem_fn)(uint64_t *, uint32_t *);

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
    uint64_t base = 0;
    uint32_t size = 0;
    uint64_t get_rc = UINT64_MAX;
    void *module = NULL;
    agc_driver_get_dmem_fn get_dmem = NULL;
    int load_rc;
    int unload_rc = -1;
    int result = 10;

    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    alarm(10);
    probe_log("AGC phase 0C start; driver DMEM query only; no libAgc or submit");

    load_rc = sceSysmoduleLoadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("LoadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)load_rc);
    if (load_rc != 0)
        goto out;

    module = dlopen(AGC_DRIVER_MODULE_NAME, RTLD_NOW | RTLD_LOCAL);
    probe_log("dlopen AgcDriver: %s", module ? "success" : "failed");
    if (!module) {
        result = 11;
        goto unload;
    }

    get_dmem = (agc_driver_get_dmem_fn)dlsym(module, AGC_DRIVER_GET_DMEM_NID);
    probe_log("resolve GetDmem NID: %s", get_dmem ? "success" : "failed");
    if (!get_dmem) {
        result = 12;
        goto close_module;
    }

    get_rc = get_dmem(&base, &size);
    probe_log("GetDmem rc=0x%016llx base=0x%016llx size=0x%08x",
              (unsigned long long)get_rc, (unsigned long long)base, size);
    probe_log("FS-table expected-base match: %s",
              ((base + 3u) & ~UINT64_C(3)) == EXPECTED_FS_TABLE_BASE
                  ? "yes" : "no");
    result = get_rc == 0 && base != 0 && size != 0 ? 0 : 13;

close_module:
    (void)dlclose(module);
unload:
    unload_rc = sceSysmoduleUnloadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("UnloadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)unload_rc);
    if (unload_rc != 0 && result == 0)
        result = 14;
out:
    alarm(0);
    probe_log("AGC phase 0C exit result=%d", result);
    if (log_fd >= 0)
        close(log_fd);
    return result;
}
