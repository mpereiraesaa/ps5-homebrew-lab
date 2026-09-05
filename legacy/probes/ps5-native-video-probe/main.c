/*
 * PS5 native VideoOut smoke test.
 * Display setup follows john-tornblom/ps5-payload-hbldr test.c (GPL-3.0).
 */
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <machine/param.h>
#include <sys/event.h>
#include <sys/mman.h>

#define LOG_PATH "/data/ps5-native-video-probe.log"

typedef struct { void *data; uint64_t reserved[3]; } vout_buf_t;
typedef struct { uint32_t res; uint32_t reserved0; uint64_t reserved1[5]; } vout_stat_t;
typedef struct { uint8_t reserved[80]; } vout_attr_t;
typedef struct { uint8_t r, g, b, a; } pixel_t;

#define PAD_OPTIONS 0x0008
#define PAD_CROSS   0x4000

typedef struct {
    uint16_t x, y;
    uint8_t finger;
    uint8_t pad[3];
} pad_touch_t;

typedef struct {
    uint8_t fingers;
    uint8_t pad1[3];
    uint32_t pad2;
    pad_touch_t touch[2];
} pad_touch_data_t;

typedef struct {
    uint32_t buttons;
    struct { uint8_t x, y; } left_stick;
    struct { uint8_t x, y; } right_stick;
    struct { uint8_t l2, r2; } triggers;
    uint16_t padding;
    float quat[4];
    float velocity[3];
    float acceleration[3];
    pad_touch_data_t touch;
    uint8_t connected;
    uint64_t timestamp;
    uint8_t ext[16];
    uint8_t count;
    uint8_t unknown[15];
} pad_data_t;

int sceKernelAllocateMainDirectMemory(size_t, size_t, int, intptr_t *);
int sceKernelAllocateDirectMemory(intptr_t, intptr_t, size_t, size_t, int,
                                  intptr_t *);
int sceKernelMapDirectMemory(void **, size_t, int, int, intptr_t, size_t);
int sceKernelReleaseDirectMemory(intptr_t, size_t);
int sceKernelCreateEqueue(struct kevent **, const char *);
int sceKernelDeleteEqueue(struct kevent *);
int sceKernelWaitEqueue(struct kevent *, struct kevent *, int, int *, unsigned int *);
int sceVideoOutOpen(int, int, int, const void *);
int sceVideoOutClose(int);
int sceVideoOutGetOutputStatus(int, vout_stat_t *);
int sceVideoOutAddFlipEvent(struct kevent *, int, void *);
int sceVideoOutDeleteFlipEvent(struct kevent *, int);
int sceVideoOutSetFlipRate(int, int);
int sceVideoOutSubmitFlip(int, int, unsigned int, int64_t);
void sceVideoOutSetBufferAttribute2(vout_attr_t *, uint64_t, uint32_t, uint32_t,
                                    uint32_t, uint64_t, uint32_t, uint64_t);
int sceVideoOutRegisterBuffers2(int, int, int, vout_buf_t *, int, vout_attr_t *,
                                int, void *);
int sceVideoOutUnregisterBuffers(int, int, int);
int sceSystemServiceHideSplashScreen(void);
int sceSystemServiceGetAppIdOfRunningBigApp(void);
int sceSystemServiceKillApp(int, int, int, int);
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
static volatile int audio_running;
static volatile int audio_high_tone;
static int audio_handle = -1;

static void *audio_thread(void *unused) {
    enum { SAMPLES = 768 };
    int16_t pcm[SAMPLES * 2];
    double phase = 0.0;
    (void)unused;
    while (audio_running) {
        double hz = audio_high_tone ? 660.0 : 330.0;
        double step = 6.283185307179586 * hz / 48000.0;
        for (int i = 0; i < SAMPLES; ++i) {
            int16_t sample = (int16_t)(sinf((float)phase) * 3500.0f);
            pcm[i * 2] = sample;
            pcm[i * 2 + 1] = sample;
            phase += step;
            if (phase >= 6.283185307179586) phase -= 6.283185307179586;
        }
        if (sceAudioOutOutput(audio_handle, pcm)) break;
    }
    return NULL;
}

static void probe_log(const char *fmt, ...) {
    char line[512];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if ((size_t)n >= sizeof(line) - 1) n = (int)sizeof(line) - 2;
    line[n++] = '\n';
    if (log_fd >= 0) { write(log_fd, line, (size_t)n); fsync(log_fd); }
    char kline[600];
    int kn = snprintf(kline, sizeof(kline), "<118>[native-video-probe] %.*s", n, line);
    if (kn > 0) syscall(0x259, 7, kline, 0);
}

static void fill_frame(uint32_t frame_id, pixel_t *frame, int width, int height,
                       int square_x, int square_y, int pressed) {
    float phase = fmodf((float)frame_id / 180.0f, 1.0f);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            pixel_t p;
            p.r = (uint8_t)((x * 255) / width);
            p.g = (uint8_t)((y * 255) / height);
            p.b = (uint8_t)(127.0f + 127.0f * sinf(phase * 6.2831853f));
            p.a = 255;
            frame[(size_t)y * (size_t)width + (size_t)x] = p;
        }
    }
    int side = height / 7;
    for (int y = square_y; y < square_y + side && y < height; ++y) {
        if (y < 0) continue;
        for (int x = square_x; x < square_x + side && x < width; ++x) {
            if (x < 0) continue;
            pixel_t *p = &frame[(size_t)y * (size_t)width + (size_t)x];
            p->r = pressed ? 255 : 30;
            p->g = pressed ? 210 : 255;
            p->b = pressed ? 30 : 255;
            p->a = 255;
        }
    }
}

int main(void) {
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    probe_log("start");

    /* Two 4K BGRA buffers need about 64 MiB; leave ample alignment headroom. */
    const size_t memsize = 0x08000000;
    const size_t memalign = 0x20000;
    intptr_t paddr = 0;
    void *vaddr = NULL;
    int direct_mapped = 0;
    int vout = -1;
    struct kevent *queue = NULL;
    int flip_event_added = 0;
    int buffers_registered = 0;
    struct kevent event;
    vout_buf_t buffers[2];
    vout_attr_t attr;
    vout_stat_t status;
    int pad = -1;
    int user_id = -1;
    pthread_t audio_tid;
    int audio_started = 0;
    int exit_requested = 0;
    memset(buffers, 0, sizeof(buffers));
    memset(&attr, 0, sizeof(attr));
    memset(&status, 0, sizeof(status));

    int rc = sceSystemServiceHideSplashScreen();
    probe_log("HideSplashScreen rc=0x%08x", rc);
    rc = sceKernelAllocateMainDirectMemory(memsize, memalign, 3, &paddr);
    probe_log("AllocateMainDirectMemory rc=0x%08x paddr=%p", rc, (void *)paddr);
    if (rc) {
        /* The zero-conf host used by elfldr may have no "Main" dmem pool.
         * Try the general physical allocator over the PS5's normal 4.5 GiB
         * direct-memory aperture before concluding the process has no budget. */
        paddr = 0;
        rc = sceKernelAllocateDirectMemory(0, 0x120000000LL, memsize,
                                           memalign, 3, &paddr);
        probe_log("AllocateDirectMemory rc=0x%08x paddr=%p", rc,
                  (void *)paddr);
        if (rc) goto done;
    }
    rc = sceKernelMapDirectMemory(&vaddr, memsize, 0x33, 0, paddr, memalign);
    probe_log("MapDirectMemory rc=0x%08x vaddr=%p", rc, vaddr);
    if (rc) goto done;
    direct_mapped = 1;
    vout = sceVideoOutOpen(0xff, 0, 0, NULL);
    probe_log("VideoOutOpen handle=0x%08x", vout);
    if (vout < 0) goto done;
    rc = sceVideoOutGetOutputStatus(vout, &status);
    probe_log("GetOutputStatus rc=0x%08x res=%u", rc, status.res);
    if (rc) goto done;
    rc = sceKernelCreateEqueue(&queue, "native video probe");
    probe_log("CreateEqueue rc=0x%08x queue=%p", rc, (void *)queue);
    if (rc) goto done;
    rc = sceVideoOutAddFlipEvent(queue, vout, NULL);
    probe_log("AddFlipEvent rc=0x%08x", rc);
    if (rc) goto done;
    flip_event_added = 1;

    int width = status.res == 2 ? 3840 : 1920;
    int height = status.res == 2 ? 2160 : 1080;
    int pitch_width = (width + 0x3f) & ~0x3f;
    int pitch_height = (height + 0x3f) & ~0x3f;
    sceVideoOutSetBufferAttribute2(&attr, 0x8000000022000000ULL, 0,
                                   (uint32_t)width, (uint32_t)height, 0, 0, 0);
    buffers[0].data = vaddr;
    buffers[1].data = (uint8_t *)vaddr + memsize / 2;
    rc = sceVideoOutRegisterBuffers2(vout, 0, 0, buffers, 2, &attr, 0, NULL);
    probe_log("RegisterBuffers2 rc=0x%08x size=%dx%d pitch=%dx%d", rc,
              width, height, pitch_width, pitch_height);
    if (rc) goto done;
    buffers_registered = 1;
    rc = sceVideoOutSetFlipRate(vout, 0);
    probe_log("SetFlipRate rc=0x%08x", rc);
    if (rc) goto done;

    rc = sceUserServiceInitialize(NULL);
    probe_log("UserServiceInitialize rc=0x%08x", rc);
    rc = sceUserServiceGetForegroundUser(&user_id);
    probe_log("GetForegroundUser rc=0x%08x user=0x%08x", rc, user_id);
    rc = scePadInit();
    probe_log("PadInit rc=0x%08x", rc);
    if (!rc && user_id != -1) pad = scePadOpen(user_id, 0, 0, NULL);
    probe_log("PadOpen handle=0x%08x", pad);

    rc = sceAudioOutInit();
    probe_log("AudioOutInit rc=0x%08x", rc);
    audio_handle = sceAudioOutOpen(0xff, 0, 0, 768, 48000, 1);
    probe_log("AudioOutOpen handle=0x%08x", audio_handle);
    if (audio_handle > 0) {
        audio_running = 1;
        rc = pthread_create(&audio_tid, NULL, audio_thread, NULL);
        probe_log("audio pthread_create rc=0x%08x", rc);
        audio_started = rc == 0;
        if (rc) audio_running = 0;
    }

    int square_x = width / 2 - height / 14;
    int square_y = height / 2 - height / 14;
    uint32_t previous_buttons = 0;
    /* Five-minute safety ceiling; OPTIONS exits immediately. */
    for (uint32_t frame_id = 0; frame_id < 18000; ++frame_id) {
        pad_data_t state;
        memset(&state, 0, sizeof(state));
        if (pad > 0 && scePadReadState(pad, &state) == 0 && state.connected) {
            int dx = (int)state.left_stick.x - 128;
            int dy = (int)state.left_stick.y - 128;
            if (dx > -12 && dx < 12) dx = 0;
            if (dy > -12 && dy < 12) dy = 0;
            square_x += dx / 8;
            square_y += dy / 8;
            int side = height / 7;
            if (square_x < 0) square_x = 0;
            if (square_y < 0) square_y = 0;
            if (square_x > pitch_width - side) square_x = pitch_width - side;
            if (square_y > pitch_height - side) square_y = pitch_height - side;
            audio_high_tone = (state.buttons & PAD_CROSS) != 0;
            if ((state.buttons & PAD_OPTIONS) && !(previous_buttons & PAD_OPTIONS)) {
                probe_log("OPTIONS pressed; exiting");
                exit_requested = 1;
                break;
            }
            previous_buttons = state.buttons;
        }
        int idx = (int)(frame_id & 1);
        fill_frame(frame_id, (pixel_t *)buffers[idx].data, pitch_width,
                   pitch_height, square_x, square_y, audio_high_tone);
        rc = sceVideoOutSubmitFlip(vout, idx, 1, frame_id);
        if (rc) { probe_log("SubmitFlip frame=%u rc=0x%08x", frame_id, rc); break; }
        int out = 0;
        rc = sceKernelWaitEqueue(queue, &event, 1, &out, NULL);
        if (rc) { probe_log("WaitEqueue frame=%u rc=0x%08x", frame_id, rc); break; }
        if (frame_id == 0) probe_log("first frame presented");
    }
    probe_log("render loop complete");
    if (audio_started) {
        audio_running = 0;
        pthread_join(audio_tid, NULL);
    }
    if (audio_handle > 0) sceAudioOutClose(audio_handle);
    if (pad > 0) scePadClose(pad);
done:
    if (buffers_registered) {
        rc = sceVideoOutUnregisterBuffers(vout, 0, 2);
        probe_log("UnregisterBuffers rc=0x%08x", rc);
    }
    if (flip_event_added) {
        rc = sceVideoOutDeleteFlipEvent(queue, vout);
        probe_log("DeleteFlipEvent rc=0x%08x", rc);
    }
    if (queue) {
        rc = sceKernelDeleteEqueue(queue);
        probe_log("DeleteEqueue rc=0x%08x", rc);
    }
    if (vout >= 0) sceVideoOutClose(vout);
    if (direct_mapped) munmap(vaddr, memsize);
    if (paddr) sceKernelReleaseDirectMemory(paddr, memsize);
    probe_log("done");
    if (log_fd >= 0) close(log_fd);
    if (exit_requested) {
        int app_id = sceSystemServiceGetAppIdOfRunningBigApp();
        if (app_id > 0) sceSystemServiceKillApp(app_id, -1, 0, 0);
    }
    return 0;
}
