/* AGC phase 0O: fixed-VA game-like direct mapping; no AGC and no submit. */
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0o-fixed-mapping.log"
#define REGION_SIZE ((size_t)0x20000)
#define REGION_ALIGN ((size_t)0x10000)

int sceKernelReserveVirtualRange(void **, size_t, int, size_t);
int sceKernelAllocateMainDirectMemory(size_t, size_t, int, intptr_t *);
int sceKernelMapDirectMemory(void **, size_t, int, int, intptr_t, size_t);
int sceKernelReleaseDirectMemory(intptr_t, size_t);

static int log_fd = -1;

static void logf_line(const char *format, ...)
{
    char line[384];
    __builtin_va_list ap;
    __builtin_va_start(ap, format);
    int n = vsnprintf(line, sizeof(line), format, ap);
    __builtin_va_end(ap);
    if (n < 0) return;
    if ((size_t)n >= sizeof(line) - 1) n = (int)sizeof(line) - 2;
    line[n++] = '\n';
    if (log_fd >= 0) { (void)write(log_fd, line, (size_t)n); (void)fsync(log_fd); }
    (void)write(STDOUT_FILENO, line, (size_t)n);
}

static void stop_signal(int signal_number)
{
    static const char message[] =
        "phase0O interrupted; no AGC loaded; submitted=no\n";
    (void)signal_number;
    if (log_fd >= 0) (void)write(log_fd, message, sizeof(message) - 1);
    _exit(124);
}

int main(void)
{
    void *reserved = NULL;
    void *mapping = NULL;
    intptr_t physical = 0;
    int reserved_ok = 0, allocated = 0, mapped = 0, canaries = 0;
    int result = 10;
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, stop_signal);
    (void)signal(SIGSEGV, stop_signal);
    (void)signal(SIGBUS, stop_signal);
    alarm(10);
    logf_line("AGC phase 0O start; fixed-VA memory policy only; no AGC, queue or submit");

    int reserve_rc = sceKernelReserveVirtualRange(
        &reserved, REGION_SIZE, 0, REGION_ALIGN);
    logf_line("ReserveVirtualRange size=0x%zx flags=0 align=0x%zx rc=0x%08x nonnull=%s",
              REGION_SIZE, REGION_ALIGN, (unsigned)reserve_rc,
              reserved ? "yes" : "no");
    if (reserve_rc != 0 || reserved == NULL) { result = 11; goto cleanup; }
    reserved_ok = 1;

    int alloc_rc = sceKernelAllocateMainDirectMemory(
        REGION_SIZE, REGION_ALIGN, 0x0c, &physical);
    logf_line("AllocateMainDirectMemory size=0x%zx align=0x%zx type=0xc rc=0x%08x",
              REGION_SIZE, REGION_ALIGN, (unsigned)alloc_rc);
    if (alloc_rc != 0) { result = 12; goto cleanup; }
    allocated = 1;

    mapping = reserved;
    int map_rc = sceKernelMapDirectMemory(
        &mapping, REGION_SIZE, 0x0f2, 0x10, physical, 0);
    logf_line("MapDirectMemory prot=0xf2 flags=0x10 align=0 rc=0x%08x same_va=%s",
              (unsigned)map_rc, mapping == reserved ? "yes" : "no");
    if (map_rc != 0 || mapping != reserved) { result = 13; goto cleanup; }
    mapped = 1;

    volatile uint64_t *first = (volatile uint64_t *)mapping;
    volatile uint64_t *last = (volatile uint64_t *)
        ((uint8_t *)mapping + REGION_SIZE - sizeof(uint64_t));
    *first = UINT64_C(0x0123456789abcdef);
    *last = UINT64_C(0xfedcba9876543210);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    canaries = (*first == UINT64_C(0x0123456789abcdef) &&
                *last == UINT64_C(0xfedcba9876543210));
    logf_line("cpu_write_read_canaries=%s", canaries ? "yes" : "no");
    result = canaries ? 0 : 14;

cleanup:
    {
        void *va = mapped ? mapping : reserved;
        int unmap_rc = reserved_ok ? munmap(va, REGION_SIZE) : 0;
        int release_rc = allocated ?
            sceKernelReleaseDirectMemory(physical, REGION_SIZE) : 0;
        logf_line("cleanup unmap_rc=0x%08x release_rc=0x%08x complete=yes",
                  (unsigned)unmap_rc, (unsigned)release_rc);
        if (unmap_rc != 0 || release_rc != 0) result = 15;
    }
    alarm(0);
    logf_line("AGC phase 0O exit result=%d submitted=no", result);
    if (log_fd >= 0) close(log_fd);
    return result;
}
