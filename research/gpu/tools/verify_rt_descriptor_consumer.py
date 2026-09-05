#!/usr/bin/env python3
"""Verify the San Andreas render-target descriptor consumer chain.

This deliberately checks exact byte-level evidence in the authorized runtime
dumps.  It does not claim the ABI is portable to another SDK or firmware.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def expect(blob: bytes, base: int, address: int, expected: bytes, label: str) -> None:
    actual = blob[address - base:address - base + len(expected)]
    if actual != expected:
        raise SystemExit(
            f"{label}: mismatch at {address:#x}: "
            f"expected {expected.hex()}, got {actual.hex()}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("eboot", type=Path)
    parser.add_argument("agc", type=Path)
    parser.add_argument("--agc-driver", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    eboot_base = 0x400000
    agc_base = 0x80058C000
    agc_driver_base = 0x800568000
    eboot = args.eboot.read_bytes()
    agc = args.agc.read_bytes()
    agc_driver = args.agc_driver.read_bytes()

    # Depth/stencil path: mov rax,[r13+0xee8]; test; branch; clear cached state;
    # mov rdi,[rsp+0x40]; mov edx,0x10; mov rsi,[rax+0x30]
    expect(eboot, eboot_base, 0x1F37F80,
           bytes.fromhex("498b85e80e00004885c00f8484000000"), "resource load")
    expect(eboot, eboot_base, 0x1F37F9B,
           bytes.fromhex("488b7c2440ba10000000488b7030"), "pointer and count")

    call_site = 0x1F37FA9
    expect(eboot, eboot_base, call_site, b"\xe8", "AGC call opcode")
    displacement = struct.unpack_from("<i", eboot, call_site - eboot_base + 1)[0]
    thunk = call_site + 5 + displacement
    if thunk != 0x4DC0D30:
        raise SystemExit(f"unexpected thunk {thunk:#x}")
    expect(eboot, eboot_base, thunk, bytes.fromhex("ff25"), "AGC thunk")
    got_disp = struct.unpack_from("<i", eboot, thunk - eboot_base + 2)[0]
    got_slot = thunk + 6 + got_disp
    target = struct.unpack_from("<Q", eboot, got_slot - eboot_base)[0]
    if target != agc_base + 0x4120:
        raise SystemExit(f"unexpected AGC target {target:#x}")

    # Color MRT path: copy sixteen pairs from view+0x28, adjust register IDs
    # for the MRT slot, then append them through the engine's pair cache.
    expect(eboot, eboot_base, 0x1F38315,
           bytes.fromhex("488b7728"), "color descriptor pointer")
    expect(eboot, eboot_base, 0x1F3832D,
           bytes.fromhex("c5fc1006c5fc104e20c5fc105640c5fc105e60"),
           "color descriptor 128-byte load")
    expect(eboot, eboot_base, 0x1F37F37,
           bytes.fromhex("488b3b8b4b08448b430c488b7424404489e2e8a2030000"),
           "per-MRT color binding call")
    expect(eboot, eboot_base, 0x1F48FB8,
           bytes.fromhex("488b4c24404989ca48c1e92849c1ea08458954240441884c2454"),
           "color primary address split")
    # The color constructor builds a normalized layout record at rsp+0x40.
    # These loads establish the raw provenance of the five layout DWORDs;
    # names such as width/pitch are deliberately deferred until corroborated.
    expect(eboot, eboot_base, 0x1F46979,
           bytes.fromhex("8b8c242c010000c4e379048c2430010000b4"),
           "color layout source loads")
    expect(eboot, eboot_base, 0x1F469B3,
           bytes.fromhex("894c2460488b8c2440010000c5f8114c2464"),
           "color layout stack normalization")
    expect(eboot, eboot_base, 0x1F48F62,
           bytes.fromhex("8b4424608b4c2464c1e00effc9"),
           "color id 0x3b0 low fields")
    expect(eboot, eboot_base, 0x1F48F7A,
           bytes.fromhex("2500c0ff0f4409c809c1"),
           "color id 0x3b0 combined fields")
    expect(eboot, eboot_base, 0x1F384A0,
           bytes.fromhex("4805c0030000488db560ffffffba100000004889c7e826fce702"),
           "color descriptor cache call")
    # The cache allocates a GPU-visible list through the same AGC NID, copies
    # count*8 bytes, and finalizes the cached range.
    expect(eboot, eboot_base, 0x4DB8118,
           bytes.fromhex("48637354488b3b4829c648c1e60348037328e8018c0000"),
           "pair-cache AGC allocation")
    expect(eboot, eboot_base, 0x4DB81E1,
           bytes.fromhex("8b7b5449c1e40348c1e0034c89ee4c89e248c1e70348037b284829c7"),
           "pair-cache copy sizing")

    # If no depth resource is bound, setup installs the immutable 16-pair
    # depth template through the cache writer instead.
    expect(eboot, eboot_base, 0x1F38014,
           bytes.fromhex("c5fc100d24edf304c5fe6f053cedf304c5fc1015f4ecf304"),
           "null-depth template load")
    expect(eboot, eboot_base, 0x1F3802C,
           bytes.fromhex("488b7c2450488db42420030000ba10000000"),
           "null-depth template arguments")

    # The large setup routine does not bind everything inline.  It constructs
    # small deferred commands whose vtables and executors preserve resource
    # identity until the backend context consumes them.  Keep this evidence
    # byte-checked so later naming of transition states cannot silently drift.
    expect(eboot, eboot_base, 0x614F7E0,
           struct.pack("<QQ", 0x19D3D90, 0x19D3DB0),
           "resource transition command vtable")
    expect(eboot, eboot_base, 0x614F800,
           struct.pack("<QQ", 0x19D3DC0, 0x19D3DF0),
           "ranged transition command vtable")
    expect(eboot, eboot_base, 0x19D3D90,
           bytes.fromhex("554889e5488b4628488b7710488b084889c7488b49105dffe1"),
           "resource transition executor")
    expect(eboot, eboot_base, 0x19D3DC0,
           bytes.fromhex("554889e5488b46288b57208b4f24448b4728488b77104c8b4f18"),
           "ranged transition executor arguments")
    expect(eboot, eboot_base, 0x19D3DDA,
           bytes.fromhex("488b384c8b9fa80000004889c75d41ffe3"),
           "ranged transition backend dispatch")
    # The concrete San Andreas backend installs vptr 0x61c5b08.  Its +0x10
    # method handles the resource-only command; +0xa8 consumes the ranged
    # command and copies its 16-byte state record into the command cache.
    expect(eboot, eboot_base, 0x1F4152A,
           bytes.fromhex("488d05d745280449bf080000008000000049894608"),
           "backend vptr installation")
    expect(eboot, eboot_base, 0x61C5B18,
           struct.pack("<Q", 0x1F59380), "backend resource transition slot")
    expect(eboot, eboot_base, 0x61C5BB0,
           struct.pack("<Q", 0x1F31890), "backend ranged transition slot")
    expect(eboot, eboot_base, 0x1F5939C,
           bytes.fromhex("48b908000000800000004881c7b0010000"),
           "resource transition state setup")
    expect(eboot, eboot_base, 0x1F59427,
           bytes.fromhex("e824c6fcff4889dfe8ecc9fcff"),
           "resource transition state assignment and release")
    expect(eboot, eboot_base, 0x1F31890,
           bytes.fromhex("554889e541574156415453488b87700200004989ce"),
           "ranged transition backend entry")
    expect(eboot, eboot_base, 0x1F31920,
           bytes.fromhex("c4c1781006c5f81100"),
           "ranged transition 16-byte cache write")

    # The apparent cache is backed by packet payload storage.  Engine helper
    # 0x4db6990 obtains a packet from libSceAgc+0x28d0; +0xd040 resolves its
    # payload pointer, which is then stored in the small/extended slot table.
    expect(eboot, eboot_base, 0x4DB69F9,
           bytes.fromhex("c1e60781c682000000e829b200004989c7"),
           "state packet allocation call")
    expect(eboot, eboot_base, 0x4DB6B0B,
           bytes.fromhex("e820b100004989c7488d7dc84c89feba01000000"),
           "state packet allocation and payload arguments")
    expect(eboot, eboot_base, 0x4DB6B27,
           bytes.fromhex("e814b10000488b45c8488b4dc0488b1d55dc9101488908"),
           "state packet payload resolution and write")
    expect(agc, agc_base, agc_base + 0x2971,
           bytes.fromhex("c1e3100fb7c681c30000fe3f81cb007600c041891e"),
           "state packet 0x76 header construction")
    expect(agc, agc_base, agc_base + 0xD040,
           bytes.fromhex("85d274094883c6084889f0eb14"),
           "state packet payload resolver")
    # The source description is a generic register-range tuple: two WORDs at
    # +0xcc/+0xce, a DWORD count at +0xd0 capped to 16, followed by consecutive
    # payload bytes.  This rules out treating packet 0x76 itself as a proven
    # render-target transition.
    expect(eboot, eboot_base, 0x1F364E2,
           bytes.fromhex("0fb781d000000041bd1000000083f810440f42e8"),
           "register-range count and cap")
    expect(eboot, eboot_base, 0x1F36506,
           bytes.fromhex("0fb781cc0000000fb789ce000000"),
           "register-range selector fields")
    expect(eboot, eboot_base, 0x1F366F0,
           bytes.fromhex("8b114983c7fc4883c10489104883c004"),
           "register-range consecutive DWORD copy")

    # Immediately before color/depth binding, setup emits a raw event through
    # libSceAgc+0x5ce0 with selector 7 and no address, then calls +0x7ad0.
    # Keep the ordering proven while leaving the event's public semantic name
    # unresolved.
    expect(eboot, eboot_base, 0x1F37ECF,
           bytes.fromhex("be0700000031d24889dfe8e28ee8024889dfe88a8fe802"),
           "pre-bind event and follow-up ordering")
    expect(agc, agc_base, agc_base + 0x5D1F,
           bytes.fromhex("4489f9c1e10e81c10000fe3f81c9004600c0"),
           "event packet 0x46 header construction")
    expect(agc, agc_base, agc_base + 0x5D3F,
           bytes.fromhex(
               "41b880800100490fa3c8730e400fb6c60d000400008945cc"),
           "partial-flush event-index encoding")
    # The follow-up is now byte-resolved across the AGC/driver boundary.
    # +0x7ad0 asks the driver for the size with selector 0, reserves exactly
    # three DWORD, then invokes the driver writer with selector 0.  Preserve
    # the literal packet without assigning an unsupported public semantic.
    expect(agc, agc_base, agc_base + 0x7ADA,
           bytes.fromhex("4889fb31ff4531f6e889f20000"),
           "post-event fixed packet size call")
    expect(agc, agc_base, agc_base + 0x7B44,
           bytes.fromhex("31f64531f6e882f20000"),
           "post-event fixed packet writer call")
    expect(agc, agc_base, agc_base + 0x28A60,
           struct.pack("<Q", agc_driver_base + 0x6C80),
           "post-event driver size GOT target")
    expect(agc, agc_base, agc_base + 0x28A90,
           struct.pack("<Q", agc_driver_base + 0x7050),
           "post-event driver writer GOT target")
    expect(agc_driver, agc_driver_base, agc_driver_base + 0x6C80,
           bytes.fromhex(
               "85ff741a89f84883c00348c1e8028d48074883f801b804000000"
               "0f45c1c3b803000000c3"),
           "post-event fixed packet size calculator")
    expect(agc_driver, agc_driver_base, agc_driver_base + 0x7050,
           bytes.fromhex(
               "31c085f60f94c08d0485007901c0890748b842030000000000c2"
               "48894704b803000000c3"),
           "post-event fixed packet serializer")
    # Earlier in the same setup, the engine calls its compound control encoder
    # in mode 2.  Attachment-derived bits select 0x0/0xc00 plus an optional
    # 0x3000 group; mode 2 emits raw event selector 0x10 before processing the
    # remaining masks.
    expect(eboot, eboot_base, 0x1F34E87,
           bytes.fromhex(
               "41f6c701ba000c0000b8000000004889dfbe020000000f44d0"
               "4584e48d82003000000f45d04584f60f45d031c94531c04531c9"
               "e8c134e802"),
           "render-target compound control arguments")
    expect(eboot, eboot_base, 0x4DB842A,
           bytes.fromhex("83fb0174154c89f7be1000000031d2e882890000"),
           "compound control mode-2 event")

    # A distinct deferred command reaches the already-proven color consumer.
    # Its executor forwards command+0x10 as the view, command+0x18 as slot,
    # and backend_context+0x230 as the pair cache.
    expect(eboot, eboot_base, 0x61C7B38,
           struct.pack("<Q", 0x1F63650), "deferred color command vtable")
    expect(eboot, eboot_base, 0x61C7B50,
           struct.pack("<Q", 0x1F636B0), "deferred color executor slot")
    expect(eboot, eboot_base, 0x1F636B0,
           bytes.fromhex("554889e5488b4710448b471831d231c9488b38b83002000048034620"),
           "deferred color executor arguments")
    expect(eboot, eboot_base, 0x1F636CC,
           bytes.fromhex("4889c65de91b4cfdff"),
           "deferred color tail-call")

    # Unreal's reflected ClearRenderTarget2D path is not a standalone AGC
    # clear.  The canvas command stream brackets a canvas operation with the
    # already-proven render-target setup and a teardown/unbind command.
    expect(eboot, eboot_base, 0x61C3BF0,
           struct.pack("<QQ", 0x1F13DE0, 0x1F13E20),
           "canvas render-target setup command vtable")
    expect(eboot, eboot_base, 0x61C3C10,
           struct.pack("<QQ", 0x1F13E30, 0x1F13E40),
           "canvas render-target teardown command vtable")
    expect(eboot, eboot_base, 0x1F13DE6,
           bytes.fromhex("4889fb488b7e20488d7310e81a0d0200"),
           "canvas setup executor to render-target setup")
    expect(eboot, eboot_base, 0x1F13E34,
           bytes.fromhex("488b7e205de9a2460200"),
           "canvas teardown executor to backend teardown")
    expect(eboot, eboot_base, 0x40D65C4,
           bytes.fromhex("e8377f6bfe"),
           "canvas operation between setup and teardown")
    expect(eboot, eboot_base, 0x40D6641,
           bytes.fromhex("488910"),
           "canvas teardown command vtable store")
    # The canvas operation is conclusively a draw: its deferred command reaches
    # backend 0x1f386a0, which emits an index/control packet and then calls the
    # AGC builder that materializes DRAW_INDEX_AUTO (PM4 opcode 0x2d).
    expect(eboot, eboot_base, 0x614F6F0,
           struct.pack("<QQ", 0x19D11C0, 0x19D11E0),
           "canvas draw command vtable")
    expect(eboot, eboot_base, 0x19D11C4,
           bytes.fromhex("488b46208b77108b57148b4f184889c75de9c6745600"),
           "canvas draw executor to backend draw")
    expect(eboot, eboot_base, 0x1F38751,
           bytes.fromhex("4c8dbb3002000031f631d24c89ffe81c87e802"),
           "canvas draw pre-packet")
    expect(eboot, eboot_base, 0x1F387A2,
           bytes.fromhex(
               "4c89ff4489f6488b840368020000488b4028488b5018e8a386e802"),
           "canvas DRAW_INDEX_AUTO call")
    expect(eboot, eboot_base, 0x66D7F50,
           struct.pack("<Q", agc_base + 0x5240),
           "DRAW_INDEX_AUTO AGC GOT target")
    expect(eboot, eboot_base, 0x66D7F60,
           struct.pack("<Q", agc_base + 0x69F0),
           "canvas pre-draw AGC GOT target")
    expect(agc, agc_base, agc_base + 0x52E8,
           bytes.fromhex("c701002d01c0897104895908"),
           "DRAW_INDEX_AUTO packet serializer")
    expect(agc, agc_base, agc_base + 0x6A82,
           bytes.fromhex("48ba007a01c043020020"),
           "canvas pre-draw packet serializer")

    # libSceAgc+0x4120 emits a five-DWORD packet.  The address comes from RSI,
    # count is masked to 14 bits, and the fixed type-3 header is 0xc0039f00.
    expect(agc, agc_base, agc_base + 0x41AE,
           bytes.fromhex("89f081e2ff3f0000"), "address/count inputs")
    expect(agc, agc_base, agc_base + 0x41BF,
           bytes.fromhex("c701009f03c0"), "packet header")
    expect(agc, agc_base, agc_base + 0x41D2,
           bytes.fromhex("4809d78971084889790c"), "count/address payload")

    result = {
        "schema": 1,
        "depth_stencil_direct": {
            "consumer": "0x1f37f80",
            "resource_field": "context+0xee8",
            "descriptor_field": "resource+0x30",
            "pair_count": 16,
            "call_site": hex(call_site),
            "pointer_passed_unmodified": True,
        },
        "color_mrt_cached": {
            "consumer": "0x1f382f0",
            "descriptor_field": "view+0x28",
            "pair_count": 16,
            "slot_adjusted": True,
            "cache_writer": "0x4db80e0",
            "primary_address_low_field": "descriptor+0x04",
            "primary_address_high_field": "descriptor+0x54",
            "layout_source_fields": {
                "stack+0x60": "source+0x12c",
                "stack+0x64": "source+0x130",
                "stack+0x68": "source+0x134",
                "stack+0x6c": "source+0x13c",
                "stack+0x70": "source+0x138",
            },
            "id_0x3b0_value":
                "((stack+0x64 - 1) & 0x3fff) | "
                "((stack+0x60 << 14) & 0x0fffc000) | "
                "((stack+0x70 << 28) & 0xf0000000)",
            "bound_before_depth_stencil": True,
        },
        "null_depth_stencil": {
            "template": "0x6e76d00",
            "pair_count": 16,
            "cache_writer": "0x4db80e0",
        },
        "deferred_setup": {
            "setup": "0x1f34b10",
            "resource_transition_vtables": ["0x614f7e0", "0x614f800"],
            "resource_transition_executors": ["0x19d3d90", "0x19d3dc0"],
            "backend_vptr": "0x61c5b08",
            "backend_resource_transition": "0x1f59380",
            "backend_resource_transition_effect":
                "deep-assign zero temporary into backend+0x1b0, then release",
            "backend_ranged_transition": "0x1f31890",
            "ranged_state_record_bytes": 16,
            "packet_allocator": {
                "engine_helper": "0x4db6990",
                "agc_builder": "libSceAgc+0x28d0",
                "header_base": "0xc0007600",
                "payload_resolver": "libSceAgc+0xd040",
                "writes_into_packet_payload": True,
                "source_tuple": {
                    "selector_0": "resource+0xcc",
                    "selector_1": "resource+0xce",
                    "count": "min(resource+0xd0, 16)",
                },
                "classification": "generic register-range write",
            },
            "pre_bind_event": {
                "call_site": "0x1f37ed9",
                "agc_builder": "libSceAgc+0x5ce0",
                "selector": 7,
                "address": 0,
                "header_base": "0xc0004600",
                "dwords": ["0xc0004600", "0x00000407"],
                "public_amd_candidate": "CS_PARTIAL_FLUSH",
                "follow_up": "libSceAgc+0x7ad0",
                "semantic_name_proven": False,
            },
            "post_event_fixed_packet": {
                "agc_helper": "libSceAgc+0x7ad0",
                "driver_size": "libSceAgcDriver+0x6c80",
                "driver_writer": "libSceAgcDriver+0x7050",
                "dword_count": 3,
                "dwords": ["0xc0017904", "0x00000342", "0xc2000000"],
                "pm4_classification": "SET_UCONFIG_REG",
                "register": "0xc342",
                "register_name_proven": False,
                "semantic_name_proven": False,
            },
            "compound_control": {
                "engine_helper": "0x4db8380",
                "mode": 2,
                "flags": "(color_bit ? 0xc00 : 0) | "
                         "((depth_or_stencil_bit) ? 0x3000 : 0)",
                "first_event_selector": 16,
                "event_builder": "libSceAgc+0x5ce0",
                "first_event_dwords": ["0xc0004600", "0x00000410"],
                "public_amd_candidate": "PS_PARTIAL_FLUSH",
                "classification": "synchronization/control encoder candidate",
                "official_semantics_proven": False,
            },
            "color_bind_vtable": "0x61c7b38",
            "color_bind_executor": "0x1f636b0",
            "color_bind_consumer": "0x1f382f0",
            "reflected_clear_route": {
                "setup_command_vtable": "0x61c3bf0",
                "setup_executor": "0x1f13de0",
                "render_target_setup": "0x1f34b10",
                "canvas_operation": "0x278e500",
                "teardown_command_vtable": "0x61c3c10",
                "teardown_executor": "0x1f13e30",
                "backend_teardown": "0x1f384e0",
                "draw_command_vtable": "0x614f6f0",
                "draw_executor": "0x19d11c0",
                "backend_draw": "0x1f386a0",
                "pre_draw_agc_builder": "libSceAgc+0x69f0",
                "draw_agc_builder": "libSceAgc+0x5240",
                "draw_packet": "DRAW_INDEX_AUTO",
                "draw_packet_header": "0xc0012d00",
                "standalone_hardware_clear_proven": False,
                "classification": "graphics draw bracketed by setup/teardown",
            },
            "clear_proven": False,
        },
        "thunk": hex(thunk),
        "got_slot": hex(got_slot),
        "agc_target": hex(target),
        "agc_offset": "0x4120",
        "nid": "ZvwO9euwYzc",
        "packet_header": "0xc0039f00",
        "target_writes": 0,
        "debugger_attach": False,
        "remote_calls": 0,
    }
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
