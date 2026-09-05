/* AGC phase 0G: derive the loaded driver base only after byte signatures match. */
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0g-driver-queue-sigbase.log"
#define AGC_DRIVER_SYSMODULE_ID 0x80000080u
#define AGC_DRIVER_MODULE_NAME "libSceAgcDriver.sprx"
#define AGC_DRIVER_SUBMIT_DCB_NID "UglJIZjGssM"
#define SUBMIT_DCB_OFFSET UINT64_C(0x2960)
#define CREATE_QUEUE_OFFSET UINT64_C(0x2020)
#define INIT_TRAMPOLINE_OFFSET UINT64_C(0x8070)
#define DEFAULT_GRAPHICS_QUEUE_OFFSET UINT64_C(0x228b8)

int sceSysmoduleLoadModuleInternal(unsigned int id);
int sceSysmoduleUnloadModuleInternal(unsigned int id);

static const uint8_t submit_dcb_expected[15] = {
    0x48, 0x89, 0xfe, 0x48, 0x8d, 0x3d, 0x4e, 0xff,
    0x01, 0x00, 0xe9, 0x41, 0xf0, 0xff, 0xff,
};
static const uint8_t create_queue_expected[7] = {
    0x31, 0xc9, 0xe9, 0x09, 0x00, 0x00, 0x00,
};
static const uint8_t init_trampoline_expected[5] = {
    0xe9, 0xab, 0xfb, 0xff, 0xff,
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
    static const char message[] = "fault/timeout; forcing probe exit\n";
    (void)signal_number;
    if (log_fd >= 0)
        (void)write(log_fd, message, sizeof(message) - 1);
    _exit(124);
}

static uint32_t load_u32(const volatile uint8_t *p)
{
    uint32_t value;
    memcpy(&value, (const void *)p, sizeof(value));
    return value;
}

static uint64_t load_u64(const volatile uint8_t *p)
{
    uint64_t value;
    memcpy(&value, (const void *)p, sizeof(value));
    return value;
}

int main(void)
{
    void *module = NULL;
    void *submit = NULL;
    uintptr_t module_base = 0;
    const volatile uint8_t *queue = NULL;
    int load_rc;
    int unload_rc = -1;
    int result = 10;

    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    (void)signal(SIGSEGV, watchdog);
    (void)signal(SIGBUS, watchdog);
    alarm(10);
    probe_log("AGC phase 0G start; signature-derived base; read-only; no queue call or submit");

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
    submit = dlsym(module, AGC_DRIVER_SUBMIT_DCB_NID);
    probe_log("resolve SubmitDcb NID: %s", submit ? "success" : "failed");
    if (!submit) {
        result = 12;
        goto close_module;
    }

    /* First prove dlsym returned the real 12.02 wrapper, not a loader thunk. */
    if (memcmp(submit, submit_dcb_expected, sizeof(submit_dcb_expected)) != 0) {
        result = 13;
        goto close_module;
    }
    module_base = (uintptr_t)submit - SUBMIT_DCB_OFFSET;
    if ((module_base & 0x3fffu) != 0) {
        result = 14;
        goto close_module;
    }
    if (memcmp((const void *)(module_base + CREATE_QUEUE_OFFSET),
               create_queue_expected, sizeof(create_queue_expected)) != 0 ||
        memcmp((const void *)(module_base + INIT_TRAMPOLINE_OFFSET),
               init_trampoline_expected, sizeof(init_trampoline_expected)) != 0) {
        result = 15;
        goto close_module;
    }
    probe_log("module base proven by three firmware-12.02 signatures");

    queue = (const volatile uint8_t *)(module_base + DEFAULT_GRAPHICS_QUEUE_OFFSET);
    probe_log("default graphics queue size=0x%08x index=%u",
              load_u32(queue), load_u32(queue + 4));
    probe_log("queue state nonzero: token=%s lock_context=%s aux=%s",
              load_u64(queue + 8) ? "yes" : "no",
              load_u64(queue + 0x38) ? "yes" : "no",
              load_u64(queue + 0x40) ? "yes" : "no");
    if (load_u32(queue) != 0x38u) {
        result = 16;
        goto close_module;
    }
    result = 0;

close_module:
    (void)dlclose(module);
unload:
    unload_rc = sceSysmoduleUnloadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("UnloadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)unload_rc);
    if (unload_rc != 0 && result == 0)
        result = 17;
out:
    alarm(0);
    probe_log("AGC phase 0G exit result=%d; reads_bounded=yes; called_create_queue=no; submitted=no",
              result);
    if (log_fd >= 0)
        close(log_fd);
    return result;
}
