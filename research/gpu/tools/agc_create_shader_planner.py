#!/usr/bin/env python3
"""Fail-closed, host-only planner for a future sceAgcCreateShader call."""

from __future__ import annotations

from dataclasses import dataclass


U64_LIMIT = 1 << 64
HEADER_PREFIX_SIZE = 0x60
USER_DATA_SIZE = 0x38
REGISTER_SIZE = 8
SEMANTIC_SIZE = 4
CODE_ALIGNMENT = 0x100
MIN_FOOTER_DISTANCE = 0x30
MAGIC = 0x34333231
VERSION = 0x18
SUCCESS = 0
PREMUTATION_ERRORS = {
    0x8A6C0003, 0x8A6C0004, 0x8A6C001F, 0x8A6C002F,
    0x8A6C003D, 0x8A6C0042,
}
POSTMUTATION_ERRORS = {0x8A6C0005}


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class Region:
    base: int
    size: int
    readable: bool
    writable: bool
    name: str

    def contains(self, address: int, size: int, *, write: bool = False) -> bool:
        if self.base < 0 or self.size <= 0 or address < self.base or size <= 0:
            return False
        end = address + size
        region_end = self.base + self.size
        if end > U64_LIMIT or region_end > U64_LIMIT:
            return False
        return end <= region_end and self.readable and (not write or self.writable)

    def contains_point(self, address: int) -> bool:
        return (self.readable and self.base <= address <= self.base + self.size
                and self.base + self.size <= U64_LIMIT)


@dataclass(frozen=True)
class HeaderFacts:
    magic: int
    version: int
    header_size: int
    shader_size: int
    target: int
    stage: int
    code_field: int
    relative_pointers: dict[int, int]
    num_cx_registers: int
    num_sh_registers: int
    num_input_semantics: int
    num_output_semantics: int


@dataclass(frozen=True)
class UserDataFacts:
    relative_pointers: dict[int, int]
    direct_resource_count: int
    sharp_resource_counts: tuple[int, int, int, int]


@dataclass(frozen=True)
class Preconditions:
    destination_initially_null: bool
    footer_marker_valid: bool
    stage_register_match_proven: bool
    runtime_mode_word: int
    target_feature_flag: int
    target_sdk_word: int
    signed_target_helper_passed: bool = False


@dataclass(frozen=True)
class MockOutcome:
    state: str
    destination_published: bool
    header_mutated: bool
    caller_may_retry_same_copy: bool


def checked_product(count: int, stride: int, label: str) -> int:
    if count < 0 or stride <= 0 or count > (U64_LIMIT - 1) // stride:
        raise PlanError(f"{label} size overflow")
    return count * stride


def relocated(header_address: int, field_offset: int, raw: int) -> int | None:
    if raw == 0:
        return None
    if raw >= (1 << 32):
        raise PlanError(f"pointer at {field_offset:#x} is already relocated or malformed")
    value = header_address + field_offset + raw
    if value >= U64_LIMIT:
        raise PlanError(f"pointer at {field_offset:#x} overflows")
    return value


def validate_target_policy(target: int, feature_flag: int, sdk_word: int,
                           signed_helper_passed: bool) -> None:
    if not 0 <= target < (1 << 32):
        raise PlanError("target is not u32")
    base = target & 0x7FFFFFFF
    if target & 0x80000000 and not signed_helper_passed:
        raise PlanError("signed target helper result is unproven")
    if ((base == 10 and feature_flag != 0) or
            (base == 12 and feature_flag == 0) or
            (base == 13 and feature_flag != 0) or
            (base == 15 and feature_flag == 0)):
        raise PlanError("target conflicts with firmware feature flag")
    sdk_gate = base >= 13
    if sdk_gate and (sdk_word & 0xFFFFFFF0) == 0x00840FC0:
        raise PlanError("target conflicts with firmware SDK policy")


def build_plan(destination: Region, header: Region, code: Region,
               facts: HeaderFacts, pre: Preconditions,
               user_data_facts: UserDataFacts | None = None) -> dict:
    if not destination.contains(destination.base, 8, write=True):
        raise PlanError("destination slot is not writable for 8 bytes")
    if not pre.destination_initially_null:
        raise PlanError("destination must initially be null")
    if header.base % 8 or not header.contains(header.base, HEADER_PREFIX_SIZE, write=True):
        raise PlanError("header prefix must be 8-byte aligned, readable and writable")
    if facts.header_size < HEADER_PREFIX_SIZE or facts.header_size > header.size:
        raise PlanError("header_size is outside the supplied header region")
    if facts.magic != MAGIC or facts.version != VERSION:
        raise PlanError("unsupported header magic/version")
    if facts.code_field != 0:
        raise PlanError("header code field must be unbound")
    if code.base % CODE_ALIGNMENT:
        raise PlanError("code is not 256-byte aligned")
    if facts.shader_size < MIN_FOOTER_DISTANCE:
        raise PlanError("shader_size cannot safely reach the footer probe")
    if not code.contains(code.base, facts.shader_size):
        raise PlanError("shader code range is not fully readable")
    if not pre.footer_marker_valid:
        raise PlanError("shader footer marker was not validated")
    if facts.stage not in range(8):
        raise PlanError("stage is outside firmware dispatch range 0..7")
    if pre.runtime_mode_word == 0x10000000:
        raise PlanError("AGC runtime is in the rejected mode")
    validate_target_policy(facts.target, pre.target_feature_flag,
                           pre.target_sdk_word, pre.signed_target_helper_passed)

    expected_fields = {0x08, 0x18, 0x20, 0x28, 0x30, 0x38}
    if set(facts.relative_pointers) != expected_fields:
        raise PlanError("relative-pointer field set is incomplete")
    resolved = {
        field: relocated(header.base, field, raw)
        for field, raw in facts.relative_pointers.items()
    }
    for field, address in resolved.items():
        if address is not None and not header.contains(address, 8, write=True):
            raise PlanError(f"relocated pointer at {field:#x} leaves header region")

    bounded_arrays = (
        (0x18, facts.num_cx_registers, REGISTER_SIZE, "CX registers"),
        (0x20, facts.num_sh_registers, REGISTER_SIZE, "SH registers"),
        (0x30, facts.num_input_semantics, SEMANTIC_SIZE, "input semantics"),
        (0x38, facts.num_output_semantics, SEMANTIC_SIZE, "output semantics"),
    )
    for field, count, stride, label in bounded_arrays:
        size = checked_product(count, stride, label)
        address = resolved[field]
        if count == 0:
            continue
        if address is None or not header.contains(address, size, write=True):
            raise PlanError(f"{label} range is absent or out of bounds")

    user_data = resolved[0x08]
    if user_data is None:
        raise PlanError("user-data structure is mandatory on FW 12.02")
    if not header.contains(user_data, USER_DATA_SIZE, write=True):
        raise PlanError("user-data structure is out of bounds")
    if user_data_facts is None:
        raise PlanError("user-data facts are required for mandatory structure")
    if user_data_facts is not None:
        fields = {0, 8, 16, 24, 32}
        if set(user_data_facts.relative_pointers) != fields:
            raise PlanError("nested user-data pointer field set is incomplete")
        counts = ((user_data_facts.direct_resource_count,) +
                  user_data_facts.sharp_resource_counts)
        if len(user_data_facts.sharp_resource_counts) != 4:
            raise PlanError("need four sharp-resource counts")
        for field, count in zip((0, 8, 16, 24, 32), counts):
            address = relocated(user_data, field,
                                user_data_facts.relative_pointers[field])
            if address is None:
                if count:
                    raise PlanError("nested resource array is absent for nonzero count")
                continue
            if not header.contains_point(address):
                raise PlanError("nested resource pointer leaves header region")
            size = checked_product(count, 2, "nested resource array")
            if size and not header.contains(address, size):
                raise PlanError("nested resource array leaves header region")
    if facts.stage not in (4, 5):
        if facts.num_sh_registers == 0 or resolved[0x20] is None:
            raise PlanError("stage requires a non-empty SH register array")
        if not pre.stage_register_match_proven:
            raise PlanError("required stage SH-register match is unproven")

    return {
        "approved": True,
        "abi": "int32_t(AgcShaderHeader **, AgcShaderHeader *, const void *)",
        "symbol_nid": "f3dg2CSgRKY",
        "header_bytes": facts.header_size,
        "code_bytes": facts.shader_size,
        "code_alignment": CODE_ALIGNMENT,
        "stage": facts.stage,
        "target": facts.target,
        "ownership": "caller retains mutable header and code",
        "retirement": "only after all pipeline/GPU references are quiescent",
        "destructor_export": None,
        "failure_policy": "post-mutation failure consumes the mutable copy",
        "console_execution_authorized": False,
    }


def classify_constructor_result(return_code: int) -> str:
    if return_code == SUCCESS:
        return "constructed_alias"
    if return_code in PREMUTATION_ERRORS:
        return "rejected_before_mutation"
    if return_code in POSTMUTATION_ERRORS:
        return "consumed_partial_mutation_discard_copy"
    return "indeterminate_retain_do_not_retry"


def mock_constructor(return_code: int) -> MockOutcome:
    state = classify_constructor_result(return_code)
    if state == "constructed_alias":
        return MockOutcome(state, True, True, False)
    if state == "rejected_before_mutation":
        return MockOutcome(state, False, False, True)
    if state == "consumed_partial_mutation_discard_copy":
        return MockOutcome(state, False, True, False)
    return MockOutcome(state, False, True, False)


def retire(*, constructed: bool, downstream_references: int,
           gpu_quiescent: bool) -> str:
    if not constructed:
        raise PlanError("cannot retire a shader that was not constructed")
    if downstream_references != 0:
        raise PlanError("downstream references remain")
    if not gpu_quiescent:
        raise PlanError("GPU/pipeline quiescence is unproven")
    return "caller_may_release_header_and_code"
