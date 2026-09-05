#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/resource.h>

#define LOG_PATH "/data/ps5-memory-budget-probe.log"
#define PAGE_SIZE_PS5 0x4000u

size_t sceKernelGetDirectMemorySize(void);
int sceKernelAllocateMainDirectMemory(size_t, size_t, int, intptr_t *);
int sceKernelMapDirectMemory(void **, size_t, int, int, intptr_t, size_t);
int sceKernelReleaseDirectMemory(intptr_t, size_t);
int sceSystemServiceGetAppIdOfRunningBigApp(void);
int sceSystemServiceKillApp(int, int, int, int);

static int log_fd = -1;

static uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

static void log_case(const char *kind, size_t size, int rc, int err,
                     uint64_t elapsed) {
    char line[256];
    int n = snprintf(line, sizeof(line),
        "%s mib=%zu rc=0x%08x errno=%d time_us=%llu\n",
        kind, size >> 20, rc, err, (unsigned long long)elapsed);
    if (n > 0) { write(log_fd, line, (size_t)n); fsync(log_fd); }
}

static void test_heap(size_t size) {
    errno = 0;
    uint64_t start = now_us();
    volatile uint8_t *mem = mmap(NULL, size, PROT_READ | PROT_WRITE,
                                 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    int rc = mem == MAP_FAILED ? -1 : 0;
    int saved_errno = errno;
    if (!rc) {
        for (size_t offset = 0; offset < size; offset += PAGE_SIZE_PS5)
            mem[offset] = (uint8_t)(offset >> 14);
        for (size_t offset = 0; offset < size; offset += PAGE_SIZE_PS5)
            if (mem[offset] != (uint8_t)(offset >> 14)) { rc = -2; break; }
        munmap((void *)mem, size);
    }
    log_case("heap-rw-touch", size, rc, saved_errno, now_us() - start);
}

static void test_direct(size_t size) {
    intptr_t paddr = 0;
    void *vaddr = NULL;
    errno = 0;
    uint64_t start = now_us();
    int rc = sceKernelAllocateMainDirectMemory(size, 0x20000, 3, &paddr);
    int saved_errno = errno;
    if (!rc) {
        rc = sceKernelMapDirectMemory(&vaddr, size, 0x33, 0, paddr, 0x20000);
        saved_errno = errno;
        if (!rc) {
            volatile uint8_t *mem = vaddr;
            for (size_t offset = 0; offset < size; offset += PAGE_SIZE_PS5)
                mem[offset] = (uint8_t)(offset >> 14);
            for (size_t offset = 0; offset < size; offset += PAGE_SIZE_PS5)
                if (mem[offset] != (uint8_t)(offset >> 14)) { rc = -2; break; }
            munmap(vaddr, size);
        }
        sceKernelReleaseDirectMemory(paddr, size);
    }
    log_case("main-direct-touch", size, rc, saved_errno, now_us() - start);
}

int main(void) {
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    struct rlimit data, stack, vmem;
    getrlimit(RLIMIT_DATA, &data);
    getrlimit(RLIMIT_STACK, &stack);
    getrlimit(RLIMIT_VMEM, &vmem);
    char line[320];
    int n = snprintf(line, sizeof(line),
        "direct_total=%zu data_cur=%llu data_max=%llu stack_cur=%llu stack_max=%llu vmem_cur=%llu vmem_max=%llu\n",
        sceKernelGetDirectMemorySize(),
        (unsigned long long)data.rlim_cur, (unsigned long long)data.rlim_max,
        (unsigned long long)stack.rlim_cur, (unsigned long long)stack.rlim_max,
        (unsigned long long)vmem.rlim_cur, (unsigned long long)vmem.rlim_max);
    if (n > 0) { write(log_fd, line, (size_t)n); fsync(log_fd); }

    const size_t heap_sizes[] = {128u << 20, 256u << 20, 320u << 20,
                                 384u << 20, 400u << 20, 416u << 20,
                                 432u << 20, 448u << 20, 512u << 20};
    const size_t direct_sizes[] = {128u << 20, 256u << 20, 512u << 20,
                                   1024u << 20, (size_t)2048u << 20};
    for (size_t i = 0; i < sizeof(heap_sizes) / sizeof(heap_sizes[0]); ++i)
        test_heap(heap_sizes[i]);
    for (size_t i = 0; i < sizeof(direct_sizes) / sizeof(direct_sizes[0]); ++i)
        test_direct(direct_sizes[i]);

    if (log_fd >= 0) close(log_fd);
    int app_id = sceSystemServiceGetAppIdOfRunningBigApp();
    if (app_id > 0) sceSystemServiceKillApp(app_id, -1, 0, 0);
    return 0;
}
