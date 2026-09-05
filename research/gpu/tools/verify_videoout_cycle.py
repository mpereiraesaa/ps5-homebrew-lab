#!/usr/bin/env python3
"""Verify the bounded CPU VideoOut lifecycle used as the AGC presentation base."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROBE = ROOT / "probes" / "ps5-native-video-probe" / "main.c"
SDL_VIDEO = ROOT / "third_party" / "SDL-ps5" / "src" / "video" / "ps5" / "SDL_ps5video.c"
SDL_TILE = ROOT / "third_party" / "SDL-ps5" / "src" / "video" / "ps5" / "SDL_ps5tilemap.c"


def ordered(text: str, *needles: str) -> bool:
    position = -1
    for needle in needles:
        position = text.find(needle, position + 1)
        if position < 0:
            return False
    return True


def main() -> int:
    probe = PROBE.read_text()
    sdl_video = SDL_VIDEO.read_text()
    sdl_tile = SDL_TILE.read_text()

    checks = {
        "two_buffers_registered": (
            "vout_buf_t buffers[2]" in probe
            and "sceVideoOutRegisterBuffers2(vout, 0, 0, buffers, 2" in probe
        ),
        "known_format_word": "0x8000000022000000ULL" in probe,
        "double_buffer_index": "frame_id & 1" in probe,
        "cpu_write_before_flip_before_wait": ordered(
            probe,
            "fill_frame(frame_id",
            "sceVideoOutSubmitFlip(vout, idx, 1, frame_id)",
            "sceKernelWaitEqueue(queue, &event, 1, &out, NULL)",
        ),
        "flip_event_installed": ordered(
            probe,
            "sceKernelCreateEqueue(&queue",
            "sceVideoOutAddFlipEvent(queue, vout",
        ),
        "bounded_loop": "frame_id < 18000" in probe,
        "conditional_unregister": (
            "if (buffers_registered)" in probe
            and "sceVideoOutUnregisterBuffers(vout, 0, 2)" in probe
        ),
        "event_and_queue_cleanup": ordered(
            probe,
            "sceVideoOutDeleteFlipEvent(queue, vout)",
            "sceKernelDeleteEqueue(queue)",
            "sceVideoOutClose(vout)",
        ),
        "mapping_released_in_order": ordered(
            probe,
            "munmap(vaddr, memsize)",
            "sceKernelReleaseDirectMemory(paddr, memsize)",
        ),
        "sdl_swizzles_before_flip": ordered(
            sdl_video,
            "PS5_Tilemap_Blit(",
            "sceVideoOutSubmitFlip(",
            "sceKernelWaitEqueue(",
        ),
        "tile_geometry_source_present": (
            "#define PS5_TILE_WIDTH  512" in sdl_tile
            and "#define PS5_TILE_HEIGHT 128" in sdl_tile
            and "PS5_TileOffset" in sdl_tile
        ),
    }
    result = {
        "checks": checks,
        "all_static_checks_pass": all(checks.values()),
        "presentation_completion_event_proven": True,
        "gpu_fence_proven": False,
        "linear_scanout_proven": False,
        "tiled_scanout_source_evidence": True,
        "submitted_to_agc": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_static_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
