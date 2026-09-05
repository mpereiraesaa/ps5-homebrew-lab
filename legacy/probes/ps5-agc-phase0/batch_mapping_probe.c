/* Phase 0Q draft: mapping-only BatchMap 0xcf2 acceptance; no AGC or submit. */
#include "stage_a_batch_mapping.h"

#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0q-batch-mapping.log"

int sceKernelReserveVirtualRange(void **, size_t, int, size_t);
int sceKernelAllocateMainDirectMemory(size_t, size_t, int, int64_t *);
int sceKernelBatchMap(struct stage_a_batch_entry *, int, int *);
int sceKernelReleaseDirectMemory(int64_t, size_t);

static int log_fd = -1;

static void log_line(const char *format, ...)
{
    char line[384];
    va_list ap;
    va_start(ap, format);
    int n = vsnprintf(line, sizeof(line), format, ap);
    va_end(ap);
    if (n < 0) return;
    if ((size_t)n >= sizeof(line) - 1) n = (int)sizeof(line) - 2;
    line[n++] = '\n';
    if (log_fd >= 0) { (void)write(log_fd, line, (size_t)n); (void)fsync(log_fd); }
    (void)write(STDOUT_FILENO, line, (size_t)n);
}

static void park(const char *reason)
{
    log_line("PARKED_PHASE0Q reason=%s; no AGC or submit; retain mapping state", reason);
    alarm(0);
    for (;;) (void)pause();
}

static void watchdog(int signal_number)
{
    static const char message[] =
        "PARKED_PHASE0Q watchdog; no AGC or submit; mapping state unknown\n";
    (void)signal_number;
    if (log_fd >= 0) { (void)write(log_fd, message, sizeof(message) - 1); (void)fsync(log_fd); }
    for (;;) (void)pause();
}

static int reserve_cb(void **p, size_t n, int flags, size_t alignment)
{ return sceKernelReserveVirtualRange(p, n, flags, alignment); }
static int allocate_cb(size_t n, size_t alignment, int type, int64_t *physical)
{ return sceKernelAllocateMainDirectMemory(n, alignment, type, physical); }
static int batch_cb(struct stage_a_batch_entry *e, int n, int *processed)
{ return sceKernelBatchMap(e, n, processed); }
static int release_va_cb(void *p, size_t n) { return munmap(p, n); }
static int release_physical_cb(int64_t physical, size_t n)
{ return sceKernelReleaseDirectMemory(physical, n); }

int main(void)
{
    static const struct stage_a_batch_api api = {
        reserve_cb, allocate_cb, batch_cb, release_va_cb, release_physical_cb
    };
    struct stage_a_batch_mapping mapping;
    memset(&mapping, 0, sizeof(mapping));
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    (void)signal(SIGSEGV, watchdog);
    (void)signal(SIGBUS, watchdog);
    alarm(10);
    log_line("phase0Q start; type=0x0c BatchMap prot=0xcf2; no AGC, queue or submit");
    int open_rc = stage_a_batch_open(&mapping, &api);
    log_line("open rc=%d state=%d va=%p", open_rc, (int)mapping.state,
             mapping.virtual_address);
    if (mapping.state == STAGE_A_BATCH_RETAIN_UNKNOWN)
        park("ambiguous map result");
    if (open_rc != 0) {
        int close_rc = stage_a_batch_close(&mapping, &api);
        log_line("definite map failure cleanup rc=%d state=%d", close_rc,
                 (int)mapping.state);
        if (close_rc != 0) park("cleanup after definite map failure failed");
        alarm(0);
        log_line("phase0Q exit result=%d submitted=no", open_rc);
        return open_rc;
    }

    volatile uint64_t *first = (volatile uint64_t *)mapping.virtual_address;
    volatile uint64_t *last = (volatile uint64_t *)
        ((uint8_t *)mapping.virtual_address + STAGE_A_BATCH_REGION_SIZE - 8);
    *first = UINT64_C(0x0123456789abcdef);
    *last = UINT64_C(0xfedcba9876543210);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    int canaries = (*first == UINT64_C(0x0123456789abcdef) &&
                    *last == UINT64_C(0xfedcba9876543210));
    log_line("cpu_canaries=%s", canaries ? "yes" : "no");
    int close_rc = stage_a_batch_close(&mapping, &api);
    log_line("close rc=%d state=%d", close_rc, (int)mapping.state);
    if (close_rc != 0) park("ambiguous or failed unmap/release");
    alarm(0);
    int result = canaries ? 0 : 20;
    log_line("phase0Q exit result=%d submitted=no", result);
    if (log_fd >= 0) close(log_fd);
    return result;
}
