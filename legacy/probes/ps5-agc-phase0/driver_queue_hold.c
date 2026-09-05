/* AGC phase 0F: hold AgcDriver for external read-only mapping inspection. */
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0f-driver-queue-hold.log"
#define AGC_DRIVER_SYSMODULE_ID 0x80000080u
#define HOLD_SECONDS 25

int sceSysmoduleLoadModuleInternal(unsigned int id);
int sceSysmoduleUnloadModuleInternal(unsigned int id);

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
    int load_rc;
    int unload_rc = -1;
    int result;

    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    alarm(HOLD_SECONDS + 10);
    probe_log("AGC phase 0F start; external read-only mapping inspection; no libAgc, queue call or submit");
    load_rc = sceSysmoduleLoadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
    probe_log("LoadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
              AGC_DRIVER_SYSMODULE_ID, (unsigned)load_rc);
    if (load_rc == 0) {
        probe_log("inspection window ready; hold_seconds=%d", HOLD_SECONDS);
        sleep(HOLD_SECONDS);
        unload_rc = sceSysmoduleUnloadModuleInternal(AGC_DRIVER_SYSMODULE_ID);
        probe_log("UnloadModuleInternal(AgcDriver=0x%08x) rc=0x%08x",
                  AGC_DRIVER_SYSMODULE_ID, (unsigned)unload_rc);
    }
    result = load_rc == 0 && unload_rc == 0 ? 0 : 10;
    alarm(0);
    probe_log("AGC phase 0F exit result=%d; attached=no; writes=0; submitted=no",
              result);
    if (log_fd >= 0)
        close(log_fd);
    return result;
}
