#include <cstddef>
#include <cstdint>

extern "C" {
#include "../../probes/ps5-agc-phase0/stage_e_compiled_metadata.h"
int open(const char *, int, ...);
long write(int, const void *, std::size_t);
int fsync(int);
int close(int);
int sceKernelUsleep(std::uint32_t);
extern const std::uint8_t stage_e_gs_start[], stage_e_gs_end[];
extern const std::uint8_t stage_e_ps_start[], stage_e_ps_end[];
}

namespace {
constexpr int kWrite = 1, kCreate = 0x200, kTruncate = 0x400;
constexpr char kLog[] = "/download0/agc-native-sce-phase0.log";

std::size_t length(const char *s) {
    std::size_t n = 0;
    while (s[n]) ++n;
    return n;
}

void text(int fd, const char *s) {
    (void)write(fd, s, length(s));
    (void)fsync(fd);
}

[[noreturn]] void park() {
    for (;;) (void)sceKernelUsleep(1000000);
}
}

int main() {
    int fd = open(kLog, kWrite | kCreate | kTruncate, 0644);
    if (fd < 0) park();

    text(fd, "AGC Stage E loader smoke v1; CPU-only; no AGC calls, DCB, submit, draw, or VideoOut\n");
    const std::size_t gs_bytes = stage_e_gs_end - stage_e_gs_start;
    const std::size_t ps_bytes = stage_e_ps_end - stage_e_ps_start;
    text(fd, gs_bytes == STAGE_E_GS_ISA_BYTES &&
                     ps_bytes == STAGE_E_PS_ISA_BYTES
                 ? "STAGE_E_LOADER_SMOKE_COMPLETE=true\n"
                 : "STAGE_E_LOADER_SMOKE_COMPLETE=false\n");
    text(fd, "parked-safe; close exact title PPSA99998\n");
    (void)close(fd);
    park();
}
