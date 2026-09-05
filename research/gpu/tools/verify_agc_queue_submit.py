#!/usr/bin/env python3
"""Byte-level proof for the FW 12.02 AGC graphics submit wrappers.

This is deliberately a local/static verifier.  It never contacts the console
and never executes module code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


CREATE_QUEUE = bytes.fromhex("31 c9 e9 09 00 00 00")
SUBMIT_DCB = bytes.fromhex("48 89 fe 48 8d 3d 4e ff 01 00 e9 41 f0 ff ff")
SETUP_ASYNC_OFFSET = 0x3F30
SETUP_ASYNC_SIZE = 0x91
DRIVER_INIT_OFFSET = 0x7C20
DRIVER_INIT_SIZE = 0x450
GC_CLASSIFIER_OFFSET = 0x8090
GET_REG_SHADOW_INFO_OFFSET = 0x3430
GET_REG_SHADOW_INFO_AGR_OFFSET = 0x3470
UNSUPPORTED_OWNER_RESULT = bytes.fromhex("b8 18 90 6c 8a c3")
SDMA_COPY_LINEAR_BLOCKING_OFFSET = 0x7AB0
SDMA_COPY_LINEAR_BLOCKING = bytes.fromhex(
    "554889e5488b3d35c60000488d35de7c0000488d15ef7a000031c0e8703b"
    "0000b801006d8a5dc3"
)
WAIT_SAFE_OFFSET = 0x7450
WAIT_SAFE_SIZE = 0x1C3
WAIT_SAFE_SHA256 = "1f63366feb8dbbb4294746de8c6063e45ed944693dfc1e40a1fcecf765ebe09c"
GRAPHICS_BACKEND_OFFSET = 0x1100
GRAPHICS_BACKEND_SIZE = 0x350
GRAPHICS_BACKEND_SHA256 = "8e5fb8efa7a44d4bf71e1d314ac9819e7d8958c8ba44fee0a4e741cff91e3362"
CLASS0_BACKEND_OFFSET = 0x1450
CLASS0_BACKEND_SIZE = 0x4CD
CLASS0_BACKEND_SHA256 = "10068a320dc9dc667f897197a66732d2c04d0f901d110f0cf7fc83a2fed3603c"
CLASS0_IOCTL_OFFSET = 0xAD80
CLASS0_IOCTL_SIZE = 0x74
CLASS0_IOCTL_SHA256 = "9a21be82c69e7a7020cfbf6f77e429f0896a4d47ba585fd320ecf96c75c6cefb"
CLASS0_REGISTER_OFFSET = 0xAC60
CLASS0_REGISTER_SIZE = 0x98
CLASS0_REGISTER_SHA256 = "b2563fe3329cb97cfc07395d07d355858a19125b42ba2234a872458fbc9c0141"
CLASS0_INIT_PACKET_OFFSET = 0x5480
CLASS0_INIT_PACKET_SIZE = 0x60
CLASS0_INIT_PACKET_SHA256 = "75b5a26badf1103791f0cb681bef10d8280b919cde6fa4f69a3ba51e397c96aa"


def require(blob: bytes, offset: int, expected: bytes, label: str) -> None:
    actual = blob[offset : offset + len(expected)]
    if actual != expected:
        raise SystemExit(
            f"{label}: mismatch at {offset:#x}: "
            f"expected={expected.hex()} actual={actual.hex()}"
        )


def verify_module_initializer_elf(blob: bytes) -> None:
    """Prove DT_INIT and its relative relocation from the system ELF."""
    if blob[:4] != b"\x7fELF" or blob[4] != 2 or blob[5] != 1:
        raise SystemExit("system AgcDriver is not little-endian ELF64")
    phoff = struct.unpack_from("<Q", blob, 0x20)[0]
    phentsize = struct.unpack_from("<H", blob, 0x36)[0]
    phnum = struct.unpack_from("<H", blob, 0x38)[0]
    dynamic_offset = None
    loads = []
    for index in range(phnum):
        entry = phoff + index * phentsize
        p_type, _flags, p_offset, p_vaddr, _paddr, p_filesz = struct.unpack_from(
            "<IIQQQQ", blob, entry
        )
        if p_type == 1:  # PT_LOAD
            loads.append((p_vaddr, p_vaddr + p_filesz, p_offset))
        if p_type == 2:  # PT_DYNAMIC
            dynamic_offset = p_offset
            break
    if dynamic_offset is None:
        raise SystemExit("system AgcDriver has no PT_DYNAMIC")

    tags = {}
    cursor = dynamic_offset
    while True:
        tag, value = struct.unpack_from("<QQ", blob, cursor)
        cursor += 16
        if tag == 0:
            break
        tags[tag] = value
    if tags.get(12) != 0x10:  # DT_INIT
        raise SystemExit(f"unexpected DT_INIT: {tags.get(12)!r}")
    if tags.get(13) != 0xB940:  # DT_FINI
        raise SystemExit(f"unexpected DT_FINI: {tags.get(13)!r}")
    if tags.get(7) is None or tags.get(8) is None or tags.get(9) != 24:
        raise SystemExit("missing ELF64 RELA metadata")

    def file_offset(virtual_address: int) -> int:
        for start, end, offset in loads:
            if start <= virtual_address < end:
                return offset + virtual_address - start
        raise SystemExit(f"virtual address {virtual_address:#x} is not file-backed")

    init_relocation = None
    rela_file = file_offset(tags[7])
    for offset in range(rela_file, rela_file + tags[8], tags[9]):
        r_offset, r_info, r_addend = struct.unpack_from("<QQq", blob, offset)
        if r_offset == 0x14108:
            init_relocation = (r_info & 0xffffffff, r_addend)
            break
    if init_relocation != (8, 0x8070):  # R_X86_64_RELATIVE
        raise SystemExit(f"unexpected initializer relocation: {init_relocation!r}")


def verify_module_initializer_code(blob: bytes, base: int, label: str) -> None:
    # DT_INIT's dispatcher checks the relocated callback slot, then tail-calls
    # +0x8070. That trampoline jumps directly to the full +0x7c20 initializer.
    require(blob, base + 0x94,
            bytes.fromhex("48833d6c400100007419"),
            f"{label}/DT_INIT callback check")
    require(blob, base + 0xB2,
            bytes.fromhex("e9b97f0000"),
            f"{label}/DT_INIT callback tail-call")
    require(blob, base + 0x8070,
            bytes.fromhex("e9abfbffff"),
            f"{label}/initializer trampoline")


def verify_module_finalizer_code(blob: bytes, base: int, label: str) -> None:
    """Prove that the normal finalizer callback is a no-op, not a GPU drain."""
    # DT_FINI dispatches through callback slot +0x140d8 when non-null.
    require(blob, base + 0xB959,
            bytes.fromhex("48833d77870000007459e818c7ffff"),
            f"{label}/DT_FINI callback dispatch")
    # The callback target at +0x8080 is exactly `xor eax,eax; ret`.
    require(blob, base + 0x8080, bytes.fromhex("31c0c3"),
            f"{label}/normal-finalizer-callback")


def verify_wait_safe_is_packet_builder(blob: bytes, base: int,
                                       label: str) -> None:
    """Pin WaitUntilSafeForRendering as writer mutation, not a CPU wait."""
    function = blob[base + WAIT_SAFE_OFFSET:
                    base + WAIT_SAFE_OFFSET + WAIT_SAFE_SIZE]
    digest = hashlib.sha256(function).hexdigest()
    if digest != WAIT_SAFE_SHA256:
        raise SystemExit(f"{label}/WaitUntilSafeForRendering hash mismatch")
    fragments = {
        # Load and later advance the caller-owned command writer cursor.
        0xA6: bytes.fromhex("488b3b"),
        0xB5: bytes.fromhex("48897db8"),
        0xBE: bytes.fromhex("89c048c1e002480303488903"),
        # Emit WAIT_REG_MEM64 or WAIT_REG_MEM packet headers into that writer.
        0xFE: bytes.fromhex("b9009307c0"),
        0x116: bytes.fromhex("b9001007c0"),
    }
    for relative, expected in fragments.items():
        require(blob, base + WAIT_SAFE_OFFSET + relative, expected,
                f"{label}/WaitUntilSafeForRendering-builder")


def verify_copy_shape(blob: bytes, base: int, label: str) -> None:
    # In SubmitCommandBuffer, r15 is the caller's second argument.  These
    # instructions copy qword +0, dword +8 and byte +0xc into a local record.
    fragments = {
        0x62: bytes.fromhex("49 8b 07 48 89 45 c0"),
        0x69: bytes.fromhex("41 8b 47 08 89 45 c8"),
        0x70: bytes.fromhex("41 0f b6 47 0c 88 45 cc"),
    }
    for relative, expected in fragments.items():
        require(blob, base + relative, expected, f"{label}/submit-info-copy")


def verify_setup_async(blob: bytes, base: int, label: str) -> None:
    fragments = {
        # Read setup state, inspect its low nibble.
        0x13: bytes.fromhex("45 8b 87 c8 01 00 00 41 83 e0 0f"),
        # Backend setup receives the driver handle and literal mode 1.
        0x20: bytes.fromhex("41 8b 7f 04 be 01 00 00 00"),
        # Publish low-nibble state 1 after backend success.
        0x39: bytes.fromhex("41 8b 87 c8 01 00 00 41 b8 01 00 00 00"),
        # Store bool(public_argument != 0) in global +0x1c0.
        0x6C: bytes.fromhex("89 d9 41 0f 95 c1"),
        0x77: bytes.fromhex("45 89 8f c0 01 00 00"),
    }
    for relative, expected in fragments.items():
        require(blob, base + relative, expected, f"{label}/SetupAsyncGraphics")


def verify_driver_init(blob: bytes, base: int, label: str) -> None:
    fragments = {
        # process_class == 1 -> CreateQueue(3, &local, 0)
        0x200: bytes.fromhex(
            "48 8d 75 d0 bf 03 00 00 00 31 d2 e8 f0 a1 ff ff"
        ),
        # process_class == 0 -> CreateQueue(0, &local, 0)
        0x26A: bytes.fromhex(
            "48 8d 75 d0 31 ff 31 d2 e8 89 a1 ff ff"
        ),
        # then CreateQueue(4, &second_local, 0)
        0x277: bytes.fromhex(
            "48 8d 75 c8 bf 04 00 00 00 31 d2 e8 79 a1 ff ff"
        ),
    }
    for relative, expected in fragments.items():
        require(blob, base + relative, expected, f"{label}/driver-init")


def verify_create_queue_lifecycle(blob: bytes, base: int, label: str) -> None:
    """Pin the default/simple queue object's initialization and sentinel."""
    fragments = {
        0xB0: bytes.fromhex(
            "4c8d35d107020083fb04488d3d770702004d89f54c0f44ef"
        ),
        0xC8: bytes.fromhex(
            "49c745080000000041895d0441c745003800000041c7451000000000"
        ),
        0x32B: bytes.fromhex(
            "83fb044c89f1480f44cf488941404885d27417"
        ),
        0x355: bytes.fromhex("41c7450800000200"),
        0x367: bytes.fromhex("41807c244800754b"),
        0x3A5: bytes.fromhex("4983c6384c89f7e8cf920000"),
        0x3B4: bytes.fromhex("41c644244801"),
    }
    for relative, expected in fragments.items():
        require(blob, base + relative, expected, f"{label}/CreateQueue-lifecycle")


def verify_gc_classifier(blob: bytes, base: int, label: str) -> None:
    fragments = {
        # open("/dev/gc", 2)
        0x1E: bytes.fromhex("48 8d 3d 47 7e 00 00 be 02 00 00 00"),
        # ioctl(fd, 0xc004812e, &word)
        0x44: bytes.fromhex(
            "48 8d 55 cc be 2e 81 04 c0 89 c7 41 89 c6"
        ),
        # Conditional fixed mapping: 0xfe0200000, 0x4000, protection 0x22.
        0x72: bytes.fromhex(
            "48 bf 00 00 20 e0 0f 00 00 00 be 00 40 00 00 "
            "ba 22 00 00 00 b9 01 00 00 00"
        ),
    }
    for relative, expected in fragments.items():
        require(blob, base + relative, expected, f"{label}/gc-classifier")


def verify_get_reg_shadow_info(blob: bytes, base: int, label: str) -> None:
    # This getter rejects NULL, checks driver_state+8 == 0, then copies exactly
    # 32 + 8 bytes from state+0x168..+0x18f to the caller-owned output.
    require(blob, base + GET_REG_SHADOW_INFO_OFFSET,
            bytes.fromhex(
                "4885ff7413488d0dccf40100b801006d8a837908007407c3"
                "b803006d8ac3488b81880100004889472031c0c5fc108168"
                "010000c5fc1107c3"
            ), f"{label}/GetRegShadowInfo")

    # AGR is another pure state getter, not a queue query: same class-zero
    # gate and another adjacent 40-byte shadow block.
    require(blob, base + GET_REG_SHADOW_INFO_AGR_OFFSET,
            bytes.fromhex(
                "4885ff7413488d0d8cf40100b801006d8a837908007407c3"
                "b803006d8ac3488b81b00100004889472031c0c5fc108190"
                "010000c5fc1107c3"
            ), f"{label}/GetRegShadowInfoAgr")


def verify_common_submit_is_not_a_probe(blob: bytes, base: int,
                                        label: str) -> None:
    fragments = {
        # Lock queue+0x38 before reading the caller descriptor.
        0x18: bytes.fromhex(
            "4c8d67384989fe4989f74c89e7488b03488945d0e8df9c0000"
        ),
        # Only after successful lock, dereference descriptor +0/+8/+0xc.
        0x62: bytes.fromhex(
            "498b07488945c0418b47088945c8410fb6470c8845cc"
        ),
        # Dispatch through the selected backend callback.
        0x111: bytes.fromhex(
            "418b8520010000488d75b04c89f7486bc07841ff540550"
        ),
    }
    for relative, expected in fragments.items():
        require(blob, base + relative, expected,
                f"{label}/SubmitCommandBuffer-safety")


def verify_graphics_backend(blob: bytes, base: int, label: str) -> None:
    """Pin the class-1 fast path and its direct use of the caller command VA."""
    function = blob[base + GRAPHICS_BACKEND_OFFSET:
                    base + GRAPHICS_BACKEND_OFFSET + GRAPHICS_BACKEND_SIZE]
    if hashlib.sha256(function).hexdigest() != GRAPHICS_BACKEND_SHA256:
        raise SystemExit(f"{label}/graphics-backend hash mismatch")
    fragments = {
        # Resolve driver_state and select class-1 fast path; other classes
        # tail-call the alternate backend at +0x1450 rather than failing.
        0x40: bytes.fromhex("488d1dc1170200837b08010f85cd010000"),
        # Load the command pointer directly from submit_info+0.
        0x73: bytes.fromhex("4c89e0498b0c244885c90f840d020000"),
        # Load submit_info+8 and encode pointer/count into the ring record.
        0x95: bytes.fromhex(
            "8b500848c1e2204809ca48b9ffff0000ffff0f004821d148894db8"
        ),
        # Enqueue the encoded local descriptor through the internal backend.
        0x2E0: bytes.fromhex(
            "8b771085f674104c8d45b0ba03000000e88b780000eb13"
        ),
    }
    for relative, expected in fragments.items():
        require(blob, base + GRAPHICS_BACKEND_OFFSET + relative, expected,
                f"{label}/graphics-backend")


def verify_class0_backend(blob: bytes, base: int, label: str) -> None:
    function = blob[base + CLASS0_BACKEND_OFFSET:
                    base + CLASS0_BACKEND_OFFSET + CLASS0_BACKEND_SIZE]
    if hashlib.sha256(function).hexdigest() != CLASS0_BACKEND_SHA256:
        raise SystemExit(f"{label}/class0-backend hash mismatch")
    fragments = {
        # Consume the two zero-or-command records built by common submit.
        0x73: bytes.fromhex("488b064885c00f8428010000"),
        0x1D0: bytes.fromhex("488b46104885c07440"),
        # Submit one or two translated records through driver helper +0xad80.
        0x285: bytes.fromhex("418b7d048b73044489f24c89f9e899960000"),
        0x484: bytes.fromhex("418b7d048b7304488d8d50ffffffba01000000e894940000"),
    }
    for relative, expected in fragments.items():
        require(blob, base + CLASS0_BACKEND_OFFSET + relative, expected,
                f"{label}/class0-backend")


def verify_class0_ioctl(blob: bytes, base: int, label: str) -> None:
    function = blob[base + CLASS0_IOCTL_OFFSET:
                    base + CLASS0_IOCTL_OFFSET + CLASS0_IOCTL_SIZE]
    if hashlib.sha256(function).hexdigest() != CLASS0_IOCTL_SHA256:
        raise SystemExit(f"{label}/class0-ioctl hash mismatch")
    fragments = {
        # struct: queue/type u32, doubled record count u32, records VA u64,
        # output/status qword initialized to one.
        0x12: bytes.fromhex(
            "01d231db498b06488945e88975d08955d4be328118c048894dd8"
            "48c745e001000000"
        ),
        # ioctl(fd, 0xc0188132, &arg24).
        0x3C: bytes.fromhex("488d55d0e89b0a0000"),
        # Success is ioctl==0 and returned status low DWORD==0.
        0x45: bytes.fromhex("85c075108b45e031db85c089056e8201000f94c3"),
    }
    for relative, expected in fragments.items():
        require(blob, base + CLASS0_IOCTL_OFFSET + relative, expected,
                f"{label}/class0-ioctl")


def verify_class0_lazy_registration(blob: bytes, base: int, label: str) -> None:
    register = blob[base + CLASS0_REGISTER_OFFSET:
                    base + CLASS0_REGISTER_OFFSET + CLASS0_REGISTER_SIZE]
    packet = blob[base + CLASS0_INIT_PACKET_OFFSET:
                  base + CLASS0_INIT_PACKET_OFFSET + CLASS0_INIT_PACKET_SIZE]
    if hashlib.sha256(register).hexdigest() != CLASS0_REGISTER_SHA256:
        raise SystemExit(f"{label}/class0-register hash mismatch")
    if hashlib.sha256(packet).hexdigest() != CLASS0_INIT_PACKET_SHA256:
        raise SystemExit(f"{label}/class0-init-packet hash mismatch")
    # Registration copies 56 bytes from the primary record, optionally
    # overlays 16 bytes from a secondary record, and issues ioctl 0xc0488131.
    require(blob, base + CLASS0_REGISTER_OFFSET + 0x2E,
            bytes.fromhex("c5fc1002c5fc104a1cc5fc1145a4c5fc114dc0"),
            f"{label}/class0-register-primary")
    require(blob, base + CLASS0_REGISTER_OFFSET + 0x41,
            bytes.fromhex("4885c97410c5f81001c5f81145c0c745e401000000"),
            f"{label}/class0-register-secondary")
    require(blob, base + CLASS0_REGISTER_OFFSET + 0x56,
            bytes.fromhex("488d55a0be318148c031c031dbe8980b0000"),
            f"{label}/class0-register-ioctl")
    # The tiny packet constructor emits three DWORDs and returns writer+12.
    require(blob, base + CLASS0_INIT_PACKET_OFFSET,
            bytes.fromhex("31c085f6c707002801c0"),
            f"{label}/class0-init-packet")
    require(blob, base + CLASS0_INIT_PACKET_OFFSET + 0x58,
            bytes.fromhex("894708488d470cc3"),
            f"{label}/class0-init-packet-end")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--system",
        type=Path,
        default=Path("research/gpu/dumps/system-libSceAgcDriver.sprx"),
    )
    parser.add_argument(
        "--runtime",
        type=Path,
        default=Path("research/gpu/dumps/game-libSceAgcDriver.sprx.bin"),
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    system = args.system.read_bytes()
    runtime = args.runtime.read_bytes()

    verify_module_initializer_elf(system)
    verify_module_initializer_code(system, 0x4000, "system")
    verify_module_finalizer_code(system, 0x4000, "system")
    verify_wait_safe_is_packet_builder(system, 0x4000, "system")
    verify_module_initializer_code(runtime, 0, "runtime")
    verify_module_finalizer_code(runtime, 0, "runtime")
    verify_wait_safe_is_packet_builder(runtime, 0, "runtime")

    # The executable PT_LOAD is file offset 0x4000 -> virtual address 0.
    require(system, 0x4000 + 0x2020, CREATE_QUEUE, "system/CreateQueue")
    require(system, 0x4000 + 0x2960, SUBMIT_DCB, "system/SubmitDcb")
    verify_copy_shape(system, 0x4000 + 0x19B0, "system")
    verify_setup_async(system, 0x4000 + SETUP_ASYNC_OFFSET, "system")
    verify_driver_init(system, 0x4000 + DRIVER_INIT_OFFSET, "system")
    verify_create_queue_lifecycle(system, 0x4000 + 0x2030, "system")
    verify_gc_classifier(system, 0x4000 + GC_CLASSIFIER_OFFSET, "system")
    verify_get_reg_shadow_info(system, 0x4000, "system")
    verify_common_submit_is_not_a_probe(system, 0x4000 + 0x19B0, "system")
    verify_graphics_backend(system, 0x4000, "system")
    verify_class0_backend(system, 0x4000, "system")
    verify_class0_ioctl(system, 0x4000, "system")
    verify_class0_lazy_registration(system, 0x4000, "system")
    require(system, 0x4000 + SDMA_COPY_LINEAR_BLOCKING_OFFSET,
            SDMA_COPY_LINEAR_BLOCKING, "system/SdmaCopyLinearBlocking")
    for name, offset in {
        "RegisterOwner": 0x6B00,
        "RegisterDefaultOwner": 0x6B70,
        "GetDefaultOwner": 0x6B80,
        "GetOwnerName": 0x6C60,
    }.items():
        require(system, 0x4000 + offset, UNSUPPORTED_OWNER_RESULT,
                f"system/{name}")

    # The mapped-module dump starts at module virtual address zero.
    require(runtime, 0x2020, CREATE_QUEUE, "runtime/CreateQueue")
    require(runtime, 0x2960, SUBMIT_DCB, "runtime/SubmitDcb")
    verify_copy_shape(runtime, 0x19B0, "runtime")
    verify_setup_async(runtime, SETUP_ASYNC_OFFSET, "runtime")
    verify_driver_init(runtime, DRIVER_INIT_OFFSET, "runtime")
    verify_create_queue_lifecycle(runtime, 0x2030, "runtime")
    verify_gc_classifier(runtime, GC_CLASSIFIER_OFFSET, "runtime")
    verify_get_reg_shadow_info(runtime, 0, "runtime")
    verify_common_submit_is_not_a_probe(runtime, 0x19B0, "runtime")
    verify_graphics_backend(runtime, 0, "runtime")
    verify_class0_backend(runtime, 0, "runtime")
    verify_class0_ioctl(runtime, 0, "runtime")
    verify_class0_lazy_registration(runtime, 0, "runtime")
    require(runtime, SDMA_COPY_LINEAR_BLOCKING_OFFSET,
            SDMA_COPY_LINEAR_BLOCKING, "runtime/SdmaCopyLinearBlocking")
    for name, offset in {
        "RegisterOwner": 0x6B00,
        "RegisterDefaultOwner": 0x6B70,
        "GetDefaultOwner": 0x6B80,
        "GetOwnerName": 0x6C60,
    }.items():
        require(runtime, offset, UNSUPPORTED_OWNER_RESULT, f"runtime/{name}")
    if (system[0x4000 + SETUP_ASYNC_OFFSET :
              0x4000 + SETUP_ASYNC_OFFSET + SETUP_ASYNC_SIZE] !=
            runtime[SETUP_ASYNC_OFFSET : SETUP_ASYNC_OFFSET + SETUP_ASYNC_SIZE]):
        raise SystemExit("SetupAsyncGraphics differs between system and runtime")
    if (system[0x4000 + DRIVER_INIT_OFFSET :
              0x4000 + DRIVER_INIT_OFFSET + DRIVER_INIT_SIZE] !=
            runtime[DRIVER_INIT_OFFSET : DRIVER_INIT_OFFSET + DRIVER_INIT_SIZE]):
        raise SystemExit("driver initializer differs between system and runtime")

    result = {
        "firmware": "12.02",
        "system_runtime_equal": {
            "create_queue_wrapper": True,
            "submit_dcb_wrapper": True,
            "submit_info_copy_shape": True,
            "setup_async_graphics": True,
            "driver_initializer": True,
            "gc_classifier": True,
            "get_reg_shadow_info": True,
            "get_reg_shadow_info_agr": True,
            "common_submit_safety_path": True,
            "graphics_backend": True,
            "class0_backend": True,
            "class0_ioctl": True,
            "class0_lazy_registration": True,
            "owner_exports_are_unsupported_stubs": True,
            "module_initializer_chain": True,
            "module_finalizer_chain": True,
            "sdma_copy_linear_blocking_stub": True,
            "wait_until_safe_is_packet_builder": True,
        },
        "create_queue": {
            "export_offset": "0x2020",
            "internal_offset": "0x2030",
            "effect": "ecx=0; tail-call internal implementation",
            "default_queue_offset": "0x228b8",
            "header_size": "0x38",
            "lock_context_offset": "0x38",
            "aux_offset": "0x40",
            "created_sentinel_offset": "0x48",
            "created_sentinel_value": 1,
            "duplicate_check_skips_creation_when_nonzero": True,
            "safe_as_read_only_getter": False,
        },
        "submit_dcb": {
            "export_offset": "0x2960",
            "common_submit_offset": "0x19b0",
            "effect": "rsi=caller_rdi; rdi=default graphics queue; tail-call",
        },
        "submit_info": {
            "pointer_offset": 0,
            "dword_count_offset": 8,
            "byte_0c_offset": 12,
            "minimum_copied_size": 13,
        },
        "setup_async_graphics": {
            "export_offset": "0x3f30",
            "argument": "boolean-like agrEnabled",
            "backend_mode_literal": 1,
            "publishes_setup_state_low_nibble": 1,
            "publishes_submit_mode_from_argument": True,
            "proves_default_graphics_queue_creation": False,
        },
        "driver_initializer": {
            "offset": "0x7c20",
            "dt_init": "0x10",
            "relative_callback_slot": "0x14108",
            "relative_callback_addend": "0x8070",
            "trampoline_target": "0x7c20",
            "module_load_attempts_full_initialization": True,
            "process_class_0_queue_indices": [0, 4],
            "process_class_1_queue_indices": [3],
            "calls_public_create_queue_wrapper_internally": True,
            "application_should_copy_queue_object": False,
            "application_should_call_create_queue_after_load": False,
            "successful_module_load_proves_initializer_success": False,
        },
        "driver_finalizer": {
            "dt_fini": "0xb940",
            "normal_callback_offset": "0x8080",
            "normal_callback_bytes": "31c0c3",
            "normal_callback_effect": "return 0",
            "drains_or_waits_for_gpu": False,
            "safe_timeout_cleanup_proven": False,
        },
        "gc_classifier": {
            "offset": "0x8090",
            "device": "/dev/gc",
            "open_mode": 2,
            "ioctl": "0xc004812e",
            "conditional_fixed_mapping": {
                "address": "0xfe0200000",
                "size": "0x4000",
                "protection": "0x22",
            },
            "safe_to_reproduce_manually": False,
        },
        "get_reg_shadow_info": {
            "export_offset": "0x3430",
            "nid": "CP-kVAMmWVw",
            "public_name_correlation": "sceAgcDriverGetRegShadowInfo",
            "null_output_result": "0x8a6d0003",
            "nonzero_process_class_result": "0x8a6d0001",
            "class_zero_success_result": 0,
            "output_bytes": 40,
            "reads_driver_state_only": True,
            "ioctl_calls": 0,
            "queue_calls": 0,
            "submit_calls": 0,
        },
        "public_getter_audit": {
            "source_catalog_firmware": "3.20",
            "target_binary_firmware": "12.02",
            "named_queue_getter_present": False,
            "get_reg_shadow_info_agr": {
                "export_offset": "0x3470",
                "nid": "ME1eUot7+Qw",
                "class_zero_gate": True,
                "output_bytes": 40,
                "reads_queue_object": False,
                "mutates_driver_state": False,
            },
            "get_reserved_dmem_for_agc": {
                "export_offset": "0x9d0",
                "nid": "Um-jkyDy9rI",
                "reads_queue_object": False,
            },
            "conclusion": "no public pure getter exposes queue+0x48",
        },
        "invalid_submit_probe": {
            "safe": False,
            "locks_queue_before_descriptor_read": True,
            "dereferences_descriptor": True,
            "dispatches_backend_callback": True,
        },
        "submit_return_contract": {
            "returns_backend_enqueue_result_after_unlock": True,
            "polls_caller_fence": False,
            "proves_gpu_completion": False,
        },
        "graphics_backend_class1_path": {
            "callback_offset": "0x1100",
            "size": "0x350",
            "sha256": GRAPHICS_BACKEND_SHA256,
            "driver_state_offset": "0x22908",
            "process_class_dword_offset": "0x22910",
            "fast_path_class": 1,
            "other_class_tailcall_offset": "0x1450",
            "callback_pointer_offset": "0x22958",
            "loads_command_pointer_from_submit_info": True,
            "loads_dword_count_from_submit_info": True,
            "copies_command_dwords_before_enqueue": False,
            "caller_mapping_lifetime_requirement_proven_for_class1_only": True,
        },
        "graphics_backend_class0_path": {
            "offset": "0x1450",
            "size": "0x4cd",
            "sha256": CLASS0_BACKEND_SHA256,
            "selected_by_process_class": 0,
            "translates_submit_records": True,
            "driver_helper_offset": "0xad80",
            "copies_command_dwords_before_driver_call": False,
            "caller_mapping_lifetime_contract_proven": False,
        },
        "class0_submit_ioctl": {
            "helper_offset": "0xad80",
            "size": "0x74",
            "sha256": CLASS0_IOCTL_SHA256,
            "request": "0xc0188132",
            "argument_bytes": 24,
            "fields": {
                "queue_or_type_u32": 0,
                "doubled_record_count_u32": 4,
                "translated_records_va_u64": 8,
                "output_status_qword": 16
            },
            "output_status_initial_value": 1,
            "success_requires_ioctl_zero": True,
            "success_requires_output_status_low32_zero": True,
            "submit_success_proves_gpu_completion": False,
            "kernel_pinning_or_command_copy_proven": False
        },
        "class0_lazy_registration": {
            "trigger": "per-queue registration counter is zero",
            "packet_builder_offset": "0x5480",
            "packet_builder_size": "0x60",
            "packet_builder_sha256": CLASS0_INIT_PACKET_SHA256,
            "packet_header": "0xc0012800",
            "register_helper_offset": "0xac60",
            "register_helper_size": "0x98",
            "register_helper_sha256": CLASS0_REGISTER_SHA256,
            "register_ioctl": "0xc0488131",
            "register_argument_bytes": 72,
            "automatic_on_first_submit": True,
            "application_registration_call_required": False,
            "proves_private_command_mapping_gpu_visible": False
        },
        "sdma_copy_linear_blocking": {
            "export_offset": "0x7ab0",
            "nid": "bQ+En9GY3PM",
            "logs_unsupported_path": True,
            "constant_result": "0x8a6d0001",
            "usable_as_safer_visibility_probe": False,
        },
        "wait_until_safe_for_rendering": {
            "export_offset": "0x7450",
            "nid": "u8BkdHb1+Po",
            "size": "0x1c3",
            "sha256": WAIT_SAFE_SHA256,
            "mutates_command_writer": True,
            "emits_wait_reg_mem_packet": True,
            "blocks_cpu_until_gpu_idle": False,
            "usable_as_timeout_drain": False,
        },
        "owner_exports": {
            "register_owner": "0x6b00",
            "register_default_owner": "0x6b70",
            "get_default_owner": "0x6b80",
            "get_owner_name": "0x6c60",
            "constant_result": "0x8a6c9018",
            "usable_for_probe": False,
        },
        "queue_initialized": False,
        "submitted_or_executed": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="") if args.json else print("AGC queue/submit static proof: OK")


if __name__ == "__main__":
    main()
