#!/usr/bin/env python3
"""Host-only positive/negative tests for the native direct-memory layout."""
import unittest

ARENA = 0x10000
ALIGN = 0x4000
REGIONS = {
    "geometry_header": (0x0000, 376, 8),
    "pixel_header": (0x1000, 384, 8),
    "pixel_code": (0x2000, 2304, 0x100),
    "geometry_code": (0x3700, 736, 0x100),
    "cx_guarded": (0x5000 - 32, 32 + 0x110 + 32, 8),
    "uc_guarded": (0x6000 - 32, 32 + 0x18 + 32, 8),
    "geometry_snapshot": (0x7000, 376, 8),
    "pixel_snapshot": (0x8000, 384, 8),
}


def validate(regions=REGIONS, arena=ARENA, arena_alignment=ALIGN):
    if arena <= 0 or arena % arena_alignment:
        raise ValueError("arena alignment")
    values = list(regions.items())
    for name, (start, size, alignment) in values:
        if start < 0 or size <= 0 or start + size > arena:
            raise ValueError(f"range: {name}")
        # Guarded outputs intentionally start 32 bytes before their aligned
        # payload; all listed region starts still meet their required ABI.
        if start % alignment:
            raise ValueError(f"alignment: {name}")
    for i, (left, (a, n, _)) in enumerate(values):
        for right, (b, m, _) in values[i + 1:]:
            if a < b + m and b < a + n:
                raise ValueError(f"alias: {left}/{right}")
    return True


class DirectArenaTests(unittest.TestCase):
    def test_selected_layout(self):
        self.assertTrue(validate())

    def test_reject_overlap(self):
        bad = dict(REGIONS); bad["pixel_header"] = (0x100, 384, 8)
        with self.assertRaisesRegex(ValueError, "alias"):
            validate(bad)

    def test_reject_out_of_bounds(self):
        bad = dict(REGIONS); bad["pixel_snapshot"] = (0xff00, 384, 8)
        with self.assertRaisesRegex(ValueError, "range"):
            validate(bad)

    def test_reject_code_misalignment(self):
        bad = dict(REGIONS); bad["pixel_code"] = (0x2001, 2304, 0x100)
        with self.assertRaisesRegex(ValueError, "alignment"):
            validate(bad)

    def test_reject_bad_arena_granularity(self):
        with self.assertRaisesRegex(ValueError, "arena alignment"):
            validate(arena=0xf000)


if __name__ == "__main__":
    unittest.main()
