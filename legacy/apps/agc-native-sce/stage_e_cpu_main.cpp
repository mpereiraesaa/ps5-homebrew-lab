#include <cstddef>
#include <cstdint>

extern "C" {
#include "../../../include/agc_link_shaders_contract.h"
#include "../../probes/ps5-agc-phase0/stage_e_shader_header.h"
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
constexpr unsigned kAgcModule = 0x80000094U;
constexpr std::size_t kArenaBytes = 0x10000, kAlignment = 0x4000;
constexpr std::size_t kVsHeader = 0x0000, kPsHeader = 0x0200;
constexpr std::size_t kVsCode = 0x1000, kPsCode = 0x1200;
constexpr std::size_t kCxA = 0x2000, kUcA = 0x2200;
constexpr std::size_t kCxB = 0x2400, kUcB = 0x2600;
constexpr std::size_t kGuard = 32;
constexpr std::size_t kShaderFooterBytes = 0x30;
constexpr char kLog[] = "/download0/agc-native-sce-phase0.log";
/* Diagnostic anchor retained to make checkpoint builds easy to identify. It
 * is not a loader requirement: the import-smoke artifact ran without it. */
extern "C" volatile std::uint32_t stage_e_linker_data_anchor = 0x53544745U;
/* Zero means normal execution; non-zero values are bounded diagnostics. */
extern "C" volatile std::uint32_t stage_e_runtime_checkpoint = 0;

std::size_t length(const char *s) { std::size_t n = 0; while (s[n]) ++n; return n; }
void text(int f, const char *s) { (void)write(f, s, length(s)); (void)fsync(f); }
void hex32(int f, const char *label, int result) {
    static constexpr char x[] = "0123456789abcdef"; char b[11] = "0x00000000";
    auto v = static_cast<std::uint32_t>(result);
    for (int i = 9; i >= 2; --i) { b[i] = x[v & 15U]; v >>= 4; }
    text(f, label); (void)write(f, b, 10); text(f, "\n");
}
void hex64(int f, const char *label, std::uint64_t v) {
    static constexpr char x[] = "0123456789abcdef"; char b[19] = "0x0000000000000000";
    for (int i = 17; i >= 2; --i) { b[i] = x[v & 15U]; v >>= 4; }
    text(f, label); (void)write(f, b, 18); text(f, "\n");
}
void yes(int f, const char *label, bool value) { text(f, label); text(f, value ? "true\n" : "false\n"); }
std::uint64_t hash64(const void *data, std::size_t bytes) {
    auto p = static_cast<const std::uint8_t *>(data);
    std::uint64_t h = UINT64_C(14695981039346656037);
    for (std::size_t i = 0; i < bytes; ++i) { h ^= p[i]; h *= UINT64_C(1099511628211); }
    return h;
}
bool guard(const std::uint8_t *p, std::size_t bytes) {
    for (std::size_t i = 0; i < kGuard; ++i)
        if (p[-static_cast<std::ptrdiff_t>(kGuard) + i] != 0xc3 || p[bytes + i] != 0x3c) return false;
    return true;
}
void prepare_output(std::uint8_t *p, std::size_t bytes, int fill) {
    memset(p - kGuard, 0xc3, kGuard); memset(p, fill, bytes); memset(p + bytes, 0x3c, kGuard);
}
[[noreturn]] void park() { for (;;) (void)sceKernelUsleep(1000000); }
}

int main() {
    int f = open(kLog, kWrite | kCreate | kTruncate, 0644); if (f < 0) park();
    text(f, "AGC Stage E CPU-only independent shader link v1; no queue, DCB, submit, draw, or VideoOut\n");
    if (stage_e_runtime_checkpoint == 1) {
        text(f, "STAGE_E_CHECKPOINT_1=true\ncleanup complete; parked-safe; close exact title PPSA99998\n");
        close(f);
        park();
    }
    const std::size_t vs_isa_bytes = stage_e_gs_end - stage_e_gs_start;
    const std::size_t ps_isa_bytes = stage_e_ps_end - stage_e_ps_start;
    const std::size_t vs_bytes = vs_isa_bytes + kShaderFooterBytes;
    const std::size_t ps_bytes = ps_isa_bytes + kShaderFooterBytes;
    bool embedded = vs_isa_bytes == STAGE_E_GS_ISA_BYTES &&
                    ps_isa_bytes == STAGE_E_PS_ISA_BYTES;
    yes(f, "generated_shader_sizes=", embedded);
    if (stage_e_runtime_checkpoint == 2) {
        text(f, "STAGE_E_CHECKPOINT_2=true\ncleanup complete; parked-safe; close exact title PPSA99998\n");
        close(f);
        park();
    }
    std::int64_t physical = -1; void *mapping = nullptr;
    int allocation = embedded ? sceKernelAllocateMainDirectMemory(kArenaBytes,
        kAlignment, 12, &physical) : -1; hex32(f, "direct_allocate=", allocation);
    int mapped = allocation == 0 ? sceKernelMapDirectMemory(&mapping, kArenaBytes, 0x33,
        0, physical, kAlignment) : -1; hex32(f, "direct_map=", mapped);
    if (mapped != 0 || !mapping) {
        if (mapping) (void)sceKernelMunmap(mapping, kArenaBytes);
        if (allocation == 0) (void)sceKernelReleaseDirectMemory(physical, kArenaBytes);
        text(f, "STAGE_E_PRECALL_FAILURE cleanup complete; parked-safe; close exact title PPSA99998\n");
        close(f); park();
    }
    if (stage_e_runtime_checkpoint == 3) {
        int checkpoint_unmap = sceKernelMunmap(mapping, kArenaBytes);
        int checkpoint_release = sceKernelReleaseDirectMemory(physical, kArenaBytes);
        hex32(f, "checkpoint_unmap=", checkpoint_unmap);
        hex32(f, "checkpoint_release=", checkpoint_release);
        yes(f, "STAGE_E_CHECKPOINT_3=", checkpoint_unmap == 0 && checkpoint_release == 0);
        text(f, "cleanup complete; parked-safe; close exact title PPSA99998\n");
        close(f);
        park();
    }
    auto base = static_cast<std::uint8_t *>(mapping); memset(base, 0, kArenaBytes);
    auto vs = reinterpret_cast<StageEShaderArena *>(base + kVsHeader);
    auto ps = reinterpret_cast<StageEShaderArena *>(base + kPsHeader);
    auto vs_code = base + kVsCode; auto ps_code = base + kPsCode;
    int vh = stage_e_build_shader_header(vs, STAGE_E_SHADER_PRE_RASTER, vs_bytes);
    int ph = stage_e_build_shader_header(ps, STAGE_E_SHADER_PIXEL, ps_bytes);
    memset(vs_code, 0, vs_bytes);
    memset(ps_code, 0, ps_bytes);
    memcpy(vs_code, stage_e_gs_start, vs_isa_bytes);
    memcpy(ps_code, stage_e_ps_start, ps_isa_bytes);
    memcpy(vs_code + vs_bytes - kShaderFooterBytes, "barefoot", 8);
    memcpy(ps_code + ps_bytes - kShaderFooterBytes, "barefoot", 8);
    bool preflight = vh == 0 && ph == 0 &&
        stage_e_validate_unrelocated_header(vs, 2, vs_bytes) == 0 &&
        stage_e_validate_unrelocated_header(ps, 1, ps_bytes) == 0 &&
        !(reinterpret_cast<std::uintptr_t>(vs_code) & 255U) &&
        !(reinterpret_cast<std::uintptr_t>(ps_code) & 255U);
    yes(f, "independent_headers_prevalidated=", preflight);
    const auto vs_hash_before = hash64(vs_code, vs_bytes), ps_hash_before = hash64(ps_code, ps_bytes);
    hex64(f, "vs_fnv1a64=", vs_hash_before); hex64(f, "ps_fnv1a64=", ps_hash_before);
    if (stage_e_runtime_checkpoint == 4) {
        memset(base, 0, kArenaBytes);
        int checkpoint_unmap = sceKernelMunmap(mapping, kArenaBytes);
        int checkpoint_release = sceKernelReleaseDirectMemory(physical, kArenaBytes);
        hex32(f, "checkpoint_unmap=", checkpoint_unmap);
        hex32(f, "checkpoint_release=", checkpoint_release);
        yes(f, "STAGE_E_CHECKPOINT_4=", preflight && checkpoint_unmap == 0 && checkpoint_release == 0);
        text(f, "cleanup complete; parked-safe; close exact title PPSA99998\n");
        close(f);
        park();
    }
    int load = -1, init = -1, create_vs = -1, create_ps = -1, link_a = -1, link_b = -1;
    void *vs_object = nullptr, *ps_object = nullptr; std::uint64_t agc_state = 0;
    if (preflight) { load = sceSysmoduleLoadModuleInternal(kAgcModule); hex32(f, "agc_load=", load); }
    if (load == 0) { init = sceAgcInit(&agc_state, sizeof(agc_state)); hex32(f, "agc_init=", init); }
    if (stage_e_runtime_checkpoint == 5) {
        memset(base, 0, kArenaBytes);
        int checkpoint_unload = load == 0 ? sceSysmoduleUnloadModuleInternal(kAgcModule) : 0;
        int checkpoint_unmap = sceKernelMunmap(mapping, kArenaBytes);
        int checkpoint_release = sceKernelReleaseDirectMemory(physical, kArenaBytes);
        hex32(f, "checkpoint_unload=", checkpoint_unload);
        hex32(f, "checkpoint_unmap=", checkpoint_unmap);
        hex32(f, "checkpoint_release=", checkpoint_release);
        yes(f, "STAGE_E_CHECKPOINT_5=", preflight && load == 0 && init == 0 &&
            checkpoint_unload == 0 && checkpoint_unmap == 0 && checkpoint_release == 0);
        text(f, "cleanup complete; parked-safe; close exact title PPSA99998\n");
        close(f);
        park();
    }
    if (init == 0) { create_vs = sceAgcCreateShader(&vs_object, vs, vs_code); hex32(f, "create_pre_raster=", create_vs); }
    if (stage_e_runtime_checkpoint == 6) {
        memset(base, 0, kArenaBytes);
        int checkpoint_unload = load == 0 ? sceSysmoduleUnloadModuleInternal(kAgcModule) : 0;
        int checkpoint_unmap = sceKernelMunmap(mapping, kArenaBytes);
        int checkpoint_release = sceKernelReleaseDirectMemory(physical, kArenaBytes);
        hex32(f, "checkpoint_unload=", checkpoint_unload);
        hex32(f, "checkpoint_unmap=", checkpoint_unmap);
        hex32(f, "checkpoint_release=", checkpoint_release);
        yes(f, "STAGE_E_CHECKPOINT_6=", preflight && load == 0 && init == 0 &&
            create_vs == 0 && checkpoint_unload == 0 && checkpoint_unmap == 0 &&
            checkpoint_release == 0);
        text(f, "cleanup complete; parked-safe; close exact title PPSA99998\n");
        close(f);
        park();
    }
    if (create_vs == 0) { create_ps = sceAgcCreateShader(&ps_object, ps, ps_code); hex32(f, "create_pixel=", create_ps); }
    if (stage_e_runtime_checkpoint == 7) {
        memset(base, 0, kArenaBytes);
        int checkpoint_unload = load == 0 ? sceSysmoduleUnloadModuleInternal(kAgcModule) : 0;
        int checkpoint_unmap = sceKernelMunmap(mapping, kArenaBytes);
        int checkpoint_release = sceKernelReleaseDirectMemory(physical, kArenaBytes);
        hex32(f, "checkpoint_unload=", checkpoint_unload);
        hex32(f, "checkpoint_unmap=", checkpoint_unmap);
        hex32(f, "checkpoint_release=", checkpoint_release);
        yes(f, "STAGE_E_CHECKPOINT_7=", preflight && load == 0 && init == 0 &&
            create_vs == 0 && create_ps == 0 && checkpoint_unload == 0 &&
            checkpoint_unmap == 0 && checkpoint_release == 0);
        text(f, "cleanup complete; parked-safe; close exact title PPSA99998\n");
        close(f);
        park();
    }
    auto cx_a = base + kCxA, uc_a = base + kUcA, cx_b = base + kCxB, uc_b = base + kUcB;
    prepare_output(cx_a, sizeof(AgcLinkedCx1202), 0xa5); prepare_output(uc_a, sizeof(AgcLinkedUc1202), 0x5a);
    prepare_output(cx_b, sizeof(AgcLinkedCx1202), 0x96); prepare_output(uc_b, sizeof(AgcLinkedUc1202), 0x69);
    if (create_ps == 0) {
        link_a = sceAgcLinkShaders(cx_a, uc_a, nullptr, vs_object, ps_object, 4); hex32(f, "link_a=", link_a);
        link_b = sceAgcLinkShaders(cx_b, uc_b, nullptr, vs_object, ps_object, 4); hex32(f, "link_b=", link_b);
    }
    bool guards = guard(cx_a, sizeof(AgcLinkedCx1202)) && guard(uc_a, sizeof(AgcLinkedUc1202)) &&
                  guard(cx_b, sizeof(AgcLinkedCx1202)) && guard(uc_b, sizeof(AgcLinkedUc1202));
    bool deterministic = link_a == 0 && link_b == 0 &&
        memcmp(cx_a, cx_b, sizeof(AgcLinkedCx1202)) == 0 && memcmp(uc_a, uc_b, sizeof(AgcLinkedUc1202)) == 0;
    bool codes = hash64(vs_code, vs_bytes) == vs_hash_before && hash64(ps_code, ps_bytes) == ps_hash_before;
    yes(f, "linked_output_canaries_intact=", guards); yes(f, "linked_outputs_deterministic=", deterministic);
    yes(f, "generated_shader_code_unchanged=", codes);
    hex64(f, "linked_cx_fnv1a64=", hash64(cx_a, sizeof(AgcLinkedCx1202)));
    hex64(f, "linked_uc_fnv1a64=", hash64(uc_a, sizeof(AgcLinkedUc1202)));
    memset(base, 0, kArenaBytes); bool scrubbed = true;
    for (std::size_t i = 0; i < kArenaBytes; ++i) if (base[i]) { scrubbed = false; break; }
    yes(f, "direct_arena_scrubbed=", scrubbed);
    int unload = load == 0 ? sceSysmoduleUnloadModuleInternal(kAgcModule) : 0; hex32(f, "agc_unload=", unload);
    int unmap = sceKernelMunmap(mapping, kArenaBytes); hex32(f, "direct_unmap=", unmap);
    int release = sceKernelReleaseDirectMemory(physical, kArenaBytes); hex32(f, "direct_release=", release);
    bool done = preflight && load == 0 && init == 0 && create_vs == 0 && create_ps == 0 &&
        deterministic && guards && codes && scrubbed && unload == 0 && unmap == 0 && release == 0;
    yes(f, "STAGE_E_CPU_LINK_COMPLETE=", done);
    text(f, "cleanup complete; parked-safe; close exact title PPSA99998\n"); close(f); park();
}
