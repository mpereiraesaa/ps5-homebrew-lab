/* AGC phase 0: sysmodule lifecycle only. No VideoOut, commands or submit. */
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0.log"
#define SCE_SYSMODULE_INTERNAL_AGC 0x80000094u

#ifndef PROBE_HOLD_SECONDS
#define PROBE_HOLD_SECONDS 0
#endif

int sceSysmoduleLoadModuleInternal(unsigned int id);
int sceSysmoduleUnloadModuleInternal(unsigned int id);

static int log_fd = -1;
static volatile int finished;

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

static void *watchdog(void *unused)
{
    (void)unused;
    for (int i = 0; i < 100 + PROBE_HOLD_SECONDS * 10 && !finished; ++i)
        usleep(100000);
    if (!finished) {
        probe_log("watchdog timeout during sysmodule lifecycle");
        _exit(124);
    }
    return NULL;
}

int main(void)
{
    pthread_t watchdog_thread;
    int watchdog_started;
    int load_rc;
    int unload_rc = -1;

    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    probe_log("AGC phase 0 start; sysmodule lifecycle only; no submit");
    watchdog_started = pthread_create(&watchdog_thread, NULL, watchdog, NULL) == 0;

    load_rc = sceSysmoduleLoadModuleInternal(SCE_SYSMODULE_INTERNAL_AGC);
    probe_log("LoadModuleInternal(AGC=0x%08x) rc=0x%08x",
              SCE_SYSMODULE_INTERNAL_AGC, (unsigned)load_rc);
    if (load_rc == 0) {
        if (PROBE_HOLD_SECONDS > 0) {
            probe_log("holding loaded module for %d seconds; still no calls or submit",
                      PROBE_HOLD_SECONDS);
            sleep(PROBE_HOLD_SECONDS);
        }
        unload_rc = sceSysmoduleUnloadModuleInternal(SCE_SYSMODULE_INTERNAL_AGC);
        probe_log("UnloadModuleInternal(AGC=0x%08x) rc=0x%08x",
                  SCE_SYSMODULE_INTERNAL_AGC, (unsigned)unload_rc);
    }

    finished = 1;
    if (watchdog_started)
        pthread_join(watchdog_thread, NULL);
    probe_log("AGC phase 0 exit load=0x%08x unload=0x%08x",
              (unsigned)load_rc, (unsigned)unload_rc);
    if (log_fd >= 0)
        close(log_fd);
    return load_rc == 0 && unload_rc == 0 ? 0 : 10;
}
