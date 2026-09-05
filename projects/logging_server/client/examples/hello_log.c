/*
 * hello_log: minimal ps5log client in single-header mode. Builds on the host
 * (make host-example) and as a PS5 payload (make ps5-example). It reads
 * dev.conf from the default search list, or from $PS5LOG_CONF, or argv[1].
 *
 * Usage: hello_log [dev.conf] [count]
 * Env:   HELLO_LOG_CAPTURE=1  also exercise zero-change printf capture.
 *
 * With capture enabled, everything printed between init and ps5log_close()
 * goes to the server as RAW lines; the final status line, printed after the
 * close restored fd 1, goes to the real stdout.
 */
#define PS5LOG_IMPLEMENTATION
#define PS5LOG_SHORT_MACROS
#include "ps5log.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef HELLO_LOG_TITLE
#define HELLO_LOG_TITLE "PPSA99999"
#endif

int main(int argc, char **argv) {
    ps5log_config cfg;
    ps5log_stats stats;
    const char *used = NULL;
    const char *capture_env = getenv("HELLO_LOG_CAPTURE");
    int capture = capture_env && *capture_env && *capture_env != '0';
    int count = argc > 2 ? atoi(argv[2]) : 5;
    int crc = 1;
    int rc;
    int i;
    uint64_t t0;
    uint64_t init_ms;

#ifdef HELLO_LOG_FORCE_CAPTURE
    capture = 1;   /* payload loaders pass no environment */
#endif

    /* No stdout output before this point: capture must precede first use so
     * setvbuf() can make stdout line-buffered (see ps5log.h). */
    t0 = ps5log_monotonic_ns();
    ps5log_config_defaults(&cfg);
    if (argc > 1) {
        const char *paths[1];
        paths[0] = argv[1];
        rc = ps5log_load_config(paths, 1, &cfg, &used);
        if (rc != 0) {
            fprintf(stderr, "hello_log: cannot use %s (rc=%d)\n", argv[1], rc);
            return 2;
        }
        rc = ps5log_init(&cfg, HELLO_LOG_TITLE, "hello-log", ps5log_monotonic_ns());
    } else {
        rc = ps5log_init_default(HELLO_LOG_TITLE, "hello-log");
    }
    init_ms = (ps5log_monotonic_ns() - t0) / 1000000ull;
    if (capture)
        crc = ps5log_capture_stdio(PS5LOG_CAPTURE_STDIO | PS5LOG_CAPTURE_IGNORE_SIGPIPE);

    ps5log_stats_get(&stats);
    if (!used) used = stats.config_path;
    printf("hello_log: init rc=%d capture rc=%d config=%s network=%s init_ms=%llu\n", rc, crc,
           used ? used : "(none)",
           ps5log_enabled() ? "up" : (stats.disabled_reason ? stats.disabled_reason : "down"),
           (unsigned long long)init_ms);

    LOGM("HELLO_LOG_STARTED");
    for (i = 0; i < count; ++i)
        LOG("frame=%d flip_arg=0x%x", i, 0x420000 + i);
    ps5log_hex64(PS5LOG_INFO, "fence", 0x1100);
    LOGW("example warning with\ttab and\nnewline");
    if (capture) {
        printf("plain printf line %d\n", 1);
        fprintf(stderr, "plain stderr line %d\n", 2);
    }
    LOGM("HELLO_LOG_COMPLETE");
    ps5log_close("complete");   /* restores fd 1 and fd 2 when captured */

    ps5log_stats_get(&stats);
    printf("hello_log: sent=%llu mirrored=%llu dropped=%llu bytes=%llu last_errno=%d\n",
           (unsigned long long)stats.lines_sent,
           (unsigned long long)stats.lines_mirrored,
           (unsigned long long)stats.lines_dropped,
           (unsigned long long)stats.bytes_sent, stats.last_errno);
    return stats.lines_sent == (uint64_t)count + 4 ? 0 : 1;
}
