#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <machine/param.h>
#include <sys/event.h>
#include <sys/mman.h>

#define LOG_PATH "/data/ps5-combined-memory-probe.log"
#define PAGE_SIZE_PS5 0x4000u
#define HEAP_SIZE (320u << 20)
#define JIT_SIZE  (64u << 20)
#define VIDEO_SIZE (128u << 20)
#define WORKERS 8
#define PAD_OPTIONS 0x0008

typedef struct { void *data; uint64_t reserved[3]; } vout_buf_t;
typedef struct { uint32_t res; uint32_t reserved0; uint64_t reserved1[5]; } vout_stat_t;
typedef struct { uint8_t reserved[80]; } vout_attr_t;
typedef struct { uint8_t b, g, r, a; } pixel_t;
typedef struct {
    uint32_t buttons;
    uint8_t sticks_triggers[8];
    float motion[10];
    uint8_t touch[24];
    uint8_t connected;
    uint64_t timestamp;
    uint8_t tail[32];
} pad_data_t;

int sceKernelAllocateMainDirectMemory(size_t, size_t, int, intptr_t *);
int sceKernelMapDirectMemory(void **, size_t, int, int, intptr_t, size_t);
int sceKernelReleaseDirectMemory(intptr_t, size_t);
int sceKernelJitCreateSharedMemory(int, size_t, int, int *);
int sceKernelJitCreateAliasOfSharedMemory(int, int, int *);
int sceSystemServiceGetAppIdOfRunningBigApp(void);
int sceSystemServiceKillApp(int, int, int, int);
int sceSystemServiceHideSplashScreen(void);
int sceKernelCreateEqueue(struct kevent **, const char *);
int sceKernelWaitEqueue(struct kevent *, struct kevent *, int, int *, unsigned int *);
int sceVideoOutOpen(int, int, int, const void *);
int sceVideoOutClose(int);
int sceVideoOutGetOutputStatus(int, vout_stat_t *);
int sceVideoOutAddFlipEvent(struct kevent *, int, void *);
int sceVideoOutSetFlipRate(int, int);
int sceVideoOutSubmitFlip(int, int, unsigned int, int64_t);
void sceVideoOutSetBufferAttribute2(vout_attr_t *, uint64_t, uint32_t, uint32_t,
                                    uint32_t, uint64_t, uint32_t, uint64_t);
int sceVideoOutRegisterBuffers2(int, int, int, vout_buf_t *, int, vout_attr_t *,
                                int, void *);
int sceVideoOutUnregisterBuffers(int, int, int);
int sceUserServiceInitialize(void *);
int sceUserServiceGetForegroundUser(int *);
int scePadInit(void);
int scePadOpen(int, int, int, void *);
int scePadReadState(int, pad_data_t *);
int scePadClose(int);
int sceAudioOutInit(void);
int sceAudioOutOpen(int, int, int, uint32_t, uint32_t, uint32_t);
int sceAudioOutOutput(int, const void *);
int sceAudioOutClose(int);

static int log_fd = -1;
static volatile int workers_running;
static volatile uint64_t worker_checksum;
static int audio_handle = -1;

static void *compute_worker(void *arg) {
    uint64_t x = (uintptr_t)arg | 1u;
    while (workers_running) {
        for (int i = 0; i < 100000; ++i)
            x = x * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
    }
    __atomic_fetch_xor(&worker_checksum, x, __ATOMIC_RELAXED);
    return NULL;
}

static void *audio_worker(void *arg) {
    int16_t pcm[768 * 2];
    uint32_t phase = 0;
    (void)arg;
    while (workers_running) {
        for (int i = 0; i < 768; ++i) {
            int16_t sample = (phase++ % 145u) < 72u ? 1800 : -1800;
            pcm[i * 2] = sample;
            pcm[i * 2 + 1] = sample;
        }
        if (sceAudioOutOutput(audio_handle, pcm)) break;
    }
    return NULL;
}

static void fill_video(pixel_t *frame, int width, int height, uint8_t blue) {
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            pixel_t *p = &frame[(size_t)y * (size_t)width + (size_t)x];
            p->r = (uint8_t)(20 + (x * 80) / width);
            p->g = (uint8_t)(20 + (y * 80) / height);
            p->b = blue;
            p->a = 255;
        }
    }
}

static void probe_log(const char *name, size_t size, int rc, int value) {
    char line[256];
    int n = snprintf(line, sizeof(line),
        "%s mib=%zu rc=0x%08x errno=%d value=%d\n",
        name, size >> 20, rc, errno, value);
    if (n > 0) { write(log_fd, line, (size_t)n); fsync(log_fd); }
}

static void touch_pages(volatile uint8_t *mem, size_t size, uint8_t salt) {
    for (size_t off = 0; off < size; off += PAGE_SIZE_PS5)
        mem[off] = (uint8_t)((off >> 14) ^ salt);
}

static int verify_pages(volatile uint8_t *mem, size_t size, uint8_t salt) {
    for (size_t off = 0; off < size; off += PAGE_SIZE_PS5)
        if (mem[off] != (uint8_t)((off >> 14) ^ salt)) return -1;
    return 0;
}

static void emit_return(void *dst, uint32_t value) {
    uint8_t code[] = {0xb8, 0, 0, 0, 0, 0xc3};
    memcpy(code + 1, &value, sizeof(value));
    memcpy(dst, code, sizeof(code));
}

int main(int argc, char **argv) {
    size_t direct_mib = 3072;
    const char *configured = getenv("PS5_DIRECT_MIB");
    if (configured) direct_mib = (size_t)strtoul(configured, NULL, 0);
    else if (argc > 1) direct_mib = (size_t)strtoul(argv[1], NULL, 0);
    if (direct_mib < 128 || direct_mib > 4096) direct_mib = 3072;
    size_t direct_size = direct_mib << 20;
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);

    volatile uint8_t *heap = MAP_FAILED;
    void *jit_rx = MAP_FAILED, *jit_rw = MAP_FAILED;
    int jit_x = -1, jit_w = -1;
    intptr_t direct_paddr = 0;
    void *direct_vaddr = NULL;
    int direct_allocated = 0;
    intptr_t video_paddr = 0;
    void *video_vaddr = NULL;
    int video_allocated = 0;
    int vout = -1, buffers_registered = 0, pad = -1;
    struct kevent *queue = NULL;
    struct kevent event;
    vout_buf_t buffers[2] = {{0}};
    vout_attr_t attr = {{0}};
    vout_stat_t status = {0};
    pthread_t worker_threads[WORKERS], audio_thread;
    int workers_started = 0, audio_started = 0;

    errno = 0;
    heap = mmap(NULL, HEAP_SIZE, PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    int rc = heap == MAP_FAILED ? -1 : 0;
    if (!rc) touch_pages(heap, HEAP_SIZE, 0x5a);
    probe_log("heap-hold", HEAP_SIZE, rc, -1);
    if (rc) goto done;

    errno = 0;
    rc = sceKernelJitCreateSharedMemory(0, JIT_SIZE,
                                        PROT_READ | PROT_WRITE | PROT_EXEC,
                                        &jit_x);
    probe_log("jit-create", JIT_SIZE, rc, jit_x);
    if (rc) goto done;
    rc = sceKernelJitCreateAliasOfSharedMemory(jit_x,
                                                PROT_READ | PROT_WRITE, &jit_w);
    probe_log("jit-alias", JIT_SIZE, rc, jit_w);
    if (rc) goto done;
    jit_rx = mmap(NULL, JIT_SIZE, PROT_READ | PROT_EXEC, MAP_SHARED, jit_x, 0);
    rc = jit_rx == MAP_FAILED ? -1 : 0;
    probe_log("jit-map-rx", JIT_SIZE, rc, -1);
    if (rc) goto done;
    jit_rw = mmap(NULL, JIT_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, jit_w, 0);
    rc = jit_rw == MAP_FAILED ? -1 : 0;
    probe_log("jit-map-rw", JIT_SIZE, rc, -1);
    if (rc) goto done;
    touch_pages(jit_rw, JIT_SIZE, 0xa5);
    emit_return(jit_rw, 3001);
    __asm__ __volatile__("mfence" ::: "memory");
    int jit_value = ((int (*)(void))jit_rx)();
    probe_log("jit-execute-before-direct", JIT_SIZE, 0, jit_value);
    if (jit_value != 3001) goto done;

    errno = 0;
    rc = sceKernelAllocateMainDirectMemory(direct_size, 0x20000, 3,
                                            &direct_paddr);
    probe_log("direct-allocate", direct_size, rc, -1);
    if (rc) goto done;
    direct_allocated = 1;
    rc = sceKernelMapDirectMemory(&direct_vaddr, direct_size, 0x33, 0,
                                  direct_paddr, 0x20000);
    probe_log("direct-map", direct_size, rc, -1);
    if (rc) goto done;
    touch_pages(direct_vaddr, direct_size, 0x3c);
    rc = verify_pages(direct_vaddr, direct_size, 0x3c);
    probe_log("direct-verify", direct_size, rc, -1);
    if (rc) goto done;

    rc = verify_pages(heap, HEAP_SIZE, 0x5a);
    probe_log("heap-verify-under-load", HEAP_SIZE, rc, -1);
    emit_return(jit_rw, 3002);
    __asm__ __volatile__("mfence" ::: "memory");
    jit_value = ((int (*)(void))jit_rx)();
    probe_log("jit-execute-under-load", JIT_SIZE, 0, jit_value);

    rc = sceKernelAllocateMainDirectMemory(VIDEO_SIZE, 0x20000, 3, &video_paddr);
    probe_log("video-memory-allocate", VIDEO_SIZE, rc, -1);
    if (rc) goto done;
    video_allocated = 1;
    rc = sceKernelMapDirectMemory(&video_vaddr, VIDEO_SIZE, 0x33, 0,
                                  video_paddr, 0x20000);
    probe_log("video-memory-map", VIDEO_SIZE, rc, -1);
    if (rc) goto done;
    sceSystemServiceHideSplashScreen();
    vout = sceVideoOutOpen(0xff, 0, 0, NULL);
    if (vout < 0) { probe_log("video-open", 0, vout, -1); goto done; }
    rc = sceVideoOutGetOutputStatus(vout, &status);
    if (rc) { probe_log("video-status", 0, rc, -1); goto done; }
    int width = status.res == 2 ? 3840 : 1920;
    int height = status.res == 2 ? 2160 : 1080;
    int pitch_width = (width + 63) & ~63;
    int pitch_height = (height + 63) & ~63;
    sceVideoOutSetBufferAttribute2(&attr, UINT64_C(0x8000000022000000), 0,
                                   width, height, 0, 0, 0);
    buffers[0].data = video_vaddr;
    buffers[1].data = (uint8_t *)video_vaddr + VIDEO_SIZE / 2;
    rc = sceVideoOutRegisterBuffers2(vout, 0, 0, buffers, 2, &attr, 0, NULL);
    probe_log("video-register", VIDEO_SIZE, rc, width);
    if (rc) goto done;
    buffers_registered = 1;
    rc = sceKernelCreateEqueue(&queue, "combined soak");
    if (!rc) rc = sceVideoOutAddFlipEvent(queue, vout, NULL);
    if (!rc) rc = sceVideoOutSetFlipRate(vout, 0);
    probe_log("video-events", 0, rc, height);
    if (rc) goto done;
    fill_video(buffers[0].data, pitch_width, pitch_height, 120);
    fill_video(buffers[1].data, pitch_width, pitch_height, 150);

    int user_id = -1;
    sceUserServiceInitialize(NULL);
    sceUserServiceGetForegroundUser(&user_id);
    rc = scePadInit();
    if (!rc) pad = scePadOpen(user_id, 0, 0, NULL);
    probe_log("pad-open", 0, pad < 0 ? pad : 0, pad);

    rc = sceAudioOutInit();
    audio_handle = sceAudioOutOpen(0xff, 0, 0, 768, 48000, 1);
    probe_log("audio-open", 0, audio_handle < 1 ? audio_handle : rc, audio_handle);

    workers_running = 1;
    for (int i = 0; i < WORKERS; ++i) {
        if (pthread_create(&worker_threads[i], NULL, compute_worker,
                           (void *)(uintptr_t)(i + 1))) break;
        ++workers_started;
    }
    if (audio_handle > 0 && !pthread_create(&audio_thread, NULL, audio_worker, NULL))
        audio_started = 1;
    probe_log("workers-started", 0, 0, workers_started);

    rc = 0;
    int completed_seconds = 0;
    for (uint32_t frame = 0; frame < 10800; ++frame) {
        pad_data_t state;
        memset(&state, 0, sizeof(state));
        if (pad > 0 && !scePadReadState(pad, &state) && state.connected &&
            (state.buttons & PAD_OPTIONS)) break;
        int idx = frame & 1;
        rc = sceVideoOutSubmitFlip(vout, idx, 1, frame);
        int out = 0;
        if (!rc) rc = sceKernelWaitEqueue(queue, &event, 1, &out, NULL);
        if (rc) break;
        if (frame % 60 == 0) {
            completed_seconds = (int)(frame / 60);
            size_t direct_off = ((size_t)completed_seconds * 104729u * PAGE_SIZE_PS5) % direct_size;
            size_t heap_off = ((size_t)completed_seconds * 8191u * PAGE_SIZE_PS5) % HEAP_SIZE;
            if (((volatile uint8_t *)direct_vaddr)[direct_off] !=
                (uint8_t)((direct_off >> 14) ^ 0x3c)) { rc = -2; break; }
            if (heap[heap_off] != (uint8_t)((heap_off >> 14) ^ 0x5a)) { rc = -3; break; }
            emit_return(jit_rw, (uint32_t)(4000 + completed_seconds));
            __asm__ __volatile__("mfence" ::: "memory");
            jit_value = ((int (*)(void))jit_rx)();
            if (jit_value != 4000 + completed_seconds) { rc = -4; break; }
        }
    }
    probe_log("multimedia-soak", direct_size + HEAP_SIZE + JIT_SIZE + VIDEO_SIZE,
              rc, completed_seconds);

done:
    workers_running = 0;
    if (audio_started) pthread_join(audio_thread, NULL);
    for (int i = 0; i < workers_started; ++i) pthread_join(worker_threads[i], NULL);
    probe_log("worker-checksum", 0, 0, (int)worker_checksum);
    if (audio_handle > 0) sceAudioOutClose(audio_handle);
    if (pad > 0) scePadClose(pad);
    if (buffers_registered) sceVideoOutUnregisterBuffers(vout, 0, 2);
    if (vout >= 0) sceVideoOutClose(vout);
    if (video_vaddr) munmap(video_vaddr, VIDEO_SIZE);
    if (video_allocated) sceKernelReleaseDirectMemory(video_paddr, VIDEO_SIZE);
    if (direct_vaddr) munmap(direct_vaddr, direct_size);
    if (direct_allocated) sceKernelReleaseDirectMemory(direct_paddr, direct_size);
    if (jit_rw != MAP_FAILED) munmap(jit_rw, JIT_SIZE);
    if (jit_rx != MAP_FAILED) munmap(jit_rx, JIT_SIZE);
    if (jit_w >= 0) close(jit_w);
    if (jit_x >= 0) close(jit_x);
    if (heap != MAP_FAILED) munmap((void *)heap, HEAP_SIZE);
    if (log_fd >= 0) close(log_fd);
    int app_id = sceSystemServiceGetAppIdOfRunningBigApp();
    if (app_id > 0) sceSystemServiceKillApp(app_id, -1, 0, 0);
    return 0;
}
