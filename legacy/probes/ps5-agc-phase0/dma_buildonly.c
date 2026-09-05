/* AGC phase 0D: CPU-only reconstruction of one observed DMA_DATA packet. */
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define LOG_PATH "/data/ps5-agc-phase0d-dma-buildonly.log"

static int log_fd = -1;

static void probe_log(const char *fmt, ...)
{
    char line[512];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    if (n < 0)
        return;
    if ((size_t)n >= sizeof(line) - 1)
        n = (int)sizeof(line) - 2;
    line[n++] = '\n';
    if (log_fd >= 0) {
        (void)write(log_fd, line, (size_t)n);
        (void)fsync(log_fd);
    }
    (void)write(STDOUT_FILENO, line, (size_t)n);
}

static void watchdog(int signal_number)
{
    static const char message[] = "watchdog timeout; forcing process exit\n";
    (void)signal_number;
    if (log_fd >= 0)
        (void)write(log_fd, message, sizeof(message) - 1);
    _exit(124);
}

int main(void)
{
    static const uint32_t expected[7] = {
        UINT32_C(0xc0055000), UINT32_C(0xc0300000),
        UINT32_C(0), UINT32_C(0), UINT32_C(0), UINT32_C(0), UINT32_C(4),
    };
    struct {
        uint64_t guard_before;
        uint32_t packet[7];
        uint64_t guard_after;
    } local = {
        .guard_before = UINT64_C(0x3141592653589793),
        .packet = {UINT32_C(0xc0055000), UINT32_C(0xc0300000), 0, 0, 0, 0, 4},
        .guard_after = UINT64_C(0x2718281828459045),
    };
    const uint64_t private_label = (uint64_t)(uintptr_t)&local.guard_after;
    int result = 0;

    log_fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    (void)signal(SIGALRM, watchdog);
    alarm(5);
    probe_log("AGC phase 0D start; CPU build-only; no modules, queue or submit");
    if (memcmp(local.packet, expected, sizeof(expected)) != 0) {
        probe_log("template mismatch");
        result = 10;
        goto out;
    }
    probe_log("template=%08x %08x %08x %08x %08x %08x %08x",
              local.packet[0], local.packet[1], local.packet[2], local.packet[3],
              local.packet[4], local.packet[5], local.packet[6]);

    /* Reproduce only the proven patch operation on this private CPU array. */
    if (((local.packet[0] >> 8) & UINT32_C(0xff)) != UINT32_C(0x50)) {
        probe_log("opcode guard mismatch");
        result = 11;
        goto out;
    }
    memcpy((uint8_t *)local.packet + 0x10, &private_label, sizeof(private_label));
    if (local.packet[4] != (uint32_t)private_label ||
        local.packet[5] != (uint32_t)(private_label >> 32)) {
        probe_log("destination patch mismatch");
        result = 12;
        goto out;
    }
    if (local.packet[0] != expected[0] || local.packet[1] != expected[1] ||
        local.packet[2] != 0 || local.packet[3] != 0 || local.packet[6] != 4) {
        probe_log("destination patch modified immutable fields");
        result = 13;
        goto out;
    }
    if (local.guard_before != UINT64_C(0x3141592653589793) ||
        local.guard_after != UINT64_C(0x2718281828459045)) {
        probe_log("canary mismatch");
        result = 14;
        goto out;
    }
    probe_log("destination patched to private CPU address; guards intact");

out:
    alarm(0);
    probe_log("AGC phase 0D exit result=%d; submitted=no", result);
    if (log_fd >= 0)
        close(log_fd);
    return result;
}
