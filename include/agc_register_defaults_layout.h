#ifndef HOMEBREW_PS5_AGC_REGISTER_DEFAULTS_LAYOUT_H
#define HOMEBREW_PS5_AGC_REGISTER_DEFAULTS_LAYOUT_H

#include <stddef.h>
#include <stdint.h>

/*
 * Minimal layout observed on FW 12.02 and independently corroborated by the
 * public Prosper/Kyty model. Pointer targets remain opaque at this gate.
 */
typedef struct AgcRegisterPair {
    uint32_t offset;
    uint32_t value;
} AgcRegisterPair;

/* FW 12.02 legacy sceAgcGetRegisterDefaults() record (8 bytes, not the
 * 12-byte record used by the public GetRegisterDefaults2 model).
 * encoded_index = (index << 2) | bank, where bank 0/1/2 = CX/SH/UC. */
typedef struct AgcTypeIndexPair {
    uint32_t key;
    uint32_t encoded_index;
} AgcTypeIndexPair;

static inline uint32_t agc_type_index_bank(const AgcTypeIndexPair *record) {
    return record->encoded_index & 3u;
}

static inline uint32_t agc_type_index_value(const AgcTypeIndexPair *record) {
    return record->encoded_index >> 2;
}

typedef struct AgcRegisterDefaults {
    AgcRegisterPair **table_cx;     /* +0x00 */
    AgcRegisterPair **table_sh;     /* +0x08 */
    AgcRegisterPair **table_uc;     /* +0x10 */
    AgcRegisterPair **table_3;      /* +0x18; null in the observed public table */
    uint64_t unknown_20;            /* +0x20 */
    uint64_t unknown_28;            /* +0x28 */
    AgcTypeIndexPair *type_index_pairs; /* +0x30; count-delimited, no sentinel */
    uint32_t count;                 /* +0x38; observed 0x89 */
    uint32_t reserved_3c;
} AgcRegisterDefaults;

#ifdef __cplusplus
#define AGC_STATIC_ASSERT static_assert
#else
#define AGC_STATIC_ASSERT _Static_assert
#endif

AGC_STATIC_ASSERT(sizeof(AgcRegisterPair) == 0x08, "AGC register pair ABI");
AGC_STATIC_ASSERT(sizeof(AgcTypeIndexPair) == 0x08, "AGC type/index pair ABI");
AGC_STATIC_ASSERT(offsetof(AgcRegisterDefaults, table_cx) == 0x00, "AGC table_cx ABI");
AGC_STATIC_ASSERT(offsetof(AgcRegisterDefaults, table_sh) == 0x08, "AGC table_sh ABI");
AGC_STATIC_ASSERT(offsetof(AgcRegisterDefaults, table_uc) == 0x10, "AGC table_uc ABI");
AGC_STATIC_ASSERT(offsetof(AgcRegisterDefaults, table_3) == 0x18, "AGC table_3 ABI");
AGC_STATIC_ASSERT(offsetof(AgcRegisterDefaults, unknown_20) == 0x20, "AGC unknown_20 ABI");
AGC_STATIC_ASSERT(offsetof(AgcRegisterDefaults, unknown_28) == 0x28, "AGC unknown_28 ABI");
AGC_STATIC_ASSERT(offsetof(AgcRegisterDefaults, type_index_pairs) == 0x30,
                  "AGC type table ABI");
AGC_STATIC_ASSERT(offsetof(AgcRegisterDefaults, count) == 0x38, "AGC count ABI");
AGC_STATIC_ASSERT(sizeof(AgcRegisterDefaults) == 0x40, "AGC defaults ABI size");

#undef AGC_STATIC_ASSERT

#endif
