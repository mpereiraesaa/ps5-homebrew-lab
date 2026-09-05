#include <sys/types.h>
#include <sys/sysctl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifndef ACTION_LAUNCH
#define ACTION_LAUNCH 0
#endif

#ifndef ACTION_STATUS
#define ACTION_STATUS 0
#endif

#ifndef TARGET_TITLE
#error TARGET_TITLE must be defined
#endif

typedef struct {
    uint32_t structsize;
    uint32_t user_id;
    uint32_t app_opt;
    uint32_t padding;
    uint64_t crash_report;
    uint32_t check_flag;
    uint32_t tail_padding;
} app_launch_ctx_t;

_Static_assert(sizeof(app_launch_ctx_t) == 0x20,
               "unexpected app launch context ABI");
_Static_assert(__builtin_offsetof(app_launch_ctx_t, user_id) == 4,
               "unexpected user-id field offset");

typedef struct {
    uint32_t app_id;
    uint64_t unknown1;
    char title_id[14];
    char unknown2[0x3c];
} app_info_t;

int sceKernelGetAppInfo(pid_t pid, app_info_t *info);
int sceSystemServiceGetAppIdOfRunningBigApp(void);
int sceSystemServiceKillApp(int app_id, int how, int reason, int core_dump);
int sceSystemServiceLaunchApp(const char *title_id, char **argv,
                              app_launch_ctx_t *ctx);
int sceUserServiceInitialize(void *params);
int sceUserServiceGetForegroundUser(uint32_t *user_id);
int sceUserServiceTerminate(void);

static int get_running_title(int wanted_app_id, char *out, size_t out_size)
{
    int mib[4] = {CTL_KERN, KERN_PROC, KERN_PROC_PROC, 0};
    size_t size = 0;
    uint8_t *buf;
    int rc = -1;

    if (out_size < sizeof(((app_info_t *)0)->title_id) + 1)
        return -1;
    out[0] = '\0';
    if (sysctl(mib, 4, NULL, &size, NULL, 0) != 0 || size == 0)
        return -1;
    buf = malloc(size);
    if (!buf)
        return -1;
    if (sysctl(mib, 4, buf, &size, NULL, 0) != 0) {
        free(buf);
        return -1;
    }

    for (uint8_t *p = buf; p < buf + size;) {
        int entry_size = *(int *)p;
        pid_t pid;
        app_info_t info;
        if (entry_size <= 0 || p + entry_size > buf + size)
            break;
        pid = *(pid_t *)&p[72];
        p += entry_size;
        memset(&info, 0, sizeof(info));
        if (sceKernelGetAppInfo(pid, &info) == 0 &&
            info.app_id == (uint32_t)wanted_app_id && info.title_id[0]) {
            size_t n = strnlen(info.title_id, sizeof(info.title_id));
            memcpy(out, info.title_id, n);
            out[n] = '\0';
            rc = 0;
            break;
        }
    }
    free(buf);
    return rc;
}

int main(void)
{
    int app_id = sceSystemServiceGetAppIdOfRunningBigApp();
    char running[16] = {0};
    int identify_rc = app_id > 0 ? get_running_title(app_id, running,
                                                      sizeof(running)) : -1;

    printf("bigapp-control action=%s target=%s app_id=%d identify_rc=%d running=%s\n",
           ACTION_STATUS ? "status" : (ACTION_LAUNCH ? "launch" : "close"),
           TARGET_TITLE, app_id,
           identify_rc, running[0] ? running : "none");

#if ACTION_STATUS
    return 0;
#elif ACTION_LAUNCH
    if (identify_rc == 0 && strcmp(running, TARGET_TITLE) == 0) {
        printf("refusing to relaunch already-running target\n");
        return 20;
    }
    if (app_id > 0) {
        printf("refusing to replace a running BigApp\n");
        return 21;
    }
    app_launch_ctx_t ctx;
    uint32_t user_id = UINT32_MAX;
    memset(&ctx, 0, sizeof(ctx));
    int user_init_rc = sceUserServiceInitialize(NULL);
    printf("user service init rc=0x%08x\n", (unsigned)user_init_rc);
    if (user_init_rc != 0) {
        printf("user service unavailable; launch refused\n");
        return 22;
    }
    if (sceUserServiceGetForegroundUser(&user_id) != 0 ||
        user_id == UINT32_MAX) {
        printf("no foreground user; launch refused\n");
        (void)sceUserServiceTerminate();
        return 22;
    }
    ctx.structsize = sizeof(ctx);
    ctx.user_id = user_id;
    int rc = sceSystemServiceLaunchApp(TARGET_TITLE, NULL, &ctx);
    printf("launch rc=0x%08x\n", (unsigned)rc);
    (void)sceUserServiceTerminate();
    /* LaunchApp returns a non-negative app ID on success, not necessarily 0. */
    return rc >= 0 ? 0 : 23;
#else
    if (app_id <= 0 || identify_rc != 0) {
        printf("no identifiable BigApp; close refused\n");
        return 10;
    }
    if (strcmp(running, TARGET_TITLE) != 0) {
        printf("title mismatch; close refused\n");
        return 11;
    }
    int rc = sceSystemServiceKillApp(app_id, -1, 0, 0);
    printf("clean close rc=0x%08x\n", (unsigned)rc);
    if (rc != 0)
        return 12;
    for (int i = 0; i < 50; ++i) {
        usleep(100000);
        if (sceSystemServiceGetAppIdOfRunningBigApp() <= 0) {
            printf("verified closed after %d ms\n", (i + 1) * 100);
            return 0;
        }
    }
    printf("clean close not verified; no forced kill attempted\n");
    return 13;
#endif
}
