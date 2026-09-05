#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>

#define LOG_PATH "/data/ps5-native-jit-probe.log"

int sceSystemServiceGetAppIdOfRunningBigApp(void);
int sceSystemServiceKillApp(int, int, int, int);

static void log_result(int fd, const char *name, void *addr, int rc, int value) {
    char line[256];
    int n = snprintf(line, sizeof(line),
                     "%s addr=%p rc=%d errno=%d value=%d\n",
                     name, addr, rc, errno, value);
    if (n > 0) {
        write(fd, line, (size_t)n);
        fsync(fd);
    }
}

static void emit_return_value(void *page, uint32_t value) {
    /* mov eax, imm32; ret */
    uint8_t code[] = {0xb8, 0, 0, 0, 0, 0xc3};
    memcpy(&code[1], &value, sizeof(value));
    memcpy(page, code, sizeof(code));
}

int main(void) {
    int fd = open(LOG_PATH, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    size_t size = 0x4000;
    int value = -1;

    errno = 0;
    void *page = mmap(NULL, size, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    log_result(fd, "mmap-rw", page, page == MAP_FAILED ? -1 : 0, -1);
    if (page != MAP_FAILED) {
        emit_return_value(page, 42);
        errno = 0;
        int rc = mprotect(page, size, PROT_READ | PROT_EXEC);
        if (!rc) value = ((int (*)(void))page)();
        log_result(fd, "rw-to-rx", page, rc, value);

        errno = 0;
        rc = mprotect(page, size, PROT_READ | PROT_WRITE);
        log_result(fd, "rx-to-rw", page, rc, -1);
        if (!rc) {
            emit_return_value(page, 43);
            errno = 0;
            rc = mprotect(page, size, PROT_READ | PROT_EXEC);
            value = rc ? -1 : ((int (*)(void))page)();
            log_result(fd, "second-rw-to-rx", page, rc, value);
        }
        munmap(page, size);
    }

    errno = 0;
    void *rwx = mmap(NULL, size, PROT_READ | PROT_WRITE | PROT_EXEC,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    value = -1;
    if (rwx != MAP_FAILED) {
        emit_return_value(rwx, 99);
        value = ((int (*)(void))rwx)();
    }
    log_result(fd, "mmap-rwx", rwx, rwx == MAP_FAILED ? -1 : 0, value);
    if (rwx != MAP_FAILED) munmap(rwx, size);

    if (fd >= 0) close(fd);
    int app_id = sceSystemServiceGetAppIdOfRunningBigApp();
    if (app_id > 0) sceSystemServiceKillApp(app_id, -1, 0, 0);
    return 0;
}
