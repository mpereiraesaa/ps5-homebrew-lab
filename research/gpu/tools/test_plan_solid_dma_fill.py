#!/usr/bin/env python3
import unittest

from plan_solid_dma_fill import DMA_MAX_BYTES, tiled_size


class SolidDmaFillPlanTests(unittest.TestCase):
    def test_4k_tiled_footprint(self):
        self.assertEqual(tiled_size(3840, 2160), 0x02000000)

    def test_1080p_tiled_footprint(self):
        self.assertEqual(tiled_size(1920, 1080), 0x00880000)

    def test_4k_fits_one_dma_data(self):
        self.assertLessEqual(tiled_size(3840, 2160), DMA_MAX_BYTES)

    def test_invalid_dimensions(self):
        for dimensions in ((0, 1), (1, 0), (-1, 1), (1, -1)):
            with self.subTest(dimensions=dimensions):
                with self.assertRaises(ValueError):
                    tiled_size(*dimensions)


if __name__ == "__main__":
    unittest.main()
