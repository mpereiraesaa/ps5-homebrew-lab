#include <cstddef>
#include <cstdint>

extern "C" {
#include "../../probes/ps5-agc-phase0/stage_e_compiled_metadata.h"
int open(const char *, int, ...);
long write(int, const void *, std::size_t);
int fsync(int);
int close(int);
void *memcpy(void *, const void *, std::size_t);
void *memset(void *, int, std::size_t);
int memcmp(const void *, const void *, std::size_t);
int sceKernelUsleep(std::uint32_t);
int sceKernelAllocateMainDirectMemory(std::size_t, std::size_t, int,
                                      std::int64_t *);
int sceKernelMapDirectMemory(void **, std::size_t, int, int, std::int64_t,
                             std::size_t);
int sceKernelMunmap(void *, std::size_t);
int sceKernelReleaseDirectMemory(std::int64_t, std::size_t);
int sceSysmoduleLoadModuleInternal(unsigned, ...);
int sceSysmoduleUnloadModuleInternal(unsigned, ...);
std::int32_t sceAgcInit(void *, std::uint32_t);
std::int32_t sceAgcCreateShader(void **, void *, void *);
std::int32_t sceAgcLinkShaders(void *, void *, void *, void *, void *,
                               std::uint32_t);
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

template <typename T> std::uintptr_t address(T pointer) {
    return reinterpret_cast<std::uintptr_t>(pointer);
}
}

int main() {
    int fd = open(kLog, kWrite | kCreate | kTruncate, 0644);
    if (fd < 0) park();

    volatile std::uintptr_t resolved = 0;
    resolved ^= address(&open);
    resolved ^= address(&write);
    resolved ^= address(&fsync);
    resolved ^= address(&close);
    resolved ^= address(&memcpy);
    resolved ^= address(&memset);
    resolved ^= address(&memcmp);
    resolved ^= address(&sceKernelUsleep);
    resolved ^= address(&sceKernelAllocateMainDirectMemory);
    resolved ^= address(&sceKernelMapDirectMemory);
    resolved ^= address(&sceKernelMunmap);
    resolved ^= address(&sceKernelReleaseDirectMemory);
    resolved ^= address(&sceSysmoduleLoadModuleInternal);
    resolved ^= address(&sceSysmoduleUnloadModuleInternal);
    resolved ^= address(&sceAgcInit);
    resolved ^= address(&sceAgcCreateShader);
    resolved ^= address(&sceAgcLinkShaders);

    const bool assets =
        stage_e_gs_end - stage_e_gs_start == STAGE_E_GS_ISA_BYTES &&
        stage_e_ps_end - stage_e_ps_start == STAGE_E_PS_ISA_BYTES;
    text(fd, "AGC Stage E import-resolution smoke v1; no imported API invoked except logging/park\n");
    text(fd, resolved != 0 && assets
                 ? "STAGE_E_IMPORT_SMOKE_COMPLETE=true\n"
                 : "STAGE_E_IMPORT_SMOKE_COMPLETE=false\n");
    text(fd, "parked-safe; close exact title PPSA99998\n");
    (void)close(fd);
    park();
}
