#include <cstddef>
#include <cstdint>

extern "C" {
#include "../../probes/ps5-agc-phase0/stage_e_dcb_offline.h"
#include "../../probes/ps5-agc-phase0/stage_e_color_target.h"
#include "../../probes/ps5-agc-phase0/stage_e_compiled_metadata.h"
#include "../../probes/ps5-agc-phase0/stage_e_pipeline_registers.h"
void *memset(void *, int, std::size_t);
}

namespace {
alignas(8) StageEPipelineRegisters pipeline;
alignas(8) AgcRegister1202 render_target[STAGE_E_RT_REGISTER_COUNT];
alignas(8) AgcRegister1202 synthetic_defaults[STAGE_E_RT_REGISTER_COUNT];
alignas(8) AgcLinkedCx1202 linked_cx;
alignas(8) AgcLinkedUc1202 linked_uc;
alignas(8) AgcRegister1202 pre_sh[6], pixel_sh[6];
alignas(8) std::uint64_t fence_word;
alignas(8) std::uint32_t dcb_words[128];
volatile std::uint64_t buildonly_digest;

int offline_set_flip(std::uint32_t **cursor, std::uint32_t capacity,
                     std::uint32_t driver_mode, std::int32_t handle,
                     std::int32_t index, std::uint32_t mode, std::uint64_t arg)
{
    if (!cursor || !*cursor || capacity < 4 || driver_mode != 0 || handle != 7 ||
        index != 1 || mode != 1 || arg != UINT64_C(0x1234)) return -1;
    (*cursor)[0] = UINT32_C(0xc0021000);
    (*cursor)[1] = 7; (*cursor)[2] = 1; (*cursor)[3] = UINT32_C(0x1234);
    *cursor += 4;
    return 0;
}

std::uint64_t hash_words(const std::uint32_t *p, std::size_t count)
{
    std::uint64_t h = UINT64_C(14695981039346656037);
    for (std::size_t i = 0; i < count; ++i) {
        std::uint32_t v = p[i];
        for (unsigned byte = 0; byte < 4; ++byte) {
            h ^= static_cast<std::uint8_t>(v); h *= UINT64_C(1099511628211); v >>= 8;
        }
    }
    return h;
}
}

int main()
{
    static constexpr std::uint32_t rt_offsets[16] = {
        0x318, 0x31b, 0x31c, 0x31d, 0x31e, 0x31f, 0x321, 0x323,
        0x324, 0x325, 0x390, 0x398, 0x3a0, 0x3a8, 0x3b0, 0x3b8,
    };
    memset(&pipeline, 0, sizeof(pipeline)); memset(&linked_cx, 0, sizeof(linked_cx));
    memset(&linked_uc, 0, sizeof(linked_uc)); memset(dcb_words, 0, sizeof(dcb_words));
    for (unsigned i = 0; i < 16; ++i) synthetic_defaults[i] = {rt_offsets[i], 0};
    if (stage_e_build_color_target(render_target, synthetic_defaults,
            static_cast<std::uintptr_t>(UINT64_C(0x5000200000)), 1920, 1080) != 0)
        return 1;
    pre_sh[0] = {0x80, 0}; pre_sh[1] = {0x80, 0};
    pre_sh[2] = {0x8a, STAGE_E_GS_RSRC1};
    pre_sh[3] = {0x8b, STAGE_E_GS_RSRC2};
    pre_sh[4] = {0xc8, 0}; pre_sh[5] = {0xc9, 0};
    pixel_sh[0] = {6, 0}; pixel_sh[1] = {6, 0};
    pixel_sh[2] = {8, 0}; pixel_sh[3] = {9, 0};
    pixel_sh[4] = {0xa, STAGE_E_PS_RSRC1};
    pixel_sh[5] = {0xb, STAGE_E_PS_RSRC2};
    if (stage_e_build_pipeline_registers(&pipeline, render_target, &linked_cx,
            &linked_uc, stage_e_pre_raster_cx_template,
            stage_e_pixel_cx_template, pre_sh, pixel_sh, 1920, 1080) != 0)
        return 2;
    StageEDcbOfflineInput input = {
        {pipeline.cx, STAGE_E_CX_REGISTER_COUNT},
        {pipeline.sh, STAGE_E_SH_REGISTER_COUNT},
        {pipeline.uc, STAGE_E_UC_REGISTER_COUNT},
        0, offline_set_flip, 7, 1, 1, UINT64_C(0x1234),
        reinterpret_cast<std::uintptr_t>(&fence_word),
    };
    StageEDcbOfflineOutput output{};
    if (stage_e_compose_dcb_offline(dcb_words, 128, &input, &output) != 0) return 3;
    buildonly_digest = hash_words(output.begin,
        static_cast<std::size_t>(output.end - output.begin));
    return buildonly_digest ? 0 : 4;
}
