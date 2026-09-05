/* AGC phase 0N: compare small direct-memory policies; no AGC and no submit. */
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0n-memory-policy.log"
#define REGION_SIZE ((size_t)0x20000)

int sceKernelAllocateMainDirectMemory(size_t, size_t, int, intptr_t *);
int sceKernelMapDirectMemory(void **, size_t, int, int, intptr_t, size_t);
int sceKernelReleaseDirectMemory(intptr_t, size_t);

struct mapping_case {
    const char *name;
    size_t allocation_alignment;
    int memory_type;
    int protection;
    int flags;
    size_t mapping_alignment;
};

static int log_fd = -1;

static void log_line(const char *text)
{
    size_t length = strlen(text);
    if (log_fd >= 0) {
        (void)write(log_fd, text, length);
        (void)write(log_fd, "\n", 1);
        (void)fsync(log_fd);
    }
    (void)write(STDOUT_FILENO, text, length);
    (void)write(STDOUT_FILENO, "\n", 1);
}

static void stop_signal(int signal_number)
{
    static const char message[] =
        "phase0N interrupted before completion; no AGC loaded; submitted=no\n";
    (void)signal_number;
    if (log_fd >= 0)
        (void)write(log_fd, message, sizeof(message) - 1);
    _exit(124);
}

static int run_case(const struct mapping_case *cfg)
{
    char line[320];
    intptr_t physical = 0;
    void *mapping = NULL;
    int allocated = 0;
    int mapped = 0;
    int verified = 0;

    int alloc_rc = sceKernelAllocateMainDirectMemory(
        REGION_SIZE, cfg->allocation_alignment, cfg->memory_type, &physical);
    (void)snprintf(line, sizeof(line),
        "case=%s allocate size=0x%zx align=0x%zx type=0x%x rc=0x%08x",
        cfg->name, REGION_SIZE, cfg->allocation_alignment, cfg->memory_type,
        (unsigned)alloc_rc);
    log_line(line);
    if (alloc_rc != 0)
        goto done;
    allocated = 1;

    int map_rc = sceKernelMapDirectMemory(
        &mapping, REGION_SIZE, cfg->protection, cfg->flags, physical,
        cfg->mapping_alignment);
    (void)snprintf(line, sizeof(line),
        "case=%s map prot=0x%x flags=0x%x align=0x%zx rc=0x%08x nonnull=%s",
        cfg->name, cfg->protection, cfg->flags, cfg->mapping_alignment,
        (unsigned)map_rc, mapping ? "yes" : "no");
    log_line(line);
    if (map_rc != 0 || mapping == NULL)
        goto done;
    mapped = 1;

    volatile uint64_t *first = (volatile uint64_t *)mapping;
    volatile uint64_t *last = (volatile uint64_t *)
        ((uint8_t *)mapping + REGION_SIZE - sizeof(uint64_t));
    *first = UINT64_C(0x0123456789abcdef);
    *last = UINT64_C(0xfedcba9876543210);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    verified = (*first == UINT64_C(0x0123456789abcdef) &&
                *last == UINT64_C(0xfedcba9876543210));
    (void)snprintf(line, sizeof(line),
        "case=%s cpu_write_read_canaries=%s", cfg->name,
        verified ? "yes" : "no");
    log_line(line);

done:
    {
        int unmap_rc = mapped ? munmap(mapping, REGION_SIZE) : 0;
        int release_rc = allocated ?
            sceKernelReleaseDirectMemory(physical, REGION_SIZE) : 0;
        (void)snprintf(line, sizeof(line),
            "case=%s cleanup unmap_rc=0x%08x release_rc=0x%08x complete=yes",
            cfg->name, (unsigned)unmap_rc, (unsigned)release_rc);
        log_line(line);
        return alloc_rc == 0 && mapped && verified &&
               unmap_rc == 0 && release_rc == 0;
    }
}

int main(void)
{
    static const struct mapping_case cases[] = {
        {"homebrew_known", 0x20000, 3, 0x33, 0, 0x20000},
        {"game_backbuffer_like", 0x10000, 0x0c, 0x0f2, 0x10, 0},
    };
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, stop_signal);
    (void)signal(SIGSEGV, stop_signal);
    (void)signal(SIGBUS, stop_signal);
    alarm(10);
    log_line("AGC phase 0N start; direct-memory mapping policy only; no AGC, queue or submit");
    int passed = 0;
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i)
        passed += run_case(&cases[i]);
    alarm(0);
    char line[160];
    (void)snprintf(line, sizeof(line),
        "AGC phase 0N exit completed_cases=2 passed_cases=%d submitted=no", passed);
    log_line(line);
    if (log_fd >= 0)
        close(log_fd);
    return passed == 2 ? 0 : 1;
}
