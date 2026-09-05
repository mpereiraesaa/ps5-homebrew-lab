#!/usr/bin/env python3
"""Fail-closed, host-only planner for FW 12.02 sceAgcLinkShaders."""
from __future__ import annotations

from dataclasses import dataclass


U64_LIMIT = 1 << 64
CX_BYTES = 0x110
UC_BYTES = 0x18
SEMANTIC_BYTES = 4
SEMANTIC_CAPACITY = 32
PROVEN_PRE_RASTER_TYPES = frozenset({2})
PROVEN_PIXEL_TYPES = frozenset({1})
PROVEN_PRIMITIVES = frozenset(range(1, 19))


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class Region:
    base: int
    size: int
    readable: bool
    writable: bool
    name: str

    @property
    def end(self) -> int:
        return self.base + self.size

    def contains(self, address: int, size: int, *, write: bool = False) -> bool:
        if min(self.base, self.size, address, size) < 0 or not self.readable:
            return False
        if self.end > U64_LIMIT or address + size > U64_LIMIT:
            return False
        return self.base <= address and address + size <= self.end and (not write or self.writable)


@dataclass(frozen=True)
class ShaderFacts:
    role: str
    type_raw: int
    header_address: int
    header_bytes: int
    special_pointer: int
    special_bytes: int
    input_pointer: int
    input_semantics: tuple[int, ...]
    output_pointer: int
    output_semantics: tuple[int, ...]
    cx_register_pointer: int = 0
    cx_register_count: int = 0
    sh_register_pointer: int = 0
    sh_register_count: int = 0
    resource_arrays: tuple[tuple[int, int], ...] = ()
    register_resource_ranges_proven: bool = False


@dataclass(frozen=True)
class LinkState:
    state: str
    outputs_mutated: bool
    reusable: bool


def overlaps(a: Region, b: Region) -> bool:
    return a.base < b.end and b.base < a.end


def semantic_keys(values: tuple[int, ...]) -> tuple[int, ...]:
    if len(values) > SEMANTIC_CAPACITY:
        raise PlanError("semantic count exceeds the 32-entry CX capacity")
    for value in values:
        if not 0 <= value < (1 << 32):
            raise PlanError("semantic word is not u32")
    return tuple(value & 0xFF for value in values)


def validate_shader(region: Region, facts: ShaderFacts) -> None:
    if facts.header_address != region.base or facts.header_bytes < 0x60:
        raise PlanError(f"{facts.role} header prefix is not fully described")
    if not region.contains(facts.header_address, facts.header_bytes):
        raise PlanError(f"{facts.role} header leaves its readable region")
    if not region.contains(facts.special_pointer, facts.special_bytes):
        raise PlanError(f"{facts.role} special-data range is absent or out of bounds")
    for pointer, values, label in (
        (facts.input_pointer, facts.input_semantics, "input"),
        (facts.output_pointer, facts.output_semantics, "output"),
    ):
        size = len(values) * SEMANTIC_BYTES
        if size and not region.contains(pointer, size):
            raise PlanError(f"{facts.role} {label}-semantic range is absent or out of bounds")
        if not size and pointer and not region.contains(pointer, 0):
            raise PlanError(f"{facts.role} empty {label}-semantic pointer leaves header")
        semantic_keys(values)
    if not facts.register_resource_ranges_proven:
        raise PlanError(f"{facts.role} register/resource ranges are unproven")
    for pointer, count, stride, label in (
        (facts.cx_register_pointer, facts.cx_register_count, 8, "CX registers"),
        (facts.sh_register_pointer, facts.sh_register_count, 8, "SH registers"),
    ):
        if count < 0 or (count and not region.contains(pointer, count * stride)):
            raise PlanError(f"{facts.role} {label} leave the header")
    if len(facts.resource_arrays) != 5:
        raise PlanError(f"{facts.role} resource inventory is incomplete")
    for pointer, count in facts.resource_arrays:
        if count < 0 or (count and not region.contains(pointer, count * 2)):
            raise PlanError(f"{facts.role} resource array leaves the header")


def build_plan(cx: Region, uc: Region, pre_region: Region, pixel_region: Region,
               pre: ShaderFacts, pixel: ShaderFacts, primitive_type: int,
               *, aux_region: Region | None = None, aux: ShaderFacts | None = None,
               outputs_fresh: bool, ownership_proven: bool) -> dict:
    if not cx.contains(cx.base, CX_BYTES, write=True) or cx.base % 8:
        raise PlanError("CX output must be 8-byte aligned and writable for 0x110 bytes")
    if not uc.contains(uc.base, UC_BYTES, write=True) or uc.base % 8:
        raise PlanError("UC output must be 8-byte aligned and writable for 0x18 bytes")
    all_regions = [cx, uc, pre_region, pixel_region]
    if aux_region is not None:
        all_regions.append(aux_region)
    for index, region in enumerate(all_regions):
        for other in all_regions[index + 1:]:
            if overlaps(region, other):
                raise PlanError(f"regions alias: {region.name}/{other.name}")
    if not outputs_fresh:
        raise PlanError("CX/UC outputs must be fresh disposable storage")
    if not ownership_proven:
        raise PlanError("caller ownership/lifetime of every input and output is unproven")
    if primitive_type not in PROVEN_PRIMITIVES:
        raise PlanError("primitive type is outside the proven firmware table range 1..18")
    if pre.role != "pre_raster" or pre.type_raw not in PROVEN_PRE_RASTER_TYPES:
        raise PlanError("pre-raster role/type is not proven for this corpus")
    if pixel.role != "pixel" or pixel.type_raw not in PROVEN_PIXEL_TYPES:
        raise PlanError("pixel role/type is not proven for this corpus")
    validate_shader(pre_region, pre)
    validate_shader(pixel_region, pixel)
    if (aux_region is None) != (aux is None):
        raise PlanError("auxiliary shader facts/region presence mismatch")
    if aux is not None:
        if aux.role != "aux_pre_raster":
            raise PlanError("third shader role is not auxiliary pre-raster")
        validate_shader(aux_region, aux)  # type: ignore[arg-type]

    pre_keys = semantic_keys(pre.output_semantics)
    pixel_keys = semantic_keys(pixel.input_semantics)
    missing = [key for key in pixel_keys if key not in pre_keys]
    if missing:
        raise PlanError("pixel inputs are not supplied by pre-raster outputs")
    if len(set(pixel_keys)) != len(pixel_keys):
        raise PlanError("duplicate pixel semantic keys are ambiguous")

    return {
        "approved": True,
        "symbol_nid": "MqAdbRMdNz4",
        "abi": "int32_t(CX*, UC*, const Shader*, const Shader*, const Shader*, uint32_t)",
        "cx_bytes": CX_BYTES, "uc_bytes": UC_BYTES,
        "primitive_type": primitive_type,
        "pre_raster_type": pre.type_raw, "pixel_type": pixel.type_raw,
        "matched_semantic_keys": list(pixel_keys),
        "firmware_return_is_validation_signal": False,
        "success_definition": "planner approval plus deterministic output transformation",
        "ownership": "caller retains all shaders and linked outputs",
        "retirement": "only after downstream pipeline references are zero and GPU use is quiescent",
        "console_execution_authorized": False,
    }


def mock_link(*, planner_approved: bool, firmware_return: int = 0) -> LinkState:
    if not planner_approved:
        return LinkState("rejected_before_call", False, True)
    if firmware_return != 0:
        return LinkState("abi_or_firmware_drift_indeterminate", True, False)
    return LinkState("linked_host_model", True, False)


def retire(*, state: LinkState, downstream_references: int, gpu_quiescent: bool) -> str:
    if state.state != "linked_host_model":
        raise PlanError("only a linked model can be retired")
    if downstream_references != 0:
        raise PlanError("downstream pipeline references remain")
    if not gpu_quiescent:
        raise PlanError("GPU quiescence is unproven")
    return "caller_may_release_outputs_then_shader_storage"
