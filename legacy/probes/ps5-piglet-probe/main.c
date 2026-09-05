/*
 * Staged, non-patching GLSlim/Piglet capability probe for PS5.
 * Build produces four independent ELFs; run only one phase at a time.
 */
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#ifndef PROBE_PHASE
#define PROBE_PHASE 1
#endif

#ifndef PROBE_SYSMODULE
#define PROBE_SYSMODULE 0
#endif

#define LOG_PATH "/data/ps5-piglet-probe.log"
#define MODULE_PATH "/system_ex/common_ex/lib/libSceGLSlimVSH.sprx"
#define MODULE_NAME "libSceGLSlimVSH.sprx"
#define GLSLIM_SYSMODULE_ID 0x800000a9u
#define WATCHDOG_SECONDS 12

int sceSysmoduleLoadModuleInternal(unsigned int id);
int sceSysmoduleUnloadModuleInternal(unsigned int id);

typedef int (*piglet_get_config_fn)(void *config);
typedef EGLDisplay (*egl_get_display_fn)(EGLNativeDisplayType);
typedef EGLBoolean (*egl_initialize_fn)(EGLDisplay, EGLint *, EGLint *);
typedef EGLint (*egl_get_error_fn)(void);
typedef EGLBoolean (*egl_terminate_fn)(EGLDisplay);
typedef EGLBoolean (*egl_bind_api_fn)(EGLenum);
typedef EGLBoolean (*egl_choose_config_fn)(EGLDisplay, const EGLint *, EGLConfig *, EGLint, EGLint *);
typedef EGLSurface (*egl_create_window_surface_fn)(EGLDisplay, EGLConfig, EGLNativeWindowType, const EGLint *);
typedef EGLBoolean (*egl_destroy_surface_fn)(EGLDisplay, EGLSurface);
typedef EGLContext (*egl_create_context_fn)(EGLDisplay, EGLConfig, EGLContext, const EGLint *);
typedef EGLBoolean (*egl_destroy_context_fn)(EGLDisplay, EGLContext);
typedef EGLBoolean (*egl_make_current_fn)(EGLDisplay, EGLSurface, EGLSurface, EGLContext);
typedef EGLBoolean (*egl_swap_buffers_fn)(EGLDisplay, EGLSurface);
typedef void (*gl_clear_color_fn)(GLfloat, GLfloat, GLfloat, GLfloat);
typedef void (*gl_clear_fn)(GLbitfield);
typedef GLenum (*gl_get_error_fn)(void);

typedef struct {
    uint32_t type;
    uint32_t width;
    uint32_t height;
} sce_window_candidate_t;

typedef struct {
    void *module;
    int sysmodule_loaded;
    piglet_get_config_fn get_config;
    egl_get_display_fn get_display;
    egl_initialize_fn initialize;
    egl_get_error_fn get_egl_error;
    egl_terminate_fn terminate;
    egl_bind_api_fn bind_api;
    egl_choose_config_fn choose_config;
    egl_create_window_surface_fn create_window_surface;
    egl_destroy_surface_fn destroy_surface;
    egl_create_context_fn create_context;
    egl_destroy_context_fn destroy_context;
    egl_make_current_fn make_current;
    egl_swap_buffers_fn swap_buffers;
    gl_clear_color_fn clear_color;
    gl_clear_fn clear;
    gl_get_error_fn get_gl_error;
} api_t;

static int log_fd = -1;

static void probe_log(const char *fmt, ...) {
    char line[768];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if ((size_t)n >= sizeof(line) - 1) n = (int)sizeof(line) - 2;
    line[n++] = '\n';
    if (log_fd >= 0) {
        (void)write(log_fd, line, (size_t)n);
        (void)fsync(log_fd);
    }
}

static void watchdog(int sig) {
    static const char msg[] = "watchdog timeout; forcing process exit\n";
    (void)sig;
    if (log_fd >= 0) (void)write(log_fd, msg, sizeof(msg) - 1);
    _exit(124);
}

static void *resolve(void *module, const char *name) {
    void *p = dlsym(module, name);
    probe_log("resolve %-38s %s", name, p ? "yes" : "no");
    return p;
}

static int load_api(api_t *a) {
    memset(a, 0, sizeof(*a));
    const char *module = MODULE_PATH;
    if (PROBE_SYSMODULE) {
        int sys_rc = sceSysmoduleLoadModuleInternal(GLSLIM_SYSMODULE_ID);
        probe_log("sceSysmoduleLoadModuleInternal(0x%08x) rc=0x%08x",
                  GLSLIM_SYSMODULE_ID, sys_rc);
        if (sys_rc != 0) return -1;
        a->sysmodule_loaded = 1;
        module = MODULE_NAME;
    }
    a->module = dlopen(module, RTLD_NOW | RTLD_LOCAL);
    probe_log("dlopen %s: %s", module, a->module ? "success" : "failed");
    if (!a->module) {
        const char *error = dlerror();
        probe_log("dlerror: %s", error ? error : "unavailable");
        return -1;
    }
#define RESOLVE(member, symbol) a->member = (void *)resolve(a->module, symbol)
    RESOLVE(get_config, "scePigletGetConfigurationVSH");
    RESOLVE(get_display, "eglGetDisplay");
    RESOLVE(initialize, "eglInitialize");
    RESOLVE(get_egl_error, "eglGetError");
    RESOLVE(terminate, "eglTerminate");
    RESOLVE(bind_api, "eglBindAPI");
    RESOLVE(choose_config, "eglChooseConfig");
    RESOLVE(create_window_surface, "eglCreateWindowSurface");
    RESOLVE(destroy_surface, "eglDestroySurface");
    RESOLVE(create_context, "eglCreateContext");
    RESOLVE(destroy_context, "eglDestroyContext");
    RESOLVE(make_current, "eglMakeCurrent");
    RESOLVE(swap_buffers, "eglSwapBuffers");
    RESOLVE(clear_color, "glClearColor");
    RESOLVE(clear, "glClear");
    RESOLVE(get_gl_error, "glGetError");
#undef RESOLVE
    return 0;
}

static int phase_get_config(api_t *a) {
    /* PS4 used ScePglConfig (~0x60 bytes).  Keep a much larger bounded opaque
     * buffer and advertise its size in word 0; do not call SetConfiguration. */
    union { uint64_t align; uint8_t bytes[0x400]; } config;
    if (!a->get_config) return -1;
    memset(&config, 0xa5, sizeof(config));
    *(uint32_t *)&config.bytes[0] = (uint32_t)sizeof(config.bytes);
    int rc = a->get_config(config.bytes);
    probe_log("GetConfigurationVSH rc=0x%08x advertised_size=0x%x", rc,
              *(uint32_t *)&config.bytes[0]);
    for (unsigned i = 0; i < 0x80; i += 16) {
        probe_log("config+%02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x",
                  i, config.bytes[i], config.bytes[i+1], config.bytes[i+2], config.bytes[i+3],
                  config.bytes[i+4], config.bytes[i+5], config.bytes[i+6], config.bytes[i+7],
                  config.bytes[i+8], config.bytes[i+9], config.bytes[i+10], config.bytes[i+11],
                  config.bytes[i+12], config.bytes[i+13], config.bytes[i+14], config.bytes[i+15]);
    }
    return rc;
}

static int phase_egl_init(api_t *a, EGLDisplay *out_display) {
    EGLint major = 0, minor = 0;
    if (!a->get_display || !a->initialize || !a->get_egl_error) return -1;
    EGLDisplay dpy = a->get_display(EGL_DEFAULT_DISPLAY);
    probe_log("eglGetDisplay=%p error=0x%04x", dpy, a->get_egl_error());
    if (dpy == EGL_NO_DISPLAY) return -1;
    EGLBoolean ok = a->initialize(dpy, &major, &minor);
    probe_log("eglInitialize=%u version=%d.%d error=0x%04x", ok, major, minor,
              a->get_egl_error());
    if (!ok) return -1;
    *out_display = dpy;
    return 0;
}

static int phase_clear_swap(api_t *a, EGLDisplay dpy) {
    const EGLint config_attrs[] = {
        EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
        EGL_NONE
    };
    const EGLint context_attrs[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    sce_window_candidate_t window = { 0, 1920, 1080 };
    EGLConfig config = NULL;
    EGLint count = 0;
    EGLSurface surface = EGL_NO_SURFACE;
    EGLContext context = EGL_NO_CONTEXT;
    int rc = -1;
    if (!a->bind_api || !a->choose_config || !a->create_window_surface ||
        !a->create_context || !a->make_current || !a->clear_color || !a->clear ||
        !a->swap_buffers) return -1;
    if (!a->bind_api(EGL_OPENGL_ES_API)) goto done;
    probe_log("eglBindAPI success");
    if (!a->choose_config(dpy, config_attrs, &config, 1, &count) || count < 1) goto done;
    probe_log("eglChooseConfig count=%d", count);
    surface = a->create_window_surface(dpy, config, (EGLNativeWindowType)&window, NULL);
    probe_log("eglCreateWindowSurface=%p error=0x%04x", surface, a->get_egl_error());
    if (surface == EGL_NO_SURFACE) goto done;
    context = a->create_context(dpy, config, EGL_NO_CONTEXT, context_attrs);
    probe_log("eglCreateContext=%p error=0x%04x", context, a->get_egl_error());
    if (context == EGL_NO_CONTEXT) goto done;
    if (!a->make_current(dpy, surface, surface, context)) goto done;
    a->clear_color(0.08f, 0.25f, 0.65f, 1.0f);
    a->clear(GL_COLOR_BUFFER_BIT);
    probe_log("glClear error=0x%04x", a->get_gl_error ? a->get_gl_error() : 0xffff);
    probe_log("eglSwapBuffers=%u error=0x%04x", a->swap_buffers(dpy, surface),
              a->get_egl_error());
    rc = 0;
done:
    if (a->make_current) (void)a->make_current(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    if (context != EGL_NO_CONTEXT && a->destroy_context) (void)a->destroy_context(dpy, context);
    if (surface != EGL_NO_SURFACE && a->destroy_surface) (void)a->destroy_surface(dpy, surface);
    if (rc) probe_log("phase4 stopped error=0x%04x", a->get_egl_error ? a->get_egl_error() : 0xffff);
    return rc;
}

int main(void) {
    api_t api;
    EGLDisplay display = EGL_NO_DISPLAY;
    int rc = 0;
    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    signal(SIGALRM, watchdog);
    alarm(WATCHDOG_SECONDS);
    probe_log("PS5 GLSlim probe phase %d%s start; no patches, no SetConfiguration",
              PROBE_PHASE, PROBE_SYSMODULE ? "B-sysmodule" : "");
    if (load_api(&api)) { rc = 10; goto done; }
    if (PROBE_PHASE >= 2 && phase_get_config(&api) < 0) { rc = 20; goto done; }
    if (PROBE_PHASE >= 3 && phase_egl_init(&api, &display)) { rc = 30; goto done; }
    if (PROBE_PHASE >= 4 && phase_clear_swap(&api, display)) { rc = 40; goto done; }
done:
    if (display != EGL_NO_DISPLAY && api.terminate) {
        probe_log("eglTerminate=%u", api.terminate(display));
    }
    if (api.module) {
        int close_rc = dlclose(api.module);
        probe_log("dlclose=%d", close_rc);
    }
    if (api.sysmodule_loaded) {
        int unload_rc = sceSysmoduleUnloadModuleInternal(GLSLIM_SYSMODULE_ID);
        probe_log("sceSysmoduleUnloadModuleInternal rc=0x%08x", unload_rc);
    }
    alarm(0);
    probe_log("phase %d exit rc=%d", PROBE_PHASE, rc);
    if (log_fd >= 0) close(log_fd);
    return rc;
}
