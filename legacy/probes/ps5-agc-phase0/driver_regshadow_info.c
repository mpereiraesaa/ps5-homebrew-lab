/* AGC phase 0H: query exported register-shadow metadata only. */
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0h-regshadow-info.log"
#define AGC_DRIVER_SYSMODULE_ID 0x80000080u
#define AGC_DRIVER_MODULE_NAME "libSceAgcDriver.sprx"
#define AGC_DRIVER_GET_REG_SHADOW_INFO_NID "CP-kVAMmWVw"

int sceSysmoduleLoadModuleInternal(unsigned int id);
int sceSysmoduleUnloadModuleInternal(unsigned int id);
typedef uint64_t (*agc_driver_get_reg_shadow_info_fn)(void *);

struct reg_shadow_info {
    uint8_t bytes[40];
};

_Static_assert(sizeof(struct reg_shadow_info) == 40, "firmware getter writes 40 bytes");

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
    struct reg_shadow_info info;
    void *module = NULL;
    agc_driver_get_reg_shadow_info_fn getter = NULL;
    uint64_t getter_rc = UINT64_MAX;
    unsigned nonzero_qwords = 0;
    int load_rc;
    int unload_rc = -1;
    int result = 10;

    memset(&info, 0, sizeof(info));
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    alarm(10);
    probe_log("AGC phase 0H start; exported RegShadowInfo query only; no libAgc, queue calls or submit");

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

    getter = (agc_driver_get_reg_shadow_info_fn)dlsym(
        module, AGC_DRIVER_GET_REG_SHADOW_INFO_NID);
    probe_log("resolve GetRegShadowInfo NID: %s", getter ? "success" : "failed");
    if (!getter) {
        result = 12;
        goto close_module;
    }

    getter_rc = getter(&info);
    for (size_t offset = 0; offset < sizeof(info); offset += sizeof(uint64_t)) {
        uint64_t value;
        memcpy(&value, info.bytes + offset, sizeof(value));
        if (value != 0)
            ++nonzero_qwords;
    }
    probe_log("GetRegShadowInfo rc=0x%016llx output_qwords_nonzero=%u/5",
              (unsigned long long)getter_rc, nonzero_qwords);
    probe_log("class-zero gate accepted: %s", getter_rc == 0 ? "yes" : "no");
    result = getter_rc == 0 ? 0 : 13;

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
    probe_log("AGC phase 0H exit result=%d; called_create_queue=no; submitted=no", result);
    if (log_fd >= 0)
        close(log_fd);
    return result;
}
