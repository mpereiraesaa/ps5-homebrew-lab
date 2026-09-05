#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/mman.h>

#define LOG_PATH "/data/ps5-native-jit-stress-probe.log"
#define CODE_PAGE 0x4000u
#define THREADS 4
#define THREAD_CYCLES 1000

int sceSystemServiceGetAppIdOfRunningBigApp(void);
int sceSystemServiceKillApp(int, int, int, int);

static int log_fd = -1;

static uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

static void probe_log(const char *label, size_t bytes, int rc,
                      uint64_t checks, uint64_t elapsed_us) {
    char line[256];
    int n = snprintf(line, sizeof(line),
                     "%s bytes=%zu rc=%d errno=%d checks=%llu time_us=%llu\n",
                     label, bytes, rc, errno,
                     (unsigned long long)checks,
                     (unsigned long long)elapsed_us);
    if (n > 0) {
        write(log_fd, line, (size_t)n);
        fsync(log_fd);
    }
}

static void emit_return(void *dst, uint32_t value) {
    uint8_t code[] = {0xb8, 0, 0, 0, 0, 0xc3}; /* mov eax, imm32; ret */
    memcpy(code + 1, &value, sizeof(value));
    memcpy(dst, code, sizeof(code));
}

static int test_cache(size_t size, uint64_t *checks) {
    uint8_t *mem = mmap(NULL, size, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mem == MAP_FAILED) return -1;
    size_t pages = size / CODE_PAGE;
    for (size_t i = 0; i < pages; ++i) emit_return(mem + i * CODE_PAGE, (uint32_t)i);
    if (mprotect(mem, size, PROT_READ | PROT_EXEC)) {
        munmap(mem, size);
        return -2;
    }
    int rc = 0;
    for (size_t i = 0; i < pages; ++i) {
        int got = ((int (*)(void))(mem + i * CODE_PAGE))();
        if (got != (int)i) { rc = -3; break; }
        ++*checks;
    }
    munmap(mem, size);
    return rc;
}

typedef struct { int id; int rc; uint64_t checks; } worker_t;
static pthread_mutex_t protect_lock = PTHREAD_MUTEX_INITIALIZER;

static void *worker(void *arg) {
    worker_t *w = arg;
    uint8_t *mem = mmap(NULL, CODE_PAGE, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mem == MAP_FAILED) { w->rc = -1; return NULL; }
    for (int i = 0; i < THREAD_CYCLES; ++i) {
        emit_return(mem, (uint32_t)(w->id * THREAD_CYCLES + i));
        if (mprotect(mem, CODE_PAGE, PROT_READ | PROT_EXEC)) { w->rc = -2; break; }
        int got = ((int (*)(void))mem)();
        if (got != w->id * THREAD_CYCLES + i) { w->rc = -3; break; }
        ++w->checks;
        if (mprotect(mem, CODE_PAGE, PROT_READ | PROT_WRITE)) { w->rc = -4; break; }
    }
    munmap(mem, CODE_PAGE);
    return NULL;
}

static void *serialized_worker(void *arg) {
    worker_t *w = arg;
    uint8_t *mem = mmap(NULL, CODE_PAGE, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mem == MAP_FAILED) { w->rc = -1; return NULL; }
    for (int i = 0; i < THREAD_CYCLES; ++i) {
        emit_return(mem, (uint32_t)(w->id * THREAD_CYCLES + i));
        pthread_mutex_lock(&protect_lock);
        int rc = mprotect(mem, CODE_PAGE, PROT_READ | PROT_EXEC);
        pthread_mutex_unlock(&protect_lock);
        if (rc) { w->rc = -2; break; }
        int got = ((int (*)(void))mem)();
        if (got != w->id * THREAD_CYCLES + i) { w->rc = -3; break; }
        ++w->checks;
        pthread_mutex_lock(&protect_lock);
        rc = mprotect(mem, CODE_PAGE, PROT_READ | PROT_WRITE);
        pthread_mutex_unlock(&protect_lock);
        if (rc) { w->rc = -4; break; }
    }
    munmap(mem, CODE_PAGE);
    return NULL;
}

static void run_thread_test(const char *label, void *(*fn)(void *)) {
    pthread_t tids[THREADS];
    worker_t workers[THREADS];
    memset(workers, 0, sizeof(workers));
    uint64_t start = now_us();
    int created = 0;
    for (int i = 0; i < THREADS; ++i) {
        workers[i].id = i;
        int rc = pthread_create(&tids[i], NULL, fn, &workers[i]);
        if (rc) { workers[i].rc = rc; break; }
        ++created;
    }
    uint64_t checks = 0;
    int thread_rc = 0;
    for (int i = 0; i < created; ++i) {
        pthread_join(tids[i], NULL);
        checks += workers[i].checks;
        if (workers[i].rc && !thread_rc) thread_rc = workers[i].rc;
    }
    errno = 0;
    probe_log(label, THREADS * CODE_PAGE, thread_rc,
              checks, now_us() - start);
}

int main(void) {
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    const size_t sizes[] = {1u << 20, 16u << 20, 64u << 20, 128u << 20};
    for (size_t i = 0; i < sizeof(sizes) / sizeof(sizes[0]); ++i) {
        errno = 0;
        uint64_t checks = 0, start = now_us();
        int rc = test_cache(sizes[i], &checks);
        probe_log("code-cache", sizes[i], rc, checks, now_us() - start);
        if (rc) break;
    }

    run_thread_test("threaded-rw-rx-unsynchronized", worker);
    run_thread_test("threaded-rw-rx-serialized", serialized_worker);

    if (log_fd >= 0) close(log_fd);
    int app_id = sceSystemServiceGetAppIdOfRunningBigApp();
    if (app_id > 0) sceSystemServiceKillApp(app_id, -1, 0, 0);
    return 0;
}
