#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/mman.h>

#define LOG_PATH "/data/ps5-jitshm-probe.log"
#define CACHE_SIZE (16u << 20)
#define PAGE_SIZE_PS5 0x4000u
#define MAX_THREADS 16
#define CYCLES 100000

int sceKernelJitCreateSharedMemory(int, size_t, int, int *);
int sceKernelJitCreateAliasOfSharedMemory(int, int, int *);
int sceSystemServiceGetAppIdOfRunningBigApp(void);
int sceSystemServiceKillApp(int, int, int, int);

static int log_fd = -1;

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    int ready;
    int go;
} gate_t;

typedef struct {
    gate_t *gate;
    uint8_t *rw;
    uint8_t *rx;
    int id;
    int rc;
    uint64_t checks;
} worker_t;

static uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

static void log_line(const char *name, int rc, int handle, void *addr,
                     int value) {
    char line[256];
    int n = snprintf(line, sizeof(line),
        "%s rc=0x%08x errno=%d handle=%d addr=%p value=%d\n",
        name, rc, errno, handle, addr, value);
    if (n > 0) { write(log_fd, line, (size_t)n); fsync(log_fd); }
}

static void emit_return(void *dst, uint32_t value) {
    uint8_t code[] = {0xb8, 0, 0, 0, 0, 0xc3};
    memcpy(code + 1, &value, sizeof(value));
    memcpy(dst, code, sizeof(code));
}

static void *dual_worker(void *arg) {
    worker_t *w = arg;
    uint8_t *writer = w->rw + (size_t)w->id * PAGE_SIZE_PS5;
    uint8_t *runner = w->rx + (size_t)w->id * PAGE_SIZE_PS5;
    pthread_mutex_lock(&w->gate->mutex);
    ++w->gate->ready;
    pthread_cond_broadcast(&w->gate->cond);
    while (!w->gate->go) pthread_cond_wait(&w->gate->cond, &w->gate->mutex);
    pthread_mutex_unlock(&w->gate->mutex);
    for (uint32_t i = 0; i < CYCLES; ++i) {
        uint32_t expected = (uint32_t)w->id * CYCLES + i;
        emit_return(writer, expected);
        __asm__ __volatile__("mfence" ::: "memory");
        int got = ((int (*)(void))runner)();
        if (got != (int)expected) { w->rc = -1; break; }
        ++w->checks;
    }
    return NULL;
}

static void run_dual_case(uint8_t *rw, uint8_t *rx, int count) {
    gate_t gate = {PTHREAD_MUTEX_INITIALIZER, PTHREAD_COND_INITIALIZER, 0, 0};
    pthread_t tids[MAX_THREADS];
    worker_t workers[MAX_THREADS];
    memset(workers, 0, sizeof(workers));
    int created = 0;
    for (int i = 0; i < count; ++i) {
        workers[i].gate = &gate;
        workers[i].rw = rw;
        workers[i].rx = rx;
        workers[i].id = i;
        if (pthread_create(&tids[i], NULL, dual_worker, &workers[i])) break;
        ++created;
    }
    pthread_mutex_lock(&gate.mutex);
    while (gate.ready < created) pthread_cond_wait(&gate.cond, &gate.mutex);
    uint64_t start = now_us();
    gate.go = 1;
    pthread_cond_broadcast(&gate.cond);
    pthread_mutex_unlock(&gate.mutex);
    uint64_t checks = 0;
    int rc = 0;
    for (int i = 0; i < created; ++i) {
        pthread_join(tids[i], NULL);
        checks += workers[i].checks;
        if (workers[i].rc && !rc) rc = workers[i].rc;
    }
    uint64_t elapsed = now_us() - start;
    char line[256];
    int n = snprintf(line, sizeof(line),
        "dual-threaded threads=%d created=%d rc=%d checks=%llu time_us=%llu mcycles_s=%.2f\n",
        count, created, rc, (unsigned long long)checks,
        (unsigned long long)elapsed,
        elapsed ? (double)checks / (double)elapsed : 0.0);
    if (n > 0) { write(log_fd, line, (size_t)n); fsync(log_fd); }
    pthread_cond_destroy(&gate.cond);
    pthread_mutex_destroy(&gate.mutex);
}

int main(void) {
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    int executable_handle = -1, writable_handle = -1;
    void *rx = NULL, *rw = NULL;
    int rc, value = -1;

    errno = 0;
    rc = sceKernelJitCreateSharedMemory(0, CACHE_SIZE,
                                        PROT_READ | PROT_WRITE | PROT_EXEC,
                                        &executable_handle);
    log_line("create", rc, executable_handle, NULL, -1);
    if (rc) goto done;

    errno = 0;
    rc = sceKernelJitCreateAliasOfSharedMemory(executable_handle,
                                                PROT_READ | PROT_WRITE,
                                                &writable_handle);
    log_line("alias", rc, writable_handle, NULL, -1);
    if (rc) goto done;

    errno = 0;
    rx = mmap(NULL, CACHE_SIZE, PROT_READ | PROT_EXEC, MAP_SHARED,
              executable_handle, 0);
    rc = rx == MAP_FAILED ? -1 : 0;
    log_line("mmap-rx", rc, executable_handle, rx, -1);
    if (rc) { rx = NULL; goto done; }

    errno = 0;
    rw = mmap(NULL, CACHE_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED,
              writable_handle, 0);
    rc = rw == MAP_FAILED ? -1 : 0;
    log_line("mmap-rw", rc, writable_handle, rw, -1);
    if (rc) { rw = NULL; goto done; }

    emit_return(rw, 1234);
    __asm__ __volatile__("mfence" ::: "memory");
    value = ((int (*)(void))rx)();
    log_line("execute", 0, -1, rx, value);

    emit_return((uint8_t *)rw + CACHE_SIZE - PAGE_SIZE_PS5, 5678);
    __asm__ __volatile__("mfence" ::: "memory");
    value = ((int (*)(void))((uint8_t *)rx + CACHE_SIZE - PAGE_SIZE_PS5))();
    log_line("execute-last-page", 0, -1,
             (uint8_t *)rx + CACHE_SIZE - PAGE_SIZE_PS5, value);

    const int thread_cases[] = {1, 4, 8, 12, 16};
    for (size_t i = 0; i < sizeof(thread_cases) / sizeof(thread_cases[0]); ++i)
        run_dual_case(rw, rx, thread_cases[i]);

done:
    if (rw) munmap(rw, CACHE_SIZE);
    if (rx) munmap(rx, CACHE_SIZE);
    if (writable_handle >= 0) close(writable_handle);
    if (executable_handle >= 0) close(executable_handle);
    if (log_fd >= 0) close(log_fd);
    int app_id = sceSystemServiceGetAppIdOfRunningBigApp();
    if (app_id > 0) sceSystemServiceKillApp(app_id, -1, 0, 0);
    return 0;
}
