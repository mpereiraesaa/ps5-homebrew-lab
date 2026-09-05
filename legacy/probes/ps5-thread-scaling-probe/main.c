#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <pthread_np.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/cpuset.h>

#define LOG_PATH "/data/ps5-thread-scaling-probe.log"
#define ITERATIONS 50000000u
#define MAX_THREADS 16

int sceSystemServiceGetAppIdOfRunningBigApp(void);
int sceSystemServiceKillApp(int, int, int, int);

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    int ready;
    int go;
} gate_t;

typedef struct {
    gate_t *gate;
    int affinity_rc;
    uint64_t affinity_mask;
    uint64_t result;
} worker_t;

static uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

static void *worker_main(void *arg) {
    worker_t *w = arg;
    cpuset_t set;
    CPU_ZERO(&set);
    w->affinity_rc = pthread_getaffinity_np(pthread_self(), sizeof(set), &set);
    for (int cpu = 0; cpu < 64; ++cpu)
        if (CPU_ISSET(cpu, &set)) w->affinity_mask |= UINT64_C(1) << cpu;

    pthread_mutex_lock(&w->gate->mutex);
    ++w->gate->ready;
    pthread_cond_broadcast(&w->gate->cond);
    while (!w->gate->go) pthread_cond_wait(&w->gate->cond, &w->gate->mutex);
    pthread_mutex_unlock(&w->gate->mutex);

    uint64_t x = (uintptr_t)w | 1u;
    for (uint32_t i = 0; i < ITERATIONS; ++i)
        x = x * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
    w->result = x;
    return NULL;
}

static void run_case(int fd, int count) {
    gate_t gate = {PTHREAD_MUTEX_INITIALIZER, PTHREAD_COND_INITIALIZER, 0, 0};
    pthread_t tids[MAX_THREADS];
    worker_t workers[MAX_THREADS];
    memset(workers, 0, sizeof(workers));
    int created = 0;
    for (int i = 0; i < count; ++i) {
        workers[i].gate = &gate;
        if (pthread_create(&tids[i], NULL, worker_main, &workers[i])) break;
        ++created;
    }
    pthread_mutex_lock(&gate.mutex);
    while (gate.ready < created) pthread_cond_wait(&gate.cond, &gate.mutex);
    uint64_t start = now_us();
    gate.go = 1;
    pthread_cond_broadcast(&gate.cond);
    pthread_mutex_unlock(&gate.mutex);

    uint64_t checksum = 0, masks = 0;
    int affinity_errors = 0;
    for (int i = 0; i < created; ++i) {
        pthread_join(tids[i], NULL);
        checksum ^= workers[i].result;
        masks |= workers[i].affinity_mask;
        affinity_errors += workers[i].affinity_rc != 0;
    }
    uint64_t elapsed = now_us() - start;
    char line[320];
    int n = snprintf(line, sizeof(line),
        "threads=%d created=%d iterations_each=%u time_us=%llu throughput_mops=%.2f affinity_mask=0x%016llx affinity_errors=%d checksum=0x%016llx\n",
        count, created, ITERATIONS, (unsigned long long)elapsed,
        elapsed ? ((double)created * ITERATIONS) / (double)elapsed : 0.0,
        (unsigned long long)masks, affinity_errors,
        (unsigned long long)checksum);
    if (n > 0) { write(fd, line, (size_t)n); fsync(fd); }
    pthread_cond_destroy(&gate.cond);
    pthread_mutex_destroy(&gate.mutex);
}

int main(void) {
    int fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    char line[256];
    int n = snprintf(line, sizeof(line), "nproc_conf=%ld nproc_online=%ld\n",
                     sysconf(_SC_NPROCESSORS_CONF), sysconf(_SC_NPROCESSORS_ONLN));
    if (n > 0) write(fd, line, (size_t)n);

    uint8_t original[256] __attribute__((aligned(8)));
    uint8_t single[256] __attribute__((aligned(8)));
    uint8_t verified[256] __attribute__((aligned(8)));
    const size_t set_sizes[] = {32, 64, 128, 256};
    size_t working_size = 0;
    uint64_t original_mask = 0;
    for (size_t i = 0; i < sizeof(set_sizes) / sizeof(set_sizes[0]); ++i) {
        memset(original, 0, sizeof(original));
        errno = 0;
        int get_rc = cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1,
                                        set_sizes[i], (cpuset_t *)original);
        memcpy(&original_mask, original, sizeof(original_mask));
        n = snprintf(line, sizeof(line),
            "cpuset_getaffinity bytes=%zu rc=%d errno=%d mask64=0x%016llx\n",
            set_sizes[i], get_rc, errno, (unsigned long long)original_mask);
        if (n > 0) write(fd, line, (size_t)n);
        if (!get_rc) { working_size = set_sizes[i]; break; }
    }

    if (working_size && original_mask) {
        int first_cpu = __builtin_ctzll(original_mask);
        memset(single, 0, sizeof(single));
        single[first_cpu / 8] = (uint8_t)(1u << (first_cpu % 8));
        errno = 0;
        int set_rc = cpuset_setaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1,
                                        working_size, (cpuset_t *)single);
        memset(verified, 0, sizeof(verified));
        int verify_rc = cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1,
                                           working_size, (cpuset_t *)verified);
        uint64_t verify_mask = 0;
        memcpy(&verify_mask, verified, sizeof(verify_mask));
        n = snprintf(line, sizeof(line),
            "cpuset_set_single cpu=%d set_rc=%d verify_rc=%d errno=%d mask=0x%016llx\n",
            first_cpu, set_rc, verify_rc, errno, (unsigned long long)verify_mask);
        if (n > 0) write(fd, line, (size_t)n);
        if (!set_rc) cpuset_setaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1,
                                        working_size, (cpuset_t *)original);
    }
    const int cases[] = {1, 2, 4, 6, 8, 12, 16};
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i)
        run_case(fd, cases[i]);
    if (fd >= 0) close(fd);
    int app_id = sceSystemServiceGetAppIdOfRunningBigApp();
    if (app_id > 0) sceSystemServiceKillApp(app_id, -1, 0, 0);
    return 0;
}
