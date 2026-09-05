#ifndef HOMEBREW_PS5_AGC_CREATE_SHADER_CONTRACT_H
#define HOMEBREW_PS5_AGC_CREATE_SHADER_CONTRACT_H

#include <stddef.h>
#include <stdint.h>

/* CPU-visible ABI observed in libSceAgc FW 12.02. These types describe the
 * input blob; they do not contain or distribute any proprietary shader. */
typedef struct AgcShaderRegister {
    uint32_t offset;
    uint32_t value;
} AgcShaderRegister;

typedef struct AgcShaderUserData {
    uint16_t *direct_resource_offsets;
    void *sharp_resource_offsets[4];
    uint16_t eud_size_dw;
    uint16_t srt_size_dw;
    uint16_t direct_resource_count;
    uint16_t sharp_resource_count[4];
} AgcShaderUserData;

typedef struct AgcShaderHeader {
    uint32_t file_header;                 /* +0x00: 0x34333231 */
    uint32_t version;                     /* +0x04: 0x18 */
    AgcShaderUserData *user_data;         /* +0x08: self-relative */
    const void *code;                     /* +0x10: null on entry */
    AgcShaderRegister *cx_registers;       /* +0x18: self-relative */
    AgcShaderRegister *sh_registers;       /* +0x20: self-relative */
    void *specials;                       /* +0x28: self-relative */
    void *input_semantics;                 /* +0x30: self-relative */
    void *output_semantics;                /* +0x38: self-relative */
    uint32_t header_size;                 /* +0x40 */
    uint32_t shader_size;                 /* +0x44 */
    uint32_t embedded_constant_dqw;        /* +0x48 */
    uint32_t target;                      /* +0x4c */
    uint32_t num_input_semantics;          /* +0x50 */
    uint16_t scratch_dw_per_thread;        /* +0x54 */
    uint16_t num_output_semantics;         /* +0x56 */
    uint16_t special_sizes_bytes;          /* +0x58 */
    uint8_t type;                         /* +0x5a */
    uint8_t num_cx_registers;              /* +0x5b */
    uint8_t num_sh_registers;              /* +0x5c */
    uint8_t reserved_5d[3];
} AgcShaderHeader;

typedef int32_t (*AgcCreateShaderFn)(AgcShaderHeader **destination,
                                     AgcShaderHeader *mutable_header,
                                     const void *code);

#if defined(__cplusplus)
#define AGC_SHADER_STATIC_ASSERT static_assert
#else
#define AGC_SHADER_STATIC_ASSERT _Static_assert
#endif

AGC_SHADER_STATIC_ASSERT(sizeof(AgcShaderRegister) == 0x08, "register ABI");
AGC_SHADER_STATIC_ASSERT(sizeof(AgcShaderUserData) == 0x38, "user-data ABI");
AGC_SHADER_STATIC_ASSERT(offsetof(AgcShaderUserData, sharp_resource_offsets) == 0x08,
                         "sharp pointers ABI");
AGC_SHADER_STATIC_ASSERT(offsetof(AgcShaderUserData, eud_size_dw) == 0x28,
                         "user-data counts ABI");
AGC_SHADER_STATIC_ASSERT(offsetof(AgcShaderUserData, direct_resource_count) == 0x2c,
                         "direct count ABI");
AGC_SHADER_STATIC_ASSERT(offsetof(AgcShaderHeader, code) == 0x10, "code ABI");
AGC_SHADER_STATIC_ASSERT(offsetof(AgcShaderHeader, sh_registers) == 0x20, "SH ABI");
AGC_SHADER_STATIC_ASSERT(offsetof(AgcShaderHeader, header_size) == 0x40, "size ABI");
AGC_SHADER_STATIC_ASSERT(offsetof(AgcShaderHeader, type) == 0x5a, "type ABI");
AGC_SHADER_STATIC_ASSERT(offsetof(AgcShaderHeader, num_sh_registers) == 0x5c,
                         "SH count ABI");
AGC_SHADER_STATIC_ASSERT(sizeof(AgcShaderHeader) == 0x60, "header prefix ABI");

#undef AGC_SHADER_STATIC_ASSERT
#endif
