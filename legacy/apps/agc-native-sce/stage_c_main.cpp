#include <cstddef>
#include <cstdint>
#include <signal.h>
#include <time.h>
#include <unistd.h>

#ifndef STAGE_C_FILL_BYTES
#define STAGE_C_FILL_BYTES 256
#endif

extern "C" {
int open(const char *, int, ...);
long write(int, const void *, std::size_t);
int fsync(int);
int close(int);
void *memset(void *, int, std::size_t);
int sceKernelReserveVirtualRange(void **, std::size_t, int, std::size_t);
int sceKernelAllocateMainDirectMemory(std::size_t, std::size_t, int,
                                      std::int64_t *);
int sceKernelBatchMap(void *, int, int *);
int sceKernelMunmap(void *, std::size_t);
int sceKernelReleaseDirectMemory(std::int64_t, std::size_t);
int sceSysmoduleLoadModuleInternal(unsigned, ...);
int sceSysmoduleUnloadModuleInternal(unsigned, ...);
std::int32_t sceAgcDriverSubmitDcb(void *);
std::int32_t sceAgcInit(void *, std::uint32_t);
}

namespace {
constexpr int kWrite = 1, kCreate = 0x200, kTruncate = 0x400;
constexpr unsigned kAgcModule = 0x80000094U;
constexpr std::size_t kArenaBytes = 0x20000;
constexpr std::size_t kAlignment = 0x10000;
constexpr std::size_t kFillOffset = 0x1000;
constexpr std::size_t kGuardBytes = 64;
constexpr std::size_t kFenceOffset = 0x1000;
constexpr std::size_t kFillBytes = STAGE_C_FILL_BYTES;
constexpr std::uint32_t kPattern = UINT32_C(0x6b5aa5c3);
constexpr std::uint8_t kOutside = 0x3c;
constexpr std::uint8_t kPrefix = 0xc3;
constexpr std::uint8_t kSuffix = 0x5a;
constexpr char kLog[] = "/download0/agc-native-sce-phase0.log";

static_assert(kFillBytes > 4, "Stage C must exceed Native Label's 4 bytes");
static_assert((kFillBytes & 3) == 0, "DMA fill must be DWORD sized");
static_assert(kFillOffset >= kGuardBytes, "prefix guard must fit");
static_assert(kFillOffset + kFillBytes + kGuardBytes <= kArenaBytes,
              "fill and guards must fit private data arena");

struct Submit {
    const std::uint32_t *words;
    std::uint32_t count;
    std::uint8_t flag;
    std::uint8_t pad[3];
};
struct BatchEntry {
    void *address;
    std::int64_t physical;
    std::size_t length;
    std::uint8_t protection;
    std::uint8_t memory_type;
    std::uint16_t reserved;
    std::uint32_t operation;
};
struct Arena {
    void *address = nullptr;
    std::int64_t physical = -1;
    bool reserved = false;
    bool allocated = false;
    bool mapped = false;
};
static_assert(sizeof(Submit) == 0x10);
static_assert(sizeof(BatchEntry) == 0x20);
static_assert(offsetof(BatchEntry, protection) == 0x18);
static_assert(offsetof(BatchEntry, memory_type) == 0x19);
static_assert(offsetof(BatchEntry, operation) == 0x1c);

int g_log = -1;
volatile sig_atomic_t g_transaction_possible = 0;
Arena g_command;
Arena g_data;
bool g_agc_loaded = false;

std::size_t string_length(const char *value) {
    std::size_t size = 0;
    while (value[size]) ++size;
    return size;
}
void log_text(const char *value) {
    if (g_log >= 0) {
        (void)write(g_log, value, string_length(value));
        (void)fsync(g_log);
    }
}
void log_hex32(const char *label, std::int32_t result) {
    static constexpr char digits[] = "0123456789abcdef";
    char value[11] = "0x00000000";
    std::uint32_t word = static_cast<std::uint32_t>(result);
    for (int index = 9; index >= 2; --index) {
        value[index] = digits[word & 15];
        word >>= 4;
    }
    log_text(label);
    if (g_log >= 0) (void)write(g_log, value, 10);
    log_text("\n");
}
void log_bool(const char *label, bool value) {
    log_text(label);
    log_text(value ? "true\n" : "false\n");
}
[[noreturn]] void park(const char *reason) {
    log_text("PARKED_STAGE_C_TRANSACTION reason=");
    log_text(reason);
    log_text("; retain process, AGC and both direct mappings; DO_NOT_CLOSE_PPSA99998\n");
    (void)alarm(0);
    for (;;) (void)pause();
}
void watchdog(int) {
    if (g_transaction_possible) park("watchdog after submit boundary");
    log_text("watchdog before submit; safe failure\n");
    _exit(124);
}
std::uint64_t monotonic_ns() {
    struct timespec time {};
    (void)clock_gettime(CLOCK_MONOTONIC, &time);
    return std::uint64_t(time.tv_sec) * UINT64_C(1000000000) +
           std::uint64_t(time.tv_nsec);
}
void flush_gpu_data(const void *address, std::size_t bytes) {
    auto cursor = static_cast<const std::uint8_t *>(address);
    const auto end = cursor + bytes;
    for (; cursor < end; cursor += 64)
        __asm__ volatile("clflush (%0)" : : "r"(cursor) : "memory");
    __asm__ volatile("mfence" : : : "memory");
}
int create_arena(Arena &arena, const char *prefix) {
    int result = sceKernelReserveVirtualRange(&arena.address, kArenaBytes, 0,
                                               kAlignment);
    log_text(prefix); log_hex32("_virtual_reserve=", result);
    if (result != 0 || !arena.address) return result != 0 ? result : -1;
    arena.reserved = true;
    result = sceKernelAllocateMainDirectMemory(kArenaBytes, kAlignment, 0x0c,
                                               &arena.physical);
    log_text(prefix); log_hex32("_direct_allocate=", result);
    if (result != 0) return result;
    arena.allocated = true;
    BatchEntry entry {arena.address, arena.physical, kArenaBytes, 0xf2, 0x0c,
                      0, 0};
    int processed = -1;
    result = sceKernelBatchMap(&entry, 1, &processed);
    log_text(prefix); log_hex32("_batch_map=", result);
    log_text(prefix); log_hex32("_batch_map_processed=", processed);
    if (result != 0 || processed != 1)
        park("BatchMap result ambiguous or rejected before submit");
    arena.mapped = true;
    if ((reinterpret_cast<std::uintptr_t>(arena.address) & (kAlignment - 1)) != 0)
        park("mapping alignment contradiction before submit");
    return 0;
}
int destroy_arena(Arena &arena, const char *prefix) {
    if (arena.mapped) {
        BatchEntry entry {arena.address, 0, kArenaBytes, 0xf2, 0x0c, 0, 1};
        int processed = -1;
        int result = sceKernelBatchMap(&entry, 1, &processed);
        log_text(prefix); log_hex32("_batch_unmap=", result);
        log_text(prefix); log_hex32("_batch_unmap_processed=", processed);
        if (result != 0 || processed != 1) return result != 0 ? result : -1;
        arena.mapped = false;
    }
    if (arena.allocated) {
        int result = sceKernelReleaseDirectMemory(arena.physical, kArenaBytes);
        log_text(prefix); log_hex32("_direct_release=", result);
        if (result != 0) return result;
        arena.allocated = false;
        arena.physical = -1;
    }
    if (arena.reserved) {
        int result = sceKernelMunmap(arena.address, kArenaBytes);
        log_text(prefix); log_hex32("_virtual_release=", result);
        if (result != 0) return result;
        arena.reserved = false;
        arena.address = nullptr;
    }
    return 0;
}
bool byte_range_is(const std::uint8_t *begin, std::size_t bytes,
                   std::uint8_t expected) {
    for (std::size_t index = 0; index < bytes; ++index)
        if (begin[index] != expected) return false;
    return true;
}
bool target_matches(const std::uint8_t *target) {
    for (std::size_t index = 0; index < kFillBytes; index += 4) {
        std::uint32_t value = 0;
        __builtin_memcpy(&value, target + index, sizeof(value));
        if (value != kPattern) return false;
    }
    return true;
}
bool outside_untouched(const std::uint8_t *base) {
    const std::size_t prefix_begin = kFillOffset - kGuardBytes;
    const std::size_t suffix_end = kFillOffset + kFillBytes + kGuardBytes;
    return byte_range_is(base, prefix_begin, kOutside) &&
           byte_range_is(base + suffix_end, kArenaBytes - suffix_end, kOutside);
}
int cleanup_all() {
    int result = destroy_arena(g_data, "data");
    if (result != 0) return result;
    result = destroy_arena(g_command, "command");
    if (result != 0) return result;
    if (g_agc_loaded) {
        result = sceSysmoduleUnloadModuleInternal(kAgcModule);
        log_hex32("agc_unload=", result);
        if (result != 0) return result;
        g_agc_loaded = false;
    }
    return 0;
}
[[noreturn]] void finish_pretransaction(int result) {
    (void)alarm(0);
    int cleanup = cleanup_all();
    if (cleanup != 0) park("pre-submit cleanup failed");
    log_hex32("stage_c_pretransaction_result=", result);
    log_text("STAGE_C_PRE_TRANSACTION_CLEANUP_COMPLETE\n");
    log_text("pre-submit clean failure; parked-safe; close exact title PPSA99998\n");
    (void)close(g_log);
    for (;;) (void)pause();
}
} // namespace

int main() {
    g_log = open(kLog, kWrite | kCreate | kTruncate, 0644);
    if (g_log < 0) for (;;) (void)pause();
    (void)signal(SIGALRM, watchdog);
    (void)signal(SIGSEGV, watchdog);
    (void)signal(SIGBUS, watchdog);
    (void)alarm(12);
    log_text("AGC native Stage C v1; private immediate DMA fill; separate command/data mappings; no VideoOut, shaders, draw or commercial process access\n");
    log_hex32("stage_c_fill_bytes=", static_cast<std::int32_t>(kFillBytes));

    int result = sceSysmoduleLoadModuleInternal(kAgcModule);
    log_hex32("agc_load=", result);
    if (result != 0) finish_pretransaction(result);
    g_agc_loaded = true;
    std::uint64_t agc_state = 0;
    result = sceAgcInit(&agc_state, sizeof(agc_state));
    log_hex32("agc_init=", result);
    if (result != 0) finish_pretransaction(result);
    result = create_arena(g_command, "command");
    if (result != 0) finish_pretransaction(result);
    result = create_arena(g_data, "data");
    if (result != 0) finish_pretransaction(result);

    auto command = static_cast<std::uint8_t *>(g_command.address);
    auto data = static_cast<std::uint8_t *>(g_data.address);
    auto target = data + kFillOffset;
    auto fence = reinterpret_cast<volatile std::uint64_t *>(
        command + kFenceOffset);
    if (!(reinterpret_cast<std::uintptr_t>(target) + kFillBytes <=
          reinterpret_cast<std::uintptr_t>(fence) ||
          reinterpret_cast<std::uintptr_t>(fence) + sizeof(*fence) <=
          reinterpret_cast<std::uintptr_t>(target)))
        park("target and fence overlap");

    (void)memset(command, 0, kArenaBytes);
    (void)memset(data, kOutside, kArenaBytes);
    (void)memset(target - kGuardBytes, kPrefix, kGuardBytes);
    (void)memset(target, 0xa5, kFillBytes);
    (void)memset(target + kFillBytes, kSuffix, kGuardBytes);
    __atomic_store_n(fence, UINT64_C(1), __ATOMIC_RELEASE);
    const std::uintptr_t destination = reinterpret_cast<std::uintptr_t>(target);
    const std::uintptr_t fence_address = reinterpret_cast<std::uintptr_t>(fence);
    const std::uint32_t stream[15] = {
        UINT32_C(0xc0055000), UINT32_C(0xc0300000), kPattern, 0,
        std::uint32_t(destination), std::uint32_t(destination >> 32),
        std::uint32_t(kFillBytes), UINT32_C(0xc0064900),
        UINT32_C(0x06000528), UINT32_C(0x42010000),
        std::uint32_t(fence_address), std::uint32_t(fence_address >> 32),
        0, 0, 0,
    };
    for (unsigned index = 0; index < 15; ++index)
        reinterpret_cast<std::uint32_t *>(command)[index] = stream[index];
    flush_gpu_data(data, kArenaBytes);
    flush_gpu_data(command, kArenaBytes);
    log_text("STAGE_C_TRANSACTION_STARTED\n");
    Submit submit {reinterpret_cast<const std::uint32_t *>(command), 15, 0,
                   {0, 0, 0}};
    g_transaction_possible = 1;
    result = sceAgcDriverSubmitDcb(&submit);
    log_hex32("stage_c_submit=", result);
    if (result != 0) park("nonzero submit return is ambiguous");
    const std::uint64_t deadline = monotonic_ns() + UINT64_C(2000000000);
    while (__atomic_load_n(fence, __ATOMIC_ACQUIRE) != 0 &&
           monotonic_ns() < deadline) {
        struct timespec delay {0, 1000000};
        (void)nanosleep(&delay, nullptr);
    }
    if (__atomic_load_n(fence, __ATOMIC_ACQUIRE) != 0)
        park("ownership fence timeout");
    log_text("STAGE_C_GPU_FENCE_ZERO\n");

    const bool target_ok = target_matches(target);
    const bool prefix_ok = byte_range_is(target - kGuardBytes, kGuardBytes,
                                         kPrefix);
    const bool suffix_ok = byte_range_is(target + kFillBytes, kGuardBytes,
                                         kSuffix);
    const bool outside_ok = outside_untouched(data);
    log_bool("stage_c_target_matches=", target_ok);
    log_bool("stage_c_prefix_canary_intact=", prefix_ok);
    log_bool("stage_c_suffix_canary_intact=", suffix_ok);
    log_bool("stage_c_outside_untouched=", outside_ok);
    if (!target_ok || !prefix_ok || !suffix_ok || !outside_ok)
        park("post-fence content or canary mismatch");

    (void)memset(data, 0, kArenaBytes);
    (void)memset(command, 0, kArenaBytes);
    log_text("stage_c_arenas_scrubbed=true\n");
    result = cleanup_all();
    if (result != 0) park("post-completion cleanup failed");
    g_transaction_possible = 0;
    (void)alarm(0);
    log_text("STAGE_C_COMPLETE cleanup complete; parked-safe; close exact title PPSA99998\n");
    (void)close(g_log);
    for (;;) (void)pause();
}
