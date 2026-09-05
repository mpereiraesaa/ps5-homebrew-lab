#include <cstddef>
#include <cstdint>
#include <signal.h>
#include <time.h>
#include <unistd.h>

#include "../../../projects/logging_server/client/ps5log.h"

#include "../../../sdk/agc/include/ps5_agc.h"
#include "../../../sdk/agc/include/ps5_agc_driver.h"

extern "C" {
#include "../../probes/ps5-agc-phase0/stage_b_completion.h"
#include "../../probes/ps5-agc-phase0/stage_b_compose.h"
#include "../../probes/ps5-agc-phase0/stage_b_event_adapter.h"
#include "../../probes/ps5-agc-phase0/stage_b_surface.h"
#include "../../probes/ps5-agc-phase0/stage_b_transaction.h"
#ifdef STAGE_E_TRIANGLE
#include "../../../include/agc_link_shaders_contract.h"
#include "../../../include/agc_register_defaults_layout.h"
#include "../../probes/ps5-agc-phase0/stage_e_color_target.h"
#include "stage_metadata_contract.h"
#ifdef STAGE_F_CUBE
#ifdef STAGE_G_DEPTH
#include "../../probes/ps5-agc-phase0/stage_g_depth_state.h"
#include "../../probes/ps5-agc-phase0/stage_gpu_visibility.h"
#endif
#ifdef STAGE_H_GEARS
#include "../../../projects/ps5-agc-gears/src/gears_frame_runner.h"
#include "../../../projects/ps5-agc-gears/src/gears_rt_clear.h"
#include "../../../projects/ps5-agc-gears/src/gears_renderer.h"
#include "../../../projects/ps5-agc-gears/src/gears_draw_compose.h"
#include "../../../projects/ps5-agc-gears/src/gears_mesh.h"
#include "../../../projects/ps5-agc-gears/src/gears_scene.h"
#endif
#else
#include "../../probes/ps5-agc-phase0/stage_e_compiled_metadata.h"
#endif
#include "../../probes/ps5-agc-phase0/stage_e_dcb_offline.h"
#include "../../probes/ps5-agc-phase0/stage_e_pipeline_registers.h"
#include "../../probes/ps5-agc-phase0/stage_e_runtime_defaults.h"
#include "../../probes/ps5-agc-phase0/stage_e_shader_header.h"
#endif

void *memset(void *, int, std::size_t);
void *memcpy(void *, const void *, std::size_t);
int sceKernelReserveVirtualRange(void **, std::size_t, int, std::size_t);
int sceKernelAllocateMainDirectMemory(std::size_t, std::size_t, int,
                                     std::int64_t *);
int sceKernelMapDirectMemory(void **, std::size_t, int, int, std::int64_t,
                            std::size_t);
int sceKernelBatchMap(void *, int, int *);
int sceKernelMunmap(void *, std::size_t);
int sceKernelReleaseDirectMemory(std::int64_t, std::size_t);
int sceKernelCreateEqueue(void **, const char *);
int sceKernelDeleteEqueue(void *);
int sceVideoOutOpen(std::int32_t, std::int32_t, std::int32_t, const void *);
int sceVideoOutClose(std::int32_t);
int sceVideoOutSetFlipRate(std::int32_t, std::int32_t);
int sceVideoOutAddFlipEvent(void *, std::int32_t, void *);
int sceVideoOutDeleteFlipEvent(void *, std::int32_t);
void sceVideoOutSetBufferAttribute2(void *, std::uint64_t, std::uint32_t,
                                    std::uint32_t, std::uint32_t, std::uint64_t,
                                    std::uint32_t, std::uint64_t);
int sceVideoOutRegisterBuffers2(std::int32_t, std::int32_t, std::int32_t,
                                void *, std::int32_t, void *, std::int32_t,
                                void *);
int sceVideoOutUnregisterBuffers(std::int32_t, std::int32_t);
#ifdef STAGE_E_TRIANGLE
extern const std::uint8_t stage_e_gs_start[], stage_e_gs_end[];
extern const std::uint8_t stage_e_ps_start[], stage_e_ps_end[];
#endif
int sceSysmoduleLoadModuleInternal(unsigned, ...);
int sceSysmoduleUnloadModuleInternal(unsigned, ...);
}

namespace {
constexpr unsigned kAgcModule = 0x80000094U;
constexpr std::size_t kCommandBytes = 0x20000;
constexpr std::size_t kCommandAlignment = 0x10000;
constexpr std::size_t kFenceOffset = 0x1100;
#ifdef STAGE_E_TRIANGLE
constexpr std::size_t kPreDrawFenceOffset = 0x1180;
constexpr std::size_t kPostWaitFenceOffset = 0x1200;
constexpr std::size_t kBootstrapFenceOffset = 0x1280;
extern "C" volatile std::uint32_t stage_e_runtime_checkpoint = 6;
/* Diagnostic build switch.  Keep the bootstrap transaction unchanged, then
 * submit only the native Wait(buffer 1) followed by SetFlip and the terminal
 * release fence.  This separates VideoOut ownership from pipeline/draw state. */
#ifdef STAGE_F_CUBE
extern "C" volatile std::uint32_t stage_e_wait_flip_isolation = 1;
#else
extern "C" volatile std::uint32_t stage_e_wait_flip_isolation = 0;
#endif
extern "C" volatile std::uint32_t stage_e_isolation_cx_count = 84;
#ifdef STAGE_G_DEPTH
extern "C" volatile std::uint32_t stage_g_depth_bind_enabled = 1;
extern "C" volatile std::uint32_t stage_g_depth_register_count =
#ifdef STAGE_G_DEPTH_ENABLE_TEST
    STAGE_G_DEPTH_REGISTER_COUNT;
#else
    STAGE_G_DSV_REGISTER_COUNT;
#endif
#endif
#ifdef STAGE_H_GEARS
constexpr std::size_t kShaderBytes = 0x40000;
#else
constexpr std::size_t kShaderBytes = 0x10000;
#endif
constexpr std::size_t kShaderAlignment = 0x4000;
constexpr std::size_t kVsHeaderOffset = 0x0000;
constexpr std::size_t kPsHeaderOffset = 0x0200;
constexpr std::size_t kVsCodeOffset = 0x1000;
constexpr std::size_t kPsCodeOffset = 0x1200;
constexpr std::size_t kLinkedCxOffset = 0x2000;
constexpr std::size_t kLinkedUcOffset = 0x2200;
constexpr std::size_t kPipelineOffset = 0x3000;
#ifdef STAGE_G_DEPTH
constexpr std::size_t kDepthRegisterOffset = 0x3e00;
#endif
constexpr std::size_t kShaderFooterBytes = 0x30;
#ifdef STAGE_F_CUBE
#ifndef STAGE_H_GEARS
constexpr std::size_t kCubeVertexOffset = 0x4000;
constexpr std::size_t kCubeSrdOffset = 0x5000;
constexpr std::size_t kGeometryFirstOffset = kCubeVertexOffset;
struct CubeVertex { float px, py, pz, nx, ny, nz; };
void cube_face(CubeVertex *&out, float ax, float ay, float az,
               float bx, float by, float bz, float cx, float cy, float cz,
               float dx, float dy, float dz, float nx, float ny, float nz) {
    const CubeVertex v[6] = {{ax,ay,az,nx,ny,nz},{bx,by,bz,nx,ny,nz},
        {cx,cy,cz,nx,ny,nz},{ax,ay,az,nx,ny,nz},{cx,cy,cz,nx,ny,nz},
        {dx,dy,dz,nx,ny,nz}};
    for (unsigned i=0;i<6;++i) *out++=v[i];
}
[[maybe_unused]] void build_cube(CubeVertex *out) {
    CubeVertex *p=out; const float n=-0.65f, q=0.65f;
    cube_face(p,n,n,q, q,n,q, q,q,q, n,q,q, 0,0,1);
    cube_face(p,q,n,n, n,n,n, n,q,n, q,q,n, 0,0,-1);
    cube_face(p,q,n,q, q,n,n, q,q,n, q,q,q, 1,0,0);
    cube_face(p,n,n,n, n,n,q, n,q,q, n,q,n, -1,0,0);
    cube_face(p,n,q,q, q,q,q, q,q,n, n,q,n, 0,1,0);
    cube_face(p,n,n,n, q,n,n, q,n,q, n,n,q, 0,-1,0);
}
#ifdef STAGE_G_DEPTH_LITMUS
void build_depth_litmus(CubeVertex *out) {
    /* Deliberately draw the near quad first and the far quad second.  With
     * depth disabled the dark far quad overwrites it; LESS_EQUAL preserves
     * the bright near quad.  Geometry, shaders and draw order are identical
     * between the g23off/g23on artifacts. */
    CubeVertex *p = out;
    const float n = -0.72f, q = 0.72f;
    cube_face(p, n,n,0.20f, q,n,0.20f, q,q,0.20f, n,q,0.20f,
              0.4f,0.7f,1.0f);
    cube_face(p, n,n,0.80f, q,n,0.80f, q,q,0.80f, n,q,0.80f,
              -0.4f,-0.7f,-1.0f);
}
#endif
std::uint32_t float_word(float value) { std::uint32_t v; memcpy(&v,&value,4); return v; }
#else
constexpr std::size_t kGearVertexOffsets[3] = {0x4000, 0x10000, 0x16000};
constexpr std::size_t kGearSrdOffset = 0x1c000;
constexpr std::size_t kClearSrdOffset = 0x1c100;
constexpr std::size_t kClearVertexOffset = 0x1c200;
constexpr std::size_t kGeometryFirstOffset = kGearVertexOffsets[0];
#endif
#ifdef STAGE_G_DEPTH
constexpr std::size_t kDepthBytes = 0x870000;
constexpr std::size_t kDepthAllocationBytes = 0x900000;
constexpr std::size_t kDepthAlignment = 0x10000;
static_assert(kDepthRegisterOffset +
                  STAGE_G_DEPTH_REGISTER_COUNT * sizeof(AgcRegister1202) <=
              kGeometryFirstOffset,
              "depth register table must precede GPU geometry");
#endif
#endif
#endif
/* sceVideoOutGetEventData returns the signed upper 48 bits of packed event
 * data, so a positive exact-match marker must stay within signed 48-bit range. */
constexpr std::uint64_t kFlipArg = UINT64_C(0x0000420000000001);
#ifdef STAGE_E_TRIANGLE
constexpr std::uint64_t kBootstrapFlipArg = UINT64_C(0x0000420000000000);
#endif
static_assert(kFlipArg <= UINT64_C(0x00007fffffffffff),
              "positive flip_arg must fit signed 48-bit VideoOut ABI");
#if defined(STAGE_D_VISIBLE_CLEAR) || defined(STAGE_E_TRIANGLE)
constexpr std::uint32_t kSelectedBuffer = 1;
#ifdef STAGE_H_GEARS
/* es2gears reference clear color: opaque black in BGRA8. */
constexpr std::uint32_t kInitialColor = UINT32_C(0xff000000);
#else
constexpr std::uint32_t kInitialColor = UINT32_C(0xff301020);
#endif
constexpr std::uint32_t kRecoveryColor = UINT32_C(0xff204080);
constexpr std::uint32_t kGuardWord = UINT32_C(0x51a6c3d9);
/* Red bootstrap, purple untouched target, green shader output: the three
 * phases remain visually unambiguous on BGRA8 VideoOut. */
constexpr std::uint32_t kGpuColor = UINT32_C(0xffff2020);
#else
constexpr std::uint32_t kSelectedBuffer = 0;
#endif
struct BatchEntry {
    void *address;
    std::int64_t physical;
    std::size_t length;
    std::uint8_t protection;
    std::uint8_t memory_type;
    std::uint16_t reserved;
    std::uint32_t operation;
};
struct Submit {
    const std::uint32_t *words;
    std::uint32_t count;
    std::uint8_t flag;
    std::uint8_t pad[3];
};
struct AgcCommandBuffer {
    std::uint32_t *bottom;
    std::uint32_t *top;
    std::uint32_t *up;
    std::uint32_t *down;
    std::uintptr_t callback;
    void *user_data;
    std::uint32_t reserved_dwords;
    std::uint32_t pad;
};
struct VideoBuffer {
    void *data;
    void *metadata;
    void *reserved0;
    void *reserved1;
};
struct VideoAttribute {
    std::uint8_t reserved[80];
};
struct Resources {
    std::uint64_t agc_state;
    void *command;
    std::int64_t command_physical;
    void *framebuffer;
    std::int64_t framebuffer_physical;
#ifdef STAGE_E_TRIANGLE
    void *shader;
    std::int64_t shader_physical;
#ifdef STAGE_G_DEPTH
    void *depth;
    std::int64_t depth_physical;
#endif
#endif
    void *equeue;
    std::int32_t video;
    bool agc_loaded;
    bool command_reserved;
    bool command_allocated;
    bool command_mapped;
    bool framebuffer_allocated;
    bool framebuffer_mapped;
#ifdef STAGE_E_TRIANGLE
    bool shader_allocated;
    bool shader_mapped;
#ifdef STAGE_G_DEPTH
    bool depth_allocated;
    bool depth_mapped;
#endif
#endif
    bool event_added;
    bool buffers_registered;
};

static_assert(sizeof(BatchEntry) == 0x20);
static_assert(offsetof(BatchEntry, protection) == 0x18);
static_assert(offsetof(BatchEntry, memory_type) == 0x19);
static_assert(offsetof(BatchEntry, operation) == 0x1c);
static_assert(sizeof(Submit) == 0x10);
static_assert(sizeof(AgcCommandBuffer) == 0x38);
static_assert(sizeof(VideoBuffer) == 0x20);
static_assert(sizeof(VideoAttribute) == 80);

volatile sig_atomic_t g_transaction_possible = 0;
Resources g_resources{};
char g_log_line[PS5LOG_MAX_LINE] {};
std::size_t g_log_line_bytes = 0;

std::size_t string_length(const char *value) {
    std::size_t size = 0;
    while (value[size]) ++size;
    return size;
}
void log_bytes(const void *value, std::size_t bytes) {
    const auto *input = static_cast<const char *>(value);
    for (std::size_t index = 0; index < bytes; ++index) {
        const char byte = input[index];
        if (byte == '\n') {
            g_log_line[g_log_line_bytes] = 0;
            (void)ps5log_line(PS5LOG_INFO, g_log_line);
            g_log_line_bytes = 0;
            continue;
        }
        if (byte == '\r') continue;
        if (g_log_line_bytes + 1 < sizeof(g_log_line)) {
            g_log_line[g_log_line_bytes++] = byte;
        } else {
            g_log_line[g_log_line_bytes] = 0;
            (void)ps5log_line(PS5LOG_ERR, g_log_line);
            (void)ps5log_line(PS5LOG_ERR, "LOG_LINE_TRUNCATED");
            g_log_line_bytes = 0;
        }
    }
}
void log_text(const char *value) {
    log_bytes(value, string_length(value));
}
void log_hex32(const char *label, int result) {
    static constexpr char digits[] = "0123456789abcdef";
    char value[11] = "0x00000000";
    std::uint32_t bits = static_cast<std::uint32_t>(result);
    for (int index = 9; index >= 2; --index) {
        value[index] = digits[bits & 15U];
        bits >>= 4;
    }
    log_text(label);
    log_bytes(value, 10);
    log_text("\n");
}
void log_hex64(const char *label, std::uint64_t bits) {
    static constexpr char digits[] = "0123456789abcdef";
    char value[19] = "0x0000000000000000";
    for (int index = 17; index >= 2; --index) {
        value[index] = digits[bits & 15U];
        bits >>= 4;
    }
    log_text(label);
    log_bytes(value, 18);
    log_text("\n");
}
std::uint64_t monotonic_ns() {
    struct timespec value {};
    (void)clock_gettime(CLOCK_MONOTONIC, &value);
    return static_cast<std::uint64_t>(value.tv_sec) * UINT64_C(1000000000) +
           static_cast<std::uint64_t>(value.tv_nsec);
}
void flush_gpu_data(const void *address, std::size_t bytes) {
    auto *line = static_cast<const std::uint8_t *>(address);
    const auto *end = line + bytes;
    for (; line < end; line += 64)
        __asm__ volatile("clflush (%0)" : : "r"(line) : "memory");
    __asm__ volatile("mfence" : : : "memory");
}
[[noreturn]] void park(const char *reason) {
    log_text("PARKED_STAGE_B_TRANSACTION reason=");
    log_text(reason);
    log_text("; retain process, AGC, VideoOut, buffers and mappings; DO_NOT_CLOSE_PPSA99998\n");
    ps5log_close("parked-retain");
    (void)alarm(0);
    for (;;) (void)pause();
}
void watchdog(int) {
    if (g_transaction_possible) park("watchdog after SetFlip boundary");
    log_text("AGC stage B exit result=124\n");
    _exit(124);
}
std::uint8_t out_of_space(AgcCommandBuffer *, std::uint32_t, void *) {
    return 0;
}
int set_flip_adapter(std::uint32_t **cursor, std::uint32_t capacity,
                     std::uint32_t driver_mode, std::int32_t handle,
                     std::int32_t buffer_index, std::uint32_t flip_mode,
                     std::uint64_t flip_arg) {
    if (!cursor || !*cursor || driver_mode != 0 || capacity == 0) return -1;
    AgcCommandBuffer command {*cursor, *cursor + capacity, *cursor,
                              *cursor + capacity,
                              reinterpret_cast<std::uintptr_t>(out_of_space),
                              nullptr, 0, 0};
    (void)sceAgcDcbSetFlip(&command, static_cast<std::uint32_t>(handle),
                           buffer_index, flip_mode,
                           static_cast<std::int64_t>(flip_arg));
    if (command.up <= *cursor || command.up > command.top) return -2;
    *cursor = command.up;
    return 0;
}
#ifdef STAGE_E_TRIANGLE
int draw_index_auto_adapter(std::uint32_t **cursor, std::uint32_t capacity,
                            std::uint32_t vertex_count,
                            std::uint64_t modifier) {
    if (!cursor || !*cursor || capacity == 0 || vertex_count == 0) return -1;
    AgcCommandBuffer command {*cursor, *cursor + capacity, *cursor,
                              *cursor + capacity,
                              reinterpret_cast<std::uintptr_t>(out_of_space),
                              nullptr, 0, 0};
    (void)sceAgcDcbDrawIndexAuto(&command, vertex_count, modifier);
    if (command.up <= *cursor || command.up > command.top) return -2;
    *cursor = command.up;
    return 0;
}
#ifdef STAGE_F_CUBE
int sh_direct_adapter(std::uint32_t **cursor, std::uint32_t capacity,
                      std::uint32_t offset, const std::uint32_t *values,
                      std::uint32_t count) {
    if (!cursor || !*cursor || !values || capacity < count + 2) return -1;
    AgcCommandBuffer command {*cursor, *cursor + capacity, *cursor,
                              *cursor + capacity,
                              reinterpret_cast<std::uintptr_t>(out_of_space),
                              nullptr, 0, 0};
    (void)sceAgcCbSetShRegisterRangeDirect(&command, offset, values, count);
    if (command.up <= *cursor || command.up > command.top) return -2;
    *cursor = command.up; return 0;
}
#ifdef STAGE_G_DEPTH
int dma_fill_adapter(std::uint32_t **cursor, std::uint32_t capacity,
                     void *destination, std::uint32_t word,
                     std::uint32_t bytes) {
    if (!cursor || !*cursor || capacity < 16) return -1;
    AgcCommandBuffer command {*cursor, *cursor + capacity, *cursor,
                              *cursor + capacity,
                              reinterpret_cast<std::uintptr_t>(out_of_space),
                              nullptr, 0, 0};
    (void)ps5AgcDcbFillL2Sync(&command, destination, word, bytes);
    if (command.up <= *cursor || command.up > command.top) return -2;
    *cursor=command.up; return 0;
}
#endif
#endif
using indirect_register_fn = std::uint32_t *(*)(void *, const void *,
                                                std::uint32_t);
int indirect_register_adapter(std::uint32_t **cursor, std::uint32_t capacity,
                              const void *registers, std::uint32_t count,
                              indirect_register_fn emit) {
    if (!cursor || !*cursor || !registers || capacity == 0 || count == 0)
        return -1;
#ifdef STAGE_G_DEPTH
    if (!stage_gpu_span_visible(g_resources.shader, kShaderBytes, registers,
                                static_cast<std::size_t>(count) *
                                    sizeof(AgcRegister1202)))
        return -3;
#endif
    AgcCommandBuffer command {*cursor, *cursor + capacity, *cursor,
                              *cursor + capacity,
                              reinterpret_cast<std::uintptr_t>(out_of_space),
                              nullptr, 0, 0};
    (void)emit(&command, registers, count);
    if (command.up <= *cursor || command.up > command.top) return -2;
    *cursor = command.up;
    return 0;
}
[[maybe_unused]] int cx_indirect_adapter(std::uint32_t **cursor, std::uint32_t capacity,
                        const void *registers, std::uint32_t count) {
    return indirect_register_adapter(cursor, capacity, registers, count,
                                     sceAgcDcbSetCxRegistersIndirect);
}
[[maybe_unused]] int uc_indirect_adapter(std::uint32_t **cursor, std::uint32_t capacity,
                        const void *registers, std::uint32_t count) {
    return indirect_register_adapter(cursor, capacity, registers, count,
                                     sceAgcDcbSetUcRegistersIndirect);
}
[[maybe_unused]] int sh_indirect_adapter(std::uint32_t **cursor, std::uint32_t capacity,
                        const void *registers, std::uint32_t count) {
    return indirect_register_adapter(cursor, capacity, registers, count,
                                     sceAgcDcbSetShRegistersIndirect);
}
int wait_rendering_adapter(std::uint32_t **cursor, std::uint32_t capacity,
                           std::uint32_t driver_mode, std::int32_t handle,
                           std::int32_t buffer_index) {
    if (!cursor || !*cursor || driver_mode != 0 || handle < 0) return -1;
    const std::uint32_t required =
        sceAgcDriverGetWaitRenderingPacketSizeInDwords();
    if (required == 0 || capacity < required) return -2;
    std::uint32_t *begin = *cursor;
    const std::uint32_t rc = sceAgcDriverWaitUntilSafeForRendering(
        cursor, required, 0, static_cast<std::uint32_t>(handle), buffer_index);
    if (rc != 0 || *cursor != begin + required) return -3;
    return 0;
}
#endif
int submit_adapter(const std::uint32_t *commands, std::uint32_t dwords,
                   void *opaque) {
    if (!commands || dwords == 0 || opaque != g_resources.command) return -1;
    flush_gpu_data(g_resources.command, kCommandBytes);
    Submit submit {commands, dwords, 0, {0, 0, 0}};
    return sceAgcDriverSubmitDcb(&submit);
}
#ifdef STAGE_I_ANIMATED
struct StageIContext {
    std::uint32_t *commands[2];
    std::uint32_t *cursor[2];
    volatile std::uint64_t *fence[2];
    StageEPipelineRegisters *pipelines[2];
    const AgcRegister1202 *depth_registers;
    GearsSceneDraw clear_draw;
    std::uint64_t draw_modifier;
    std::uint32_t flip_mode;
    std::uint32_t color_bytes;
    std::uint32_t depth_bytes;
};

StageIContext g_stage_i {};

int stage_i_compose(const GearsAnimationFrame *frame, void *) {
    if (!frame || frame->buffer >= 2 || !g_stage_i.commands[frame->buffer] ||
        !g_stage_i.pipelines[frame->buffer] || !g_stage_i.depth_registers)
        return -1;
    std::uint32_t *commands = g_stage_i.commands[frame->buffer];
    (void)memset(commands, 0, 0x1000);
    std::uint32_t *cursor = commands;
    std::uint32_t *const end = commands + 0x1000 / 4;
    int rc = wait_rendering_adapter(
        &cursor, static_cast<std::uint32_t>(end - cursor), 0,
        g_resources.video, static_cast<std::int32_t>(frame->buffer));
    if (rc != 0) return -10;
    void *color = static_cast<std::uint8_t *>(g_resources.framebuffer) +
                  frame->buffer * STAGE_B_BUFFER_STRIDE;
#ifndef STAGE_I_PIPELINE_CLEAR
    rc = dma_fill_adapter(&cursor, static_cast<std::uint32_t>(end - cursor),
                          color, kInitialColor, g_stage_i.color_bytes);
    if (rc != 0) return -11;
#else
    (void)color;
#endif
    rc = dma_fill_adapter(&cursor, static_cast<std::uint32_t>(end - cursor),
                          g_resources.depth, UINT32_C(0x3f800000),
                          g_stage_i.depth_bytes);
    if (rc != 0) return -12;
    rc = indirect_register_adapter(
        &cursor, static_cast<std::uint32_t>(end - cursor),
        g_stage_i.depth_registers, STAGE_G_DEPTH_REGISTER_COUNT,
        sceAgcDcbSetCxRegistersIndirect);
    if (rc != 0) return -13;
    StageEPipelineRegisters *pipeline = g_stage_i.pipelines[frame->buffer];
    rc = indirect_register_adapter(&cursor,
        static_cast<std::uint32_t>(end - cursor), pipeline->cx,
        STAGE_E_CX_REGISTER_COUNT, sceAgcDcbSetCxRegistersIndirect);
    if (rc != 0) return -14;
    rc = indirect_register_adapter(&cursor,
        static_cast<std::uint32_t>(end - cursor), pipeline->uc,
        STAGE_E_UC_REGISTER_COUNT, sceAgcDcbSetUcRegistersIndirect);
    if (rc != 0) return -15;
    rc = indirect_register_adapter(&cursor,
        static_cast<std::uint32_t>(end - cursor), pipeline->sh,
        STAGE_E_SH_REGISTER_COUNT, sceAgcDcbSetShRegistersIndirect);
    if (rc != 0) return -16;
#ifdef STAGE_I_PIPELINE_CLEAR
    GearsRendererComposeResult composed {};
    rc = gears_renderer_compose_frame(
        &cursor, end, &g_stage_i.clear_draw, frame->draws,
        g_stage_i.draw_modifier, sh_direct_adapter, draw_index_auto_adapter,
        &composed);
    if (rc != 0 || composed.draws != 4) return -18;
#else
    GearsDrawComposeResult composed {};
    rc = gears_compose_three_draws(
        &cursor, end, frame->draws, g_stage_i.draw_modifier,
        sh_direct_adapter, draw_index_auto_adapter, &composed);
    if (rc != 0 || composed.draws != GEARS_SCENE_DRAW_COUNT) return -17;
#endif
    g_stage_i.cursor[frame->buffer] = cursor;
    return 0;
}

int stage_i_submit(const GearsAnimationFrame *frame, void *) {
    if (!frame || frame->buffer >= 2 || !g_stage_i.cursor[frame->buffer] ||
        g_stage_i.cursor[frame->buffer] <= g_stage_i.commands[frame->buffer])
        return -1;
    const unsigned slot = frame->buffer;
    __atomic_store_n(g_stage_i.fence[slot], UINT64_C(1), __ATOMIC_RELEASE);
    stage_b_stream stream {g_stage_i.cursor[slot],
        g_stage_i.commands[slot] + 0x1000 / 4, nullptr, 0};
    /* The SetFlip builder itself is the irreversible boundary. The runner has
     * already moved this slot to SUBMITTED before entering this callback. */
    g_transaction_possible = 1;
    int rc = stage_b_compose_setflip_then_fence(
        &stream, set_flip_adapter, g_resources.video,
        static_cast<std::int32_t>(frame->buffer), g_stage_i.flip_mode,
        frame->token, reinterpret_cast<std::uintptr_t>(g_stage_i.fence[slot]));
    if (rc != STAGE_B_COMPOSE_OK) return -2;
    const std::uint32_t dwords = static_cast<std::uint32_t>(
        stream.cursor - g_stage_i.commands[slot]);
    return submit_adapter(g_stage_i.commands[slot], dwords, g_resources.command);
}

int stage_i_wait_gpu(const GearsAnimationFrame *frame, void *) {
    if (!frame || frame->buffer >= 2) return -1;
    volatile std::uint64_t *fence = g_stage_i.fence[frame->buffer];
    const std::uint64_t deadline = monotonic_ns() + UINT64_C(2000000000);
    while (__atomic_load_n(fence, __ATOMIC_ACQUIRE) != 0 &&
           monotonic_ns() < deadline) {
        struct timespec delay {0, 1000000};
        (void)nanosleep(&delay, nullptr);
    }
    return __atomic_load_n(fence, __ATOMIC_ACQUIRE) == 0 ? 0 : -1;
}

int stage_i_wait_videoout(const GearsAnimationFrame *frame,
                          std::uint64_t *observed_token, void *) {
    if (!frame || !observed_token) return -1;
    stage_b_completion_state completion {};
    int rc = stage_b_completion_begin(&completion, frame->token, 1);
    if (rc != STAGE_B_COMPLETION_WAITING) return -2;
    alignas(8) std::uint8_t event[32] {};
    stage_b_event_diagnostics diagnostics {};
    const std::uint64_t deadline = monotonic_ns() + UINT64_C(2000000000);
    for (;;) {
        stage_b_event_poll poll {
            g_resources.equeue, &event, g_stage_i.fence[frame->buffer], 10000, 0,
            monotonic_ns() >= deadline ? 1 : 0, &diagnostics,
        };
        rc = stage_b_poll_videoout_completion(&completion, &poll);
        if (rc == STAGE_B_COMPLETION_DONE) {
            *observed_token = frame->token;
            return 0;
        }
        if (rc < 0) return rc;
    }
}

void stage_i_telemetry(std::uint64_t frame,
                       const GearsTelemetrySnapshot *snapshot,
                       int terminal_error, void *) {
    if (!snapshot) return;
    log_text("STAGE_I_TELEMETRY_BEGIN\n");
    log_hex64("stage_i_frame=", frame);
    log_hex64("stage_i_frames_completed=", snapshot->frames_completed);
    log_hex64("stage_i_compose_ns_average=", snapshot->compose_ns_average);
    log_hex64("stage_i_gpu_wait_ns_average=", snapshot->gpu_wait_ns_average);
    log_hex64("stage_i_video_wait_ns_average=", snapshot->video_wait_ns_average);
    log_hex64("stage_i_deadline_misses=", snapshot->deadline_misses);
    log_hex64("stage_i_errors=", snapshot->errors);
    log_hex32("stage_i_terminal_error=", terminal_error);
    log_text("STAGE_I_TELEMETRY_END\n");
}
#endif
int cleanup_resources() {
    int first = 0;
    auto capture = [&first](const char *label, int result) {
        log_hex32(label, result);
        if (first == 0 && result != 0) first = result;
    };
    if (g_resources.buffers_registered) {
        int result = sceVideoOutUnregisterBuffers(g_resources.video, 0);
        log_hex32("videoout_unregister=", result);
        /* The currently scanned-out set may remain busy until VideoOutClose.
         * ProsperoTV's native teardown documents this exact firmware result.
         * Continue only for RESOURCE_BUSY; the handle is closed before any
         * framebuffer unmap. Every other unregister failure remains fatal. */
        if (result != 0 && static_cast<std::uint32_t>(result) !=
                               UINT32_C(0x80290009))
            return result;
        if (static_cast<std::uint32_t>(result) == UINT32_C(0x80290009))
            log_text("videoout_unregister_busy_deferred_to_close=true\n");
        if (result == 0) g_resources.buffers_registered = false;
    }
    if (g_resources.event_added) {
        int result = sceVideoOutDeleteFlipEvent(g_resources.equeue,
                                                g_resources.video);
        capture("videoout_delete_flip_event=", result);
        if (result != 0) return result;
        if (result == 0) g_resources.event_added = false;
    }
    if (g_resources.equeue) {
        int result = sceKernelDeleteEqueue(g_resources.equeue);
        capture("equeue_delete=", result);
        if (result != 0) return result;
        if (result == 0) g_resources.equeue = nullptr;
    }
    if (g_resources.video >= 0) {
        int result = sceVideoOutClose(g_resources.video);
        capture("videoout_close=", result);
        if (result != 0) return result;
        if (result == 0) {
            g_resources.video = -1;
            g_resources.buffers_registered = false;
        }
    }
    if (g_resources.framebuffer_mapped) {
        int result = sceKernelMunmap(g_resources.framebuffer,
                                     STAGE_B_DIRECT_BYTES);
        capture("framebuffer_unmap=", result);
        if (result != 0) return result;
        if (result == 0) g_resources.framebuffer_mapped = false;
    }
    if (g_resources.framebuffer_allocated) {
        int result = sceKernelReleaseDirectMemory(
            g_resources.framebuffer_physical, STAGE_B_DIRECT_BYTES);
        capture("framebuffer_release=", result);
        if (result != 0) return result;
        if (result == 0) g_resources.framebuffer_allocated = false;
    }
#ifdef STAGE_E_TRIANGLE
#ifdef STAGE_G_DEPTH
    if (g_resources.depth_mapped) {
        int result = sceKernelMunmap(g_resources.depth, kDepthAllocationBytes);
        capture("depth_unmap=", result);
        if (result != 0) return result;
        g_resources.depth_mapped = false;
    }
    if (g_resources.depth_allocated) {
        int result = sceKernelReleaseDirectMemory(g_resources.depth_physical,
                                                   kDepthAllocationBytes);
        capture("depth_release=", result);
        if (result != 0) return result;
        g_resources.depth_allocated = false;
    }
#endif
    if (g_resources.shader_mapped) {
        int result = sceKernelMunmap(g_resources.shader, kShaderBytes);
        capture("shader_unmap=", result);
        if (result != 0) return result;
        g_resources.shader_mapped = false;
    }
    if (g_resources.shader_allocated) {
        int result = sceKernelReleaseDirectMemory(g_resources.shader_physical,
                                                  kShaderBytes);
        capture("shader_release=", result);
        if (result != 0) return result;
        g_resources.shader_allocated = false;
    }
#endif
    if (g_resources.command_mapped) {
        BatchEntry entry {g_resources.command, 0, kCommandBytes, 0xf2, 0x0c,
                          0, 1};
        int processed = -1;
        int result = sceKernelBatchMap(&entry, 1, &processed);
        capture("command_batch_unmap=", result);
        log_hex32("command_batch_unmap_processed=", processed);
        if (result != 0 || processed != 1) {
            return result != 0 ? result : -1;
        } else {
            g_resources.command_mapped = false;
        }
    }
    if (g_resources.command_allocated) {
        int result = sceKernelReleaseDirectMemory(g_resources.command_physical,
                                                  kCommandBytes);
        capture("command_release=", result);
        if (result != 0) return result;
        if (result == 0) g_resources.command_allocated = false;
    }
    if (g_resources.command_reserved) {
        int result = sceKernelMunmap(g_resources.command, kCommandBytes);
        capture("command_virtual_release=", result);
        if (result != 0) return result;
        if (result == 0) g_resources.command_reserved = false;
    }
    if (g_resources.agc_loaded) {
        int result = sceSysmoduleUnloadModuleInternal(kAgcModule);
        capture("agc_unload=", result);
        if (result != 0) return result;
        if (result == 0) g_resources.agc_loaded = false;
    }
    return first;
}
[[noreturn]] void finish_pretransaction(int result) {
    int cleanup = cleanup_resources();
    if (cleanup != 0) park("pre-transaction cleanup failed");
    log_text("STAGE_B_PRE_TRANSACTION_CLEANUP_COMPLETE\n");
    log_hex32("AGC stage B exit result=", result);
    log_text("pre-submit clean failure; parked-safe; close exact title PPSA99998\n");
    ps5log_close("pre-submit-clean");
    (void)alarm(0);
    for (;;) (void)pause();
}
} // namespace

int main() {
    g_resources.command_physical = -1;
    g_resources.framebuffer_physical = -1;
#ifdef STAGE_E_TRIANGLE
    g_resources.shader_physical = -1;
#ifdef STAGE_G_DEPTH
    g_resources.depth_physical = -1;
#endif
#endif
    g_resources.video = -1;
    ps5log_config log_config {};
    ps5log_config_defaults(&log_config);
    const char *const log_paths[] = {"/app0/dev.conf"};
    const char *log_config_path = nullptr;
    const int log_config_result = ps5log_load_config(
        log_paths, 1, &log_config, &log_config_path);
    const std::uint64_t log_boot_token = monotonic_ns();
    const int log_init_result = log_config_result == 0
        ? ps5log_init(&log_config, "PPSA99998", "agc-native-sce",
                      log_boot_token)
        : 1;
    (void)signal(SIGALRM, watchdog);
    (void)signal(SIGSEGV, watchdog);
    (void)signal(SIGBUS, watchdog);
    (void)alarm(20);
    log_text("LOG_SCHEMA=3\n");
    log_text("LOG_TRANSPORT=ps5log/1 tcp structured\n");
    log_text("LOG_FS_SINKS=disabled\n");
    log_hex64("LOG_BOOT_MONOTONIC_NS=", log_boot_token);
    log_hex32("LOG_CONFIG_RESULT=", log_config_result);
    log_hex32("LOG_INIT_RESULT=", log_init_result);
    log_text(log_config_path ? "LOG_CONFIG=/app0/dev.conf\n"
                             : "LOG_CONFIG=unavailable\n");
#ifdef PS5LOG_TRANSPORT_SMOKE
    log_text("PS5LOG_NATIVE_TRANSPORT_SMOKE_COMPLETE\n");
    ps5log_close("transport-smoke");
    (void)alarm(0);
    return 0;
#endif
#ifdef STAGE_G_LOG_DIAGNOSTIC
    log_text("STAGE_G_LOG_DIAGNOSTIC_WINDOW_MS=5000\n");
    const std::uint64_t log_diagnostic_deadline =
        monotonic_ns() + UINT64_C(5000000000);
    while (monotonic_ns() < log_diagnostic_deadline) {}
#endif
#if defined(STAGE_H_GEARS)
#ifdef STAGE_I_ANIMATED
    log_text("AGC native Stage I v1; animated lit gears + D32 no-HTILE + exact per-frame ownership\n");
#else
    log_text("AGC native Stage H v1; three lit gears + D32 no-HTILE; offline gated\n");
#endif
#elif defined(STAGE_G_DEPTH)
#ifdef STAGE_G_DEPTH_LITMUS
#ifdef STAGE_G_DEPTH_ENABLE_TEST
    log_text("AGC native Stage G/23 ON v1; adversarial overlap + D32 LESS_EQUAL\n");
#else
    log_text("AGC native Stage G/23 OFF v1; adversarial overlap + D32 bind only\n");
#endif
#elif defined(STAGE_G_DEPTH_ENABLE_TEST)
    log_text("AGC native Stage G/22 v1; gfx1013 cube + D32 LESS_EQUAL depth test\n");
#else
    log_text("AGC native Stage G v1; gfx1013 cube + D32 no-HTILE + synchronized GPU clear\n");
#endif
#elif defined(STAGE_F_CUBE)
    log_text("AGC native Stage F v1; own gfx1013 cube shaders + vertex SRD + direct MVP; no depth\n");
#elif defined(STAGE_E_TRIANGLE)
    log_text("AGC native Stage E v1; own gfx1013 shaders + runtime defaults + fullscreen triangle; checkpoint-gated submit path\n");
#elif defined(STAGE_D_VISIBLE_CLEAR)
    log_text("AGC native Stage D v1; DMA_DATA solid clear + SetFlip + ownership fence + exact VideoOut event; no shaders or draw\n");
#else
    log_text("AGC native Stage B v1; CPU-fill selected buffer only; SetFlip + ownership fence; exact VideoOut event; no shaders or draw\n");
#endif

    int result = sceSysmoduleLoadModuleInternal(kAgcModule);
    log_hex32("agc_load=", result);
    if (result != 0) finish_pretransaction(10);
    g_resources.agc_loaded = true;
    result = sceAgcInit(&g_resources.agc_state, sizeof(g_resources.agc_state));
    log_hex32("agc_init=", result);
    if (result != 0) finish_pretransaction(11);

    result = sceKernelReserveVirtualRange(&g_resources.command, kCommandBytes,
                                          0, kCommandAlignment);
    log_hex32("command_virtual_reserve=", result);
    if (result != 0 || !g_resources.command) finish_pretransaction(12);
    g_resources.command_reserved = true;
    result = sceKernelAllocateMainDirectMemory(kCommandBytes,
                                               kCommandAlignment, 0x0c,
                                               &g_resources.command_physical);
    log_hex32("command_allocate=", result);
    if (result != 0) finish_pretransaction(13);
    g_resources.command_allocated = true;
    {
        BatchEntry entry {g_resources.command, g_resources.command_physical,
                          kCommandBytes, 0xf2, 0x0c, 0, 0};
        int processed = -1;
        result = sceKernelBatchMap(&entry, 1, &processed);
        log_hex32("command_batch_map=", result);
        log_hex32("command_batch_map_processed=", processed);
        if (result != 0 || processed != 1) park("command BatchMap ambiguous");
    }
    g_resources.command_mapped = true;
    (void)memset(g_resources.command, 0, kCommandBytes);

    g_resources.video = sceVideoOutOpen(0xff, 0, 0, nullptr);
    log_hex32("videoout_open=", g_resources.video);
    if (g_resources.video < 0) finish_pretransaction(14);
    result = sceKernelCreateEqueue(&g_resources.equeue, "agc stage b flip");
    log_hex32("equeue_create=", result);
    if (result != 0 || !g_resources.equeue) finish_pretransaction(15);
    result = sceVideoOutAddFlipEvent(g_resources.equeue, g_resources.video,
                                     nullptr);
    log_hex32("videoout_add_flip_event=", result);
    if (result != 0) finish_pretransaction(16);
    g_resources.event_added = true;
    result = sceVideoOutSetFlipRate(g_resources.video, 0);
    log_hex32("videoout_set_flip_rate=", result);
    if (result != 0) finish_pretransaction(17);

    stage_b_surface_plan plan {};
    result = stage_b_make_surface_plan(0, &plan);
    log_hex32("surface_plan=", result);
    if (result != 0 || plan.width != 1920 || plan.height != 1080)
        finish_pretransaction(18);
    result = sceKernelAllocateMainDirectMemory(
        STAGE_B_DIRECT_BYTES, STAGE_B_DIRECT_ALIGNMENT, STAGE_B_MEMORY_TYPE,
        &g_resources.framebuffer_physical);
    log_hex32("framebuffer_allocate=", result);
    if (result != 0) finish_pretransaction(19);
    g_resources.framebuffer_allocated = true;
    result = sceKernelMapDirectMemory(
        &g_resources.framebuffer, STAGE_B_DIRECT_BYTES, STAGE_B_MAP_PROTECTION,
        0, g_resources.framebuffer_physical, STAGE_B_DIRECT_ALIGNMENT);
    log_hex32("framebuffer_map=", result);
    if (result != 0 || !g_resources.framebuffer) finish_pretransaction(20);
    g_resources.framebuffer_mapped = true;

    auto *selected = reinterpret_cast<std::uint32_t *>(
        static_cast<std::uint8_t *>(g_resources.framebuffer) +
        kSelectedBuffer * STAGE_B_BUFFER_STRIDE);
#if defined(STAGE_D_VISIBLE_CLEAR) || defined(STAGE_E_TRIANGLE)
    auto *recovery = static_cast<std::uint32_t *>(g_resources.framebuffer);
    for (std::size_t index = 0; index < plan.tiled_footprint / 4; ++index)
        recovery[index] = kRecoveryColor;
    for (std::size_t index = 0; index < plan.tiled_footprint / 4; ++index)
        selected[index] = kInitialColor;
    auto *guard_before = reinterpret_cast<std::uint32_t *>(
        reinterpret_cast<std::uint8_t *>(selected) - 64);
    auto *guard_after = reinterpret_cast<std::uint32_t *>(
        reinterpret_cast<std::uint8_t *>(selected) + plan.tiled_footprint);
    for (std::size_t index = 0; index < 16; ++index) {
        guard_before[index] = kGuardWord;
        guard_after[index] = kGuardWord;
    }
    flush_gpu_data(recovery, plan.tiled_footprint);
    flush_gpu_data(guard_before, 64);
    flush_gpu_data(selected, plan.tiled_footprint);
    flush_gpu_data(guard_after, 64);
#ifdef STAGE_E_TRIANGLE
    log_text("STAGE_E_BUFFERS_INITIALIZED target=1 recovery=0 guards=64\n");
#else
    log_text("STAGE_D_BUFFERS_INITIALIZED target=1 recovery=0 guards=64\n");
#endif
#else
    for (std::size_t index = 0; index < plan.tiled_footprint / 4; ++index)
        selected[index] = UINT32_C(0xff804020);
    flush_gpu_data(selected, plan.tiled_footprint);
    log_text("selected_buffer_prefilled=true index=0 other_buffer_cpu_writes=0\n");
#endif
    VideoBuffer buffers[2] = {
        {g_resources.framebuffer, nullptr, nullptr, nullptr},
        {static_cast<std::uint8_t *>(g_resources.framebuffer) +
             STAGE_B_BUFFER_STRIDE,
         nullptr, nullptr, nullptr},
    };
    VideoAttribute attribute {};
    sceVideoOutSetBufferAttribute2(&attribute, STAGE_B_FORMAT_WORD, 0,
                                    plan.width, plan.height, 0, 0, 0);
    result = sceVideoOutRegisterBuffers2(g_resources.video, 0, 0, buffers, 2,
                                         &attribute, 0, nullptr);
    log_hex32("videoout_register_buffers=", result);
    if (result != 0) finish_pretransaction(21);
    g_resources.buffers_registered = true;

#ifdef STAGE_E_TRIANGLE
    StageEPipelineRegisters *pipeline = nullptr;
    std::uint64_t draw_modifier = 0;
#ifdef STAGE_F_CUBE
#ifdef STAGE_H_GEARS
    GearsSceneDraw gear_draws[GEARS_SCENE_DRAW_COUNT] {};
    std::uint32_t gear_tables[GEARS_SCENE_DRAW_COUNT] {};
    std::uint32_t gear_counts[GEARS_SCENE_DRAW_COUNT] {};
#ifdef STAGE_I_ANIMATED
    StageEPipelineRegisters *stage_i_pipelines[2] {};
    volatile std::uint32_t *stage_i_depth_guard = nullptr;
#endif
#else
    std::uint32_t cube_params[17] {};
#endif
#ifdef STAGE_G_DEPTH
    AgcRegister1202 *depth_registers = nullptr;
#endif
#endif
    result = sceKernelAllocateMainDirectMemory(
        kShaderBytes, kShaderAlignment, 0x0c, &g_resources.shader_physical);
    log_hex32("shader_allocate=", result);
    if (result != 0) finish_pretransaction(22);
    g_resources.shader_allocated = true;
    result = sceKernelMapDirectMemory(&g_resources.shader, kShaderBytes, 0x33,
                                      0, g_resources.shader_physical,
                                      kShaderAlignment);
    log_hex32("shader_map=", result);
    if (result != 0 || !g_resources.shader) finish_pretransaction(23);
    g_resources.shader_mapped = true;
    {
        auto *base = static_cast<std::uint8_t *>(g_resources.shader);
        (void)memset(base, 0, kShaderBytes);
#ifdef STAGE_G_DEPTH
        depth_registers = reinterpret_cast<AgcRegister1202 *>(
            base + kDepthRegisterOffset);
#endif
        auto *vs_arena = reinterpret_cast<StageEShaderArena *>(base + kVsHeaderOffset);
        auto *ps_arena = reinterpret_cast<StageEShaderArena *>(base + kPsHeaderOffset);
        auto *vs_code = base + kVsCodeOffset;
        auto *ps_code = base + kPsCodeOffset;
        const std::size_t vs_isa = stage_e_gs_end - stage_e_gs_start;
        const std::size_t ps_isa = stage_e_ps_end - stage_e_ps_start;
        const std::size_t vs_size = vs_isa + kShaderFooterBytes;
        const std::size_t ps_size = ps_isa + kShaderFooterBytes;
        if (vs_isa != STAGE_E_GS_ISA_BYTES ||
            ps_isa != STAGE_E_PS_ISA_BYTES ||
            stage_e_build_shader_header(vs_arena, STAGE_E_SHADER_PRE_RASTER,
                                        static_cast<std::uint32_t>(vs_size)) != 0 ||
            stage_e_build_shader_header(ps_arena, STAGE_E_SHADER_PIXEL,
                                        static_cast<std::uint32_t>(ps_size)) != 0)
            finish_pretransaction(24);
        (void)memcpy(vs_code, stage_e_gs_start, vs_isa);
        (void)memcpy(ps_code, stage_e_ps_start, ps_isa);
        (void)memcpy(vs_code + vs_size - kShaderFooterBytes, "barefoot", 8);
        (void)memcpy(ps_code + ps_size - kShaderFooterBytes, "barefoot", 8);
        void *vs_object = nullptr;
        void *ps_object = nullptr;
        result = sceAgcCreateShader(&vs_object, vs_arena, vs_code);
        log_hex32("stage_e_create_pre_raster=", result);
        if (result != 0 || !vs_object) finish_pretransaction(25);
        result = sceAgcCreateShader(&ps_object, ps_arena, ps_code);
        log_hex32("stage_e_create_pixel=", result);
        if (result != 0 || !ps_object) finish_pretransaction(26);
        const bool shader_aliases_own_headers =
            vs_object == vs_arena && ps_object == ps_arena;
        const bool shader_objects_distinct = vs_object != ps_object;
        const bool shader_code_bound =
            vs_arena->header.code == vs_code && ps_arena->header.code == ps_code;
        log_text(shader_aliases_own_headers
                     ? "stage_e_shader_aliases_own_headers=true\n"
                     : "stage_e_shader_aliases_own_headers=false\n");
        log_text(shader_objects_distinct
                     ? "stage_e_shader_objects_distinct=true\n"
                     : "stage_e_shader_objects_distinct=false\n");
        log_text(shader_code_bound
                     ? "stage_e_shader_code_bound=true\n"
                     : "stage_e_shader_code_bound=false\n");
        if (!shader_aliases_own_headers || !shader_objects_distinct ||
            !shader_code_bound)
            finish_pretransaction(37);
        auto *linked_cx = reinterpret_cast<AgcLinkedCx1202 *>(base + kLinkedCxOffset);
        auto *linked_uc = reinterpret_cast<AgcLinkedUc1202 *>(base + kLinkedUcOffset);
        result = sceAgcLinkShaders(linked_cx, linked_uc, nullptr, vs_object,
                                   ps_object, 4);
        log_hex32("stage_e_link=", result);
        if (result != 0) finish_pretransaction(27);
        auto *vs_header = static_cast<AgcShaderHeader *>(vs_object);
        auto *ps_header = static_cast<AgcShaderHeader *>(ps_object);
        if (!vs_header->cx_registers || !ps_header->cx_registers ||
            !vs_header->sh_registers || !ps_header->sh_registers ||
            !vs_header->specials || vs_header->num_sh_registers != 6 ||
            ps_header->num_sh_registers != 6 ||
            vs_header->num_cx_registers != STAGE_E_PRE_RASTER_CX_REGISTER_COUNT ||
            ps_header->num_cx_registers != STAGE_E_PIXEL_CX_REGISTER_COUNT ||
            vs_header->type != STAGE_E_SHADER_PRE_RASTER ||
            ps_header->type != STAGE_E_SHADER_PIXEL)
            finish_pretransaction(28);
        AgcRegister1202 defaults[STAGE_E_RT_REGISTER_COUNT];
        AgcRegister1202 render_target[STAGE_E_RT_REGISTER_COUNT];
        const auto *runtime_defaults = static_cast<const AgcRegisterDefaults *>(
            sceAgcGetRegisterDefaults());
        std::uint32_t runtime_color_index = UINT32_MAX;
        result = stage_e_find_runtime_color_default_index(
            runtime_defaults, &runtime_color_index);
        log_hex32("stage_e_runtime_default_index_result=", result);
        log_hex32("stage_e_runtime_default_index=",
                  static_cast<int>(runtime_color_index));
        if (result != 0) finish_pretransaction(29);
        if (stage_e_runtime_checkpoint == 1) {
            log_text("STAGE_E_CHECKPOINT_DEFAULT_INDEX_COMPLETE no block read; no DCB; no submit\n");
            finish_pretransaction(32);
        }
        result = stage_e_select_runtime_color_defaults(defaults,
                                                        runtime_defaults);
        log_hex32("stage_e_runtime_defaults=", result);
        if (result != 0) finish_pretransaction(29);
        if (stage_e_runtime_checkpoint == 2) {
            log_text("STAGE_E_CHECKPOINT_DEFAULT_BLOCK_COMPLETE offsets=16; no DCB; no submit\n");
            finish_pretransaction(33);
        }
        result = stage_e_build_color_target(
            render_target, defaults, reinterpret_cast<std::uintptr_t>(selected),
            plan.width, plan.height);
        log_hex32("stage_e_color_target=", result);
        if (result != 0) finish_pretransaction(30);
        if (stage_e_runtime_checkpoint == 3) {
            log_text("STAGE_E_CHECKPOINT_COLOR_TARGET_COMPLETE registers=16; no pipeline; no DCB; no submit\n");
            finish_pretransaction(34);
        }
        pipeline = reinterpret_cast<StageEPipelineRegisters *>(base + kPipelineOffset);
#ifdef STAGE_I_ANIMATED
        /* Keep the proven buffer-1 pipeline at its original address and place
         * buffer 0 immediately after it; both fit before geometry at 0x4000. */
        stage_i_pipelines[1] = pipeline;
        stage_i_pipelines[0] = pipeline + 1;
        static_assert(kPipelineOffset + 2 * sizeof(StageEPipelineRegisters) <=
                      kGearVertexOffsets[0]);
#endif
        result = stage_e_build_pipeline_registers(
            pipeline, render_target, linked_cx, linked_uc,
            reinterpret_cast<const AgcRegister1202 *>(vs_header->cx_registers),
            reinterpret_cast<const AgcRegister1202 *>(ps_header->cx_registers),
            reinterpret_cast<const AgcRegister1202 *>(vs_header->sh_registers),
            reinterpret_cast<const AgcRegister1202 *>(ps_header->sh_registers),
            plan.width, plan.height);
        log_hex32("stage_e_pipeline=", result);
        if (result != 0) finish_pretransaction(31);
#ifdef STAGE_I_ANIMATED
        AgcRegister1202 render_target0[STAGE_E_RT_REGISTER_COUNT];
        result = stage_e_build_color_target(
            render_target0, defaults,
            reinterpret_cast<std::uintptr_t>(g_resources.framebuffer),
            plan.width, plan.height);
        log_hex32("stage_i_color_target0=", result);
        if (result != 0) finish_pretransaction(44);
        result = stage_e_build_pipeline_registers(
            stage_i_pipelines[0], render_target0, linked_cx, linked_uc,
            reinterpret_cast<const AgcRegister1202 *>(vs_header->cx_registers),
            reinterpret_cast<const AgcRegister1202 *>(ps_header->cx_registers),
            reinterpret_cast<const AgcRegister1202 *>(vs_header->sh_registers),
            reinterpret_cast<const AgcRegister1202 *>(ps_header->sh_registers),
            plan.width, plan.height);
        log_hex32("stage_i_pipeline0=", result);
        if (result != 0) finish_pretransaction(45);
        log_text("STAGE_I_DOUBLE_PIPELINE_READY buffers=2\n");
#endif
        if (stage_e_runtime_checkpoint == 4) {
            log_text("STAGE_E_CHECKPOINT_PIPELINE_COMPLETE registers=84/12/3; no DCB; no submit\n");
            finish_pretransaction(35);
        }
        draw_modifier = static_cast<StageEShaderSpecials *>(
                            vs_header->specials)->draw_modifier;
        log_hex64("stage_e_draw_modifier=", draw_modifier);
#ifdef STAGE_F_CUBE
#ifdef STAGE_H_GEARS
        const GearSpec gear_specs[3] = {
            {0.2500f, 0.9125f, 1.0875f, 0.250f, 20},
            {0.1250f, 0.4125f, 0.5875f, 0.500f, 10},
            {0.3250f, 0.4125f, 0.5875f, 0.125f, 10},
        };
        for (unsigned gear = 0; gear < 3; ++gear) {
            auto *vertices = reinterpret_cast<GearsVertex *>(
                base + kGearVertexOffsets[gear]);
            const std::size_t capacity =
                gears_mesh_vertex_count(gear_specs[gear].teeth);
            const std::size_t emitted =
                gears_build_mesh(vertices, capacity, &gear_specs[gear]);
            if (emitted != capacity || emitted > UINT32_MAX)
                finish_pretransaction(41);
            auto *srd = reinterpret_cast<std::uint32_t *>(
                base + kGearSrdOffset + gear * 16);
            const std::uintptr_t vertex_address =
                reinterpret_cast<std::uintptr_t>(vertices);
            const std::uintptr_t table_address =
                reinterpret_cast<std::uintptr_t>(srd);
            /* IndirectUserDataVaPtr is one DWORD on this linked pipeline.  FW
             * 12.02 reconstructs it inside the 0x2 GPU direct-memory aperture,
             * as already demonstrated by Stage F/G.  Reject a different
             * aperture instead of incorrectly requiring a full VA below 4 GiB. */
            if ((table_address >> 32) != UINT64_C(2))
                finish_pretransaction(42);
            srd[0] = static_cast<std::uint32_t>(vertex_address);
            srd[1] = static_cast<std::uint32_t>(
                (vertex_address >> 32) & 0xffffu) | (24u << 16);
            srd[2] = static_cast<std::uint32_t>(emitted);
            srd[3] = UINT32_C(0x11014fac);
            gear_tables[gear] = static_cast<std::uint32_t>(table_address);
            gear_counts[gear] = static_cast<std::uint32_t>(emitted);
        }
        result = gears_build_scene(gear_draws, 0.0f, gear_tables, gear_counts);
        log_hex32("stage_h_scene_build=", result);
        if (result != 0) finish_pretransaction(43);
        log_text("STAGE_H_GEOMETRY_READY draws=3 vertices=1200,600,600 stride=24 topology=es2gears\n");
#ifdef STAGE_I_PIPELINE_CLEAR
        auto *clear_vertices = reinterpret_cast<GearsRtClearVertex *>(
            base + kClearVertexOffset);
        auto *clear_srd = reinterpret_cast<std::uint32_t *>(
            base + kClearSrdOffset);
        const std::uintptr_t clear_vertex_address =
            reinterpret_cast<std::uintptr_t>(clear_vertices);
        const std::uintptr_t clear_table_address =
            reinterpret_cast<std::uintptr_t>(clear_srd);
        if ((clear_table_address >> 32) != UINT64_C(2))
            finish_pretransaction(47);
        clear_srd[0] = static_cast<std::uint32_t>(clear_vertex_address);
        clear_srd[1] = static_cast<std::uint32_t>(
            (clear_vertex_address >> 32) & 0xffffu) | (24u << 16);
        clear_srd[2] = GEARS_RT_CLEAR_VERTEX_COUNT;
        clear_srd[3] = UINT32_C(0x11014fac);
#ifdef STAGE_I_CLEAR_PROOF
        const float clear_rgba[4] = {0.0f, 0.55f, 0.05f, 1.0f};
#else
        const float clear_rgba[4] = {0.0f, 0.0f, 0.0f, 1.0f};
#endif
        result = gears_rt_clear_build(clear_vertices, &g_stage_i.clear_draw,
            static_cast<std::uint32_t>(clear_table_address), clear_rgba);
        log_hex32("stage_i_rt_clear_build=", result);
        if (result != 0) finish_pretransaction(48);
        log_text("STAGE_I_RT_CLEAR_READY method=fullscreen_triangle vertices=3 color_dma=false\n");
#endif
#else
        auto *vertices = reinterpret_cast<CubeVertex *>(base + kCubeVertexOffset);
        auto *srd = reinterpret_cast<std::uint32_t *>(base + kCubeSrdOffset);
#ifdef STAGE_G_DEPTH_LITMUS
        build_depth_litmus(vertices);
#else
        build_cube(vertices);
#endif
        const std::uintptr_t vertex_address = reinterpret_cast<std::uintptr_t>(vertices);
        const std::uintptr_t table_address = reinterpret_cast<std::uintptr_t>(srd);
        srd[0]=static_cast<std::uint32_t>(vertex_address);
        srd[1]=static_cast<std::uint32_t>((vertex_address>>32)&0xffffu)|(24u<<16);
        srd[2]=
#ifdef STAGE_G_DEPTH_LITMUS
            12;
#else
            36;
#endif
        srd[3]=UINT32_C(0x11014fac);
#ifdef STAGE_G_DEPTH_LITMUS
        const float m[16] = {
          0.72f,0.0f,0.0f,0.0f, 0.0f,0.72f,0.0f,0.0f,
          0.0f,0.0f,1.0f,0.0f, 0.0f,0.0f,0.0f,1.0f};
#else
        const float m[16] = {
          0.72f,0.18f,0.10f,0.0f, -0.10f,0.78f,0.18f,0.0f,
          0.42f,-0.28f,0.45f,0.0f, 0.0f,0.0f,0.45f,1.0f};
#endif
        for (unsigned i=0;i<16;++i) cube_params[i]=float_word(m[i]);
        cube_params[16]=static_cast<std::uint32_t>(table_address);
        log_hex64("stage_f_vertex_address=", vertex_address);
        log_hex64("stage_f_srd_table_address=", table_address);
#ifdef STAGE_G_DEPTH_LITMUS
        log_text("STAGE_G23_LITMUS_READY vertices=12 near_first=true far_second=true expected_off=dark expected_on=bright\n");
#else
        log_text("STAGE_F_CUBE_DATA_READY vertices=36 stride=24 srd=1 params=17\n");
#endif
#endif
#ifdef STAGE_G_DEPTH
        result = sceKernelAllocateMainDirectMemory(kDepthAllocationBytes,
            kDepthAlignment, 0x0c, &g_resources.depth_physical);
        log_hex32("stage_g_depth_allocate=", result);
        if (result != 0) finish_pretransaction(38);
        g_resources.depth_allocated=true;
        result = sceKernelMapDirectMemory(&g_resources.depth,
            kDepthAllocationBytes, 0x33, 0, g_resources.depth_physical,
            kDepthAlignment);
        log_hex32("stage_g_depth_map=", result);
        if (result != 0 || !g_resources.depth) finish_pretransaction(39);
        g_resources.depth_mapped=true;
        const std::uintptr_t za=reinterpret_cast<std::uintptr_t>(g_resources.depth);
        result = stage_g_build_d32_no_htile(depth_registers, za, 1920, 1080);
        log_hex32("stage_g_depth_state_build=", result);
        if (result != 0) finish_pretransaction(40);
        log_hex64("stage_g_depth_address=",za);
        log_text("STAGE_G_DEPTH_READY bytes=0x870000 swizzle=64KB_Z_X htile=false\n");
#ifdef STAGE_I_ANIMATED
        stage_i_depth_guard = reinterpret_cast<volatile std::uint32_t *>(
            static_cast<std::uint8_t *>(g_resources.depth) + kDepthBytes);
        for (unsigned index = 0; index < 16; ++index)
            stage_i_depth_guard[index] = kGuardWord;
        flush_gpu_data(const_cast<std::uint32_t *>(stage_i_depth_guard), 64);
        log_text("STAGE_I_DEPTH_GUARD_READY bytes=64\n");
#endif
#endif
#endif
        flush_gpu_data(g_resources.shader, kShaderBytes);
        log_text("STAGE_E_PREFLIGHT_COMPLETE own_shaders=true target=gfx1013 runtime_defaults=true registers=84/12/3\n");
    }
#endif

    auto *command_words = static_cast<std::uint32_t *>(g_resources.command);
    auto *fence = reinterpret_cast<volatile std::uint64_t *>(
        static_cast<std::uint8_t *>(g_resources.command) + kFenceOffset);
#ifdef STAGE_E_TRIANGLE
#ifdef STAGE_I_ANIMATED
    g_stage_i.commands[0] = command_words;
    /* 0x1000..0x1fff contains both per-slot fences and bootstrap labels. */
    g_stage_i.commands[1] = command_words + 0x2000 / 4;
    g_stage_i.cursor[0] = nullptr;
    g_stage_i.cursor[1] = nullptr;
    g_stage_i.fence[0] = fence;
    g_stage_i.fence[1] = reinterpret_cast<volatile std::uint64_t *>(
        static_cast<std::uint8_t *>(g_resources.command) + kPostWaitFenceOffset);
    g_stage_i.pipelines[0] = stage_i_pipelines[0];
    g_stage_i.pipelines[1] = stage_i_pipelines[1];
    g_stage_i.depth_registers = depth_registers;
    g_stage_i.draw_modifier = draw_modifier;
    g_stage_i.flip_mode = plan.flip_mode;
    g_stage_i.color_bytes = static_cast<std::uint32_t>(plan.tiled_footprint);
    g_stage_i.depth_bytes = static_cast<std::uint32_t>(kDepthBytes);
    GearsFrameRunnerInput runner_input {};
    runner_input.start_ns = monotonic_ns();
    runner_input.first_flip_token = kFlipArg;
    runner_input.frame_deadline_ns = UINT64_C(16666667);
    runner_input.frame_count = STAGE_I_FRAME_COUNT;
    for (unsigned gear = 0; gear < GEARS_SCENE_DRAW_COUNT; ++gear) {
        runner_input.srd_tables[gear] = gear_tables[gear];
        runner_input.vertex_counts[gear] = gear_counts[gear];
    }
    runner_input.now_ns = [](void *) -> std::uint64_t { return monotonic_ns(); };
    runner_input.compose = stage_i_compose;
    runner_input.submit = stage_i_submit;
    runner_input.wait_gpu = stage_i_wait_gpu;
    runner_input.wait_videoout = stage_i_wait_videoout;
    runner_input.telemetry = stage_i_telemetry;
    GearsFrameRunnerResult runner_result {};
    (void)alarm(static_cast<unsigned>(STAGE_I_FRAME_COUNT / 50 + 60));
    log_text("STAGE_I_LOOP_BEGIN buffers=2 depth_registers=22\n");
    log_hex32("stage_i_frames_requested=", STAGE_I_FRAME_COUNT);
    result = gears_run_frames(&runner_input, &runner_result);
    log_hex32("stage_i_runner_result=", result);
    log_hex32("stage_i_runner_state=", static_cast<int>(runner_result.state));
    log_hex32("stage_i_frames_completed=",
              static_cast<int>(runner_result.frames_completed));
    log_hex32("stage_i_max_frames_in_flight=",
              static_cast<int>(runner_result.max_frames_in_flight));
    log_hex64("stage_i_loop_elapsed_ns=", runner_result.loop_elapsed_ns);
    log_hex64("stage_i_frame_interval_ns_average=",
              runner_result.frame_interval_ns_average);
    if (result == 1) finish_pretransaction(46);
    if (result != 0 || runner_result.state != GEARS_RUN_COMPLETE ||
        runner_result.frames_completed != runner_input.frame_count)
        park("Stage I post-submit frame-loop failure");
    if (__atomic_load_n(g_stage_i.fence[0], __ATOMIC_ACQUIRE) != 0 ||
        __atomic_load_n(g_stage_i.fence[1], __ATOMIC_ACQUIRE) != 0)
        park("Stage I terminal fence not zero");
    log_text("STAGE_I_GPU_FENCE_ZERO\n");
    log_hex64("stage_i_final_flip_arg=",
              kFlipArg + runner_input.frame_count - 1);
    log_text("STAGE_I_VIDEOOUT_EVENT_EXACT\n");
    for (unsigned index = 0; index < 16; ++index) {
        if (guard_before[index] != kGuardWord ||
            guard_after[index] != kGuardWord ||
            stage_i_depth_guard[index] != kGuardWord)
            park("Stage I render/depth guard corruption");
    }
    log_text("STAGE_I_GUARDS_INTACT color=true depth=true\n");
    log_text("STAGE_I_LOOP_COMPLETE\n");
    log_hex32("stage_i_frames_verified=", STAGE_I_FRAME_COUNT);
    log_text("STAGE_I_VISIBLE_HOLD_STARTED\n");
    log_hex32("stage_i_visible_hold_seconds=", STAGE_I_VISIBLE_HOLD_SECONDS);
    { struct timespec visible {STAGE_I_VISIBLE_HOLD_SECONDS, 0};
      (void)nanosleep(&visible, nullptr); }
    log_text("STAGE_I_VISIBLE_HOLD_COMPLETE\n");
#else
    auto *bootstrap_fence = reinterpret_cast<volatile std::uint64_t *>(
        static_cast<std::uint8_t *>(g_resources.command) + kBootstrapFenceOffset);
    const std::uintptr_t bootstrap_destination =
        reinterpret_cast<std::uintptr_t>(recovery);
    const std::uint32_t bootstrap_dma[7] = {
        UINT32_C(0xc0055000), UINT32_C(0xc0300000), kGpuColor, 0,
        static_cast<std::uint32_t>(bootstrap_destination),
        static_cast<std::uint32_t>(bootstrap_destination >> 32),
        static_cast<std::uint32_t>(plan.tiled_footprint),
    };
    for (std::size_t index = 0; index < 7; ++index)
        command_words[index] = bootstrap_dma[index];
    __atomic_store_n(bootstrap_fence, UINT64_C(1), __ATOMIC_RELEASE);
    stage_b_stream bootstrap_stream {command_words + 7,
                                     command_words + 0x1000 / 4, nullptr, 0};
    result = stage_b_compose_setflip_then_fence(
        &bootstrap_stream, set_flip_adapter, g_resources.video, 0,
        plan.flip_mode, kBootstrapFlipArg,
        reinterpret_cast<std::uintptr_t>(bootstrap_fence));
    log_hex32("stage_e_bootstrap_compose=", result);
    if (result != STAGE_B_COMPOSE_OK) park("Stage E bootstrap compose failed");
    result = submit_adapter(command_words,
        static_cast<std::uint32_t>(bootstrap_stream.cursor - command_words),
        g_resources.command);
    log_hex32("stage_e_bootstrap_submit=", result);
    if (result != 0) park("Stage E bootstrap submit failed");
    {
        const std::uint64_t deadline = monotonic_ns() + UINT64_C(2000000000);
        while (__atomic_load_n(bootstrap_fence, __ATOMIC_ACQUIRE) != 0 &&
               monotonic_ns() < deadline) {
            struct timespec delay {0, 1000000};
            (void)nanosleep(&delay, nullptr);
        }
        if (__atomic_load_n(bootstrap_fence, __ATOMIC_ACQUIRE) != 0)
            park("Stage E bootstrap fence timeout");
    }
    stage_b_completion_state bootstrap_completion {};
    result = stage_b_completion_begin(&bootstrap_completion,
                                      kBootstrapFlipArg, 1);
    if (result != STAGE_B_COMPLETION_WAITING)
        park("Stage E bootstrap completion begin failed");
    alignas(8) std::uint8_t bootstrap_event[32] {};
    stage_b_event_diagnostics bootstrap_diagnostics {};
    const std::uint64_t bootstrap_event_deadline =
        monotonic_ns() + UINT64_C(2000000000);
    for (;;) {
        stage_b_event_poll poll {
            g_resources.equeue, &bootstrap_event, bootstrap_fence, 10000, 0,
            monotonic_ns() >= bootstrap_event_deadline ? 1 : 0,
            &bootstrap_diagnostics,
        };
        result = stage_b_poll_videoout_completion(&bootstrap_completion, &poll);
        if (result == STAGE_B_COMPLETION_DONE) break;
        if (result < 0) park("Stage E bootstrap VideoOut timeout");
    }
    log_text("STAGE_E_BOOTSTRAP_COMPLETE buffer=0 fence=true event=true\n");
    (void)memset(command_words, 0, 0x1000);
    auto *pre_draw_fence = reinterpret_cast<volatile std::uint64_t *>(
        static_cast<std::uint8_t *>(g_resources.command) + kPreDrawFenceOffset);
    auto *post_wait_fence = reinterpret_cast<volatile std::uint64_t *>(
        static_cast<std::uint8_t *>(g_resources.command) + kPostWaitFenceOffset);
    __atomic_store_n(post_wait_fence, UINT64_C(1), __ATOMIC_RELEASE);
    __atomic_store_n(pre_draw_fence, UINT64_C(1), __ATOMIC_RELEASE);
    __atomic_store_n(fence, UINT64_C(1), __ATOMIC_RELEASE);
    if (stage_e_wait_flip_isolation != 0) {
        std::uint32_t *cursor = command_words;
        result = wait_rendering_adapter(
            &cursor, static_cast<std::uint32_t>(0x1000 / 4), 0,
            g_resources.video, static_cast<std::int32_t>(kSelectedBuffer));
        log_hex32("stage_e_wait_flip_wait=", result);
        if (result != 0) park("Stage E wait-flip wait compose failed");
#ifdef STAGE_G_DEPTH
        result = dma_fill_adapter(&cursor, static_cast<std::uint32_t>(
            (command_words + 0x1000 / 4) - cursor), g_resources.depth,
            UINT32_C(0x3f800000), static_cast<std::uint32_t>(kDepthBytes));
        log_hex32("stage_g_depth_clear=", result);
        if (result != 0) park("Stage G depth clear compose failed");
        if (stage_g_depth_bind_enabled != 0) {
            result = indirect_register_adapter(&cursor, static_cast<std::uint32_t>(
                (command_words + 0x1000 / 4) - cursor), depth_registers,
                stage_g_depth_register_count, sceAgcDcbSetCxRegistersIndirect);
            log_hex32("stage_g_depth_bind=", result);
            log_hex32("stage_g_depth_register_count=",
                      static_cast<int>(stage_g_depth_register_count));
            if (result != 0) park("Stage G depth bind compose failed");
        } else log_text("stage_g_depth_bind=disabled-control\n");
#endif
        result = indirect_register_adapter(
            &cursor, static_cast<std::uint32_t>(
                (command_words + 0x1000 / 4) - cursor),
            pipeline->cx, stage_e_isolation_cx_count,
            sceAgcDcbSetCxRegistersIndirect);
        log_hex32("stage_e_isolation_cx=", result);
        log_hex32("stage_e_isolation_cx_count=",
                  static_cast<int>(stage_e_isolation_cx_count));
        if (result != STAGE_E_DCB_OK)
            park("Stage E CX isolation compose failed");
        result = indirect_register_adapter(
            &cursor, static_cast<std::uint32_t>(
                (command_words + 0x1000 / 4) - cursor),
            pipeline->uc, STAGE_E_UC_REGISTER_COUNT,
            sceAgcDcbSetUcRegistersIndirect);
        log_hex32("stage_e_isolation_uc=", result);
        if (result != 0) park("Stage E UC isolation compose failed");
        result = indirect_register_adapter(
            &cursor, static_cast<std::uint32_t>(
                (command_words + 0x1000 / 4) - cursor),
            pipeline->sh, STAGE_E_SH_REGISTER_COUNT,
            sceAgcDcbSetShRegistersIndirect);
        log_hex32("stage_e_isolation_sh=", result);
        if (result != 0) park("Stage E SH isolation compose failed");
#ifdef STAGE_F_CUBE
#ifdef STAGE_H_GEARS
        GearsDrawComposeResult gear_compose {};
        result = gears_compose_three_draws(
            &cursor, command_words + 0x1000 / 4, gear_draws, draw_modifier,
            sh_direct_adapter, draw_index_auto_adapter, &gear_compose);
        log_hex32("stage_h_three_draw_compose=", result);
        log_hex32("stage_h_draw_count=", static_cast<int>(gear_compose.draws));
        log_hex32("stage_h_draw_dwords=",
                  static_cast<int>(gear_compose.command_dwords));
        if (result != 0) park("Stage H three-draw contract failed");
#else
        result = sh_direct_adapter(&cursor, static_cast<std::uint32_t>(
            (command_words + 0x1000 / 4) - cursor),
            PS5_AGC_GEARS_PARAMETER_OFFSET, cube_params, 17);
        log_hex32("stage_f_direct_user_data=", result);
        if (result != 0) park("Stage F direct user data compose failed");
#endif
#endif
#ifndef STAGE_H_GEARS
        result = draw_index_auto_adapter(
            &cursor, static_cast<std::uint32_t>(
                (command_words + 0x1000 / 4) - cursor),

#ifdef STAGE_F_CUBE
#ifdef STAGE_G_DEPTH_LITMUS
            12,
#else
            36,
#endif
#else
            3,
#endif
            draw_modifier);
        log_hex32("stage_e_isolation_draw=", result);
        if (result != 0) park("Stage E draw isolation compose failed");
#endif
        stage_b_stream isolation_stream {
            cursor, command_words + 0x1000 / 4, nullptr, 0};
        result = stage_b_compose_setflip_then_fence(
            &isolation_stream, set_flip_adapter, g_resources.video,
            static_cast<std::int32_t>(kSelectedBuffer), plan.flip_mode,
            kFlipArg, reinterpret_cast<std::uintptr_t>(fence));
        log_hex32("stage_e_wait_flip_compose=", result);
        if (result != STAGE_B_COMPOSE_OK)
            park("Stage E wait-flip SetFlip/fence compose failed");
        const std::uint32_t total_dwords = static_cast<std::uint32_t>(
            isolation_stream.cursor - command_words);
        log_hex32("stage_e_command_dwords=", total_dwords);
        g_transaction_possible = 1;
        log_text("STAGE_E_TRANSACTION_STARTED one_submit=true\n");
        log_text("STAGE_E_DRAW_ISOLATION buffer=1 cx=true uc=true sh=true draw=true\n");
        result = submit_adapter(command_words, total_dwords,
                                g_resources.command);
        log_hex32("stage_e_submit=", result);
        if (result != 0) park("Stage E wait-flip submit failed");
    } else {
      StageEDcbOfflineInput stage_e_input {
        {pipeline->cx, STAGE_E_CX_REGISTER_COUNT},
        {pipeline->sh, STAGE_E_SH_REGISTER_COUNT},
        {pipeline->uc, STAGE_E_UC_REGISTER_COUNT},
        draw_modifier, 0, wait_rendering_adapter, cx_indirect_adapter,
        uc_indirect_adapter, sh_indirect_adapter, draw_index_auto_adapter,
        set_flip_adapter,
        g_resources.video,
        static_cast<std::int32_t>(kSelectedBuffer), plan.flip_mode, kFlipArg,
        reinterpret_cast<std::uintptr_t>(post_wait_fence),
        reinterpret_cast<std::uintptr_t>(pre_draw_fence),
        reinterpret_cast<std::uintptr_t>(fence),
    };
    StageEDcbOfflineOutput stage_e_output {};
    log_text("STAGE_E_DCB_COMPOSE_STARTED no_submit_yet=true\n");
    result = stage_e_compose_dcb_offline(command_words, 0x1000 / 4,
                                         &stage_e_input, &stage_e_output);
    log_hex32("stage_e_compose=", result);
    if (result != STAGE_E_DCB_OK) park("Stage E compose failed");
    {
        const std::uint32_t total_dwords = static_cast<std::uint32_t>(
            stage_e_output.end - command_words);
        log_hex32("stage_e_command_dwords=", total_dwords);
        if (stage_e_runtime_checkpoint == 5) {
            log_text("STAGE_E_CHECKPOINT_DCB_COMPLETE no submit\n");
            finish_pretransaction(36);
        }
        g_transaction_possible = 1;
        log_text("STAGE_E_TRANSACTION_STARTED one_submit=true\n");
        result = submit_adapter(command_words, total_dwords,
                                g_resources.command);
        log_hex32("stage_e_submit=", result);
    }
    if (result != 0) park("Stage E submit failed");
    }
#endif /* STAGE_I_ANIMATED */
#elif defined(STAGE_D_VISIBLE_CLEAR)
    const std::uintptr_t destination = reinterpret_cast<std::uintptr_t>(selected);
    const std::uint32_t dma[7] = {
        UINT32_C(0xc0055000), UINT32_C(0xc0300000), kGpuColor, 0,
        static_cast<std::uint32_t>(destination),
        static_cast<std::uint32_t>(destination >> 32),
        static_cast<std::uint32_t>(plan.tiled_footprint),
    };
    for (std::size_t index = 0; index < 7; ++index) command_words[index] = dma[index];
    stage_b_stream stream {command_words + 7, command_words + 0x1000 / 4,
                           nullptr, 0};
    g_transaction_possible = 1;
    log_text("STAGE_D_TRANSACTION_STARTED\n");
    result = stage_b_compose_setflip_then_fence(
        &stream, set_flip_adapter, g_resources.video,
        static_cast<std::int32_t>(kSelectedBuffer), plan.flip_mode, kFlipArg,
        reinterpret_cast<std::uintptr_t>(fence));
    log_hex32("stage_d_compose=", result);
    if (result != STAGE_B_COMPOSE_OK) park("Stage D compose failed");
    const std::uint32_t total_dwords =
        static_cast<std::uint32_t>(stream.cursor - command_words);
    result = submit_adapter(command_words, total_dwords, g_resources.command);
    log_hex32("stage_d_submit=", result);
    log_hex32("stage_d_command_dwords=", total_dwords);
    if (result != 0) park("Stage D submit failed");
#else
    stage_b_stream stream {command_words, command_words + 0x1000 / 4,
                           nullptr, 0};
    stage_b_transaction_input input {
        &stream, set_flip_adapter, submit_adapter, g_resources.command, fence,
        g_resources.video, static_cast<std::int32_t>(kSelectedBuffer),
        plan.flip_mode, kFlipArg, 1, 1, 1,
    };
    stage_b_transaction_state transaction {};
    g_transaction_possible = 1;
    log_text("SETFLIP_TRANSACTION_STARTED\n");
    result = stage_b_build_and_submit(&input, &transaction);
    log_hex32("stage_b_transaction=", result);
    log_hex32("stage_b_builder=", transaction.builder_result);
    log_hex32("stage_b_submit=", transaction.submit_result);
    log_hex32("stage_b_command_dwords=", transaction.command_dwords);
    if (result != STAGE_B_TRANSACTION_OK) park("build or submit failed");
#endif

#ifndef STAGE_I_ANIMATED
    stage_b_completion_state completion {};
    result = stage_b_completion_begin(&completion, kFlipArg, 1);
    if (result != STAGE_B_COMPLETION_WAITING) park("completion begin failed");
    const std::uint64_t fence_deadline = monotonic_ns() + UINT64_C(2000000000);
    while (__atomic_load_n(fence, __ATOMIC_ACQUIRE) != 0 &&
           monotonic_ns() < fence_deadline) {
        struct timespec delay {0, 1000000};
        (void)nanosleep(&delay, nullptr);
    }
    if (__atomic_load_n(fence, __ATOMIC_ACQUIRE) != 0)
        park("ownership fence timeout");
    log_text("STAGE_B_GPU_FENCE_ZERO\n");

#ifdef STAGE_E_TRIANGLE
    std::uint32_t changed_words = 0;
    for (std::size_t index = 0; index < plan.tiled_footprint / 4; ++index)
        if (selected[index] != kInitialColor) ++changed_words;
    log_hex32("stage_e_target_changed_words=",
              static_cast<int>(changed_words));
    if (changed_words != 0)
        log_text("STAGE_E_TARGET_CHANGED_BY_GPU true\n");
    else
        log_text("STAGE_E_TARGET_CHANGED_BY_GPU false\n");
#endif

#ifdef STAGE_D_VISIBLE_CLEAR
    bool target_matches = true;
    for (std::size_t index = 0; index < plan.tiled_footprint / 4; ++index) {
        if (selected[index] != kGpuColor) { target_matches = false; break; }
    }
    if (!target_matches) park("Stage D target mismatch");
    log_text("STAGE_D_TARGET_MATCHES\n");
#endif
#if defined(STAGE_D_VISIBLE_CLEAR) || defined(STAGE_E_TRIANGLE)
    bool guards_intact = true;
    for (std::size_t index = 0; index < 16; ++index) {
        if (guard_before[index] != kGuardWord || guard_after[index] != kGuardWord) {
            guards_intact = false; break;
        }
    }
    if (!guards_intact) park("visible target guard corruption");
#ifdef STAGE_E_TRIANGLE
    log_text("STAGE_E_GUARDS_INTACT\n");
#else
    log_text("STAGE_D_GUARDS_INTACT\n");
#endif
    bool recovery_untouched = true;
    for (std::size_t index = 0; index < plan.tiled_footprint / 4; ++index) {
        const std::uint32_t expected_recovery =
#ifdef STAGE_E_TRIANGLE
            kGpuColor;
#else
            kRecoveryColor;
#endif
        if (recovery[index] != expected_recovery) {
            recovery_untouched = false; break;
        }
    }
    if (!recovery_untouched) park("recovery buffer modified");
#ifdef STAGE_E_TRIANGLE
    log_text("STAGE_E_RECOVERY_BUFFER_UNTOUCHED\n");
#else
    log_text("STAGE_D_RECOVERY_BUFFER_UNTOUCHED\n");
#endif
#endif

    alignas(8) std::uint8_t event[32] {};
    stage_b_event_diagnostics event_diagnostics {};
    const std::uint64_t event_deadline = monotonic_ns() + UINT64_C(2000000000);
    for (;;) {
        stage_b_event_poll poll {
            g_resources.equeue, &event, fence, 10000, 0,
            monotonic_ns() >= event_deadline ? 1 : 0, &event_diagnostics,
        };
        result = stage_b_poll_videoout_completion(&completion, &poll);
        if (result == STAGE_B_COMPLETION_DONE) break;
        if (result < 0) {
            log_hex32("stage_b_event_result=", result);
            log_hex32("stage_b_wait_calls=", event_diagnostics.wait_calls);
            log_hex32("stage_b_last_wait_rc=", event_diagnostics.last_wait_rc);
            log_hex32("stage_b_last_event_count=", event_diagnostics.last_event_count);
            log_hex32("stage_b_decode_calls=", event_diagnostics.decode_calls);
            log_hex32("stage_b_last_decode_rc=", event_diagnostics.last_decode_rc);
            log_hex64("stage_b_last_flip_arg=",
                      static_cast<std::uint64_t>(event_diagnostics.last_flip_arg));
            park("VideoOut completion mismatch or timeout");
        }
    }
    log_text("STAGE_B_VIDEOOUT_EVENT_ONE\n");
    log_hex64("stage_b_flip_arg=", kFlipArg);

#if defined(STAGE_D_VISIBLE_CLEAR) || defined(STAGE_E_TRIANGLE)
#ifdef STAGE_E_TRIANGLE
#if defined(STAGE_G_DEPTH_LITMUS) || defined(STAGE_H_GEARS)
    log_text("STAGE_E_VISIBLE_HOLD_STARTED milliseconds=10000\n");
#else
    log_text("STAGE_E_VISIBLE_HOLD_STARTED milliseconds=5000\n");
#endif
#else
    log_text("STAGE_D_VISIBLE_HOLD_STARTED milliseconds=5000\n");
#endif
    { struct timespec visible {
#if defined(STAGE_G_DEPTH_LITMUS) || defined(STAGE_H_GEARS)
        10,
#else
        5,
#endif
        0}; (void)nanosleep(&visible, nullptr); }
#ifdef STAGE_E_TRIANGLE
    log_text("STAGE_E_VISIBLE_HOLD_COMPLETE\n");
#else
    log_text("STAGE_D_VISIBLE_HOLD_COMPLETE\n");
#endif
#endif

#endif /* !STAGE_I_ANIMATED */
    (void)memset(g_resources.command, 0, kCommandBytes);
#ifdef STAGE_E_TRIANGLE
    (void)memset(g_resources.shader, 0, kShaderBytes);
    flush_gpu_data(g_resources.shader, kShaderBytes);
    log_text("STAGE_E_SHADER_ARENA_SCRUBBED\n");
#endif
    result = cleanup_resources();
    if (result != 0) park("post-completion cleanup failed");
    g_transaction_possible = 0;
    log_text("AGC stage B exit result=0\n");
#ifdef STAGE_E_TRIANGLE
    log_text("STAGE_E_COMPLETE cleanup complete; immediate process exit follows\n");
#elif defined(STAGE_D_VISIBLE_CLEAR)
    log_text("STAGE_D_COMPLETE cleanup complete; immediate process exit follows\n");
#else
    log_text("STAGE_B_COMPLETE cleanup complete; immediate process exit follows\n");
#endif
    ps5log_close("cleanup-complete");
    (void)alarm(0);
    _exit(0);
}
