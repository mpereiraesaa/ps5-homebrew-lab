import importlib.util
import struct
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "capture_agc_defaults_cpu", HERE / "capture_agc_defaults_cpu.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def records(*items):
    return b"".join(struct.pack("<II", key, encoded) for key, encoded in items)


class FakeMap:
    def __init__(self, start=0x1000, end=0x2000, perms="r--"):
        self.start, self.end, self.perms = start, end, perms


class AgcDefaultsParserTests(unittest.TestCase):
    def test_accepts_count_delimited_banks(self):
        decoded, banks = MODULE.decode_type_records(
            records((1, 0), (2, 4), (3, 1), (4, 2)), 4
        )
        self.assertEqual(len(decoded), 4)
        self.assertEqual(banks, {0: [0, 1], 1: [0], 2: [0]})

    def test_rejects_count_and_size(self):
        with self.assertRaises(MODULE.ParseError):
            MODULE.decode_type_records(b"", 0)
        with self.assertRaises(MODULE.ParseError):
            MODULE.decode_type_records(records((1, 0)), 2)

    def test_rejects_duplicate_key(self):
        with self.assertRaisesRegex(MODULE.ParseError, "duplicate"):
            MODULE.decode_type_records(records((1, 0), (1, 4)), 2)

    def test_rejects_bank_three(self):
        with self.assertRaisesRegex(MODULE.ParseError, "bank selector"):
            MODULE.decode_type_records(records((1, 3)), 1)

    def test_rejects_non_contiguous_or_reordered_index(self):
        with self.assertRaisesRegex(MODULE.ParseError, "contiguous"):
            MODULE.decode_type_records(records((1, 4)), 1)
        with self.assertRaisesRegex(MODULE.ParseError, "contiguous"):
            MODULE.decode_type_records(records((1, 4), (2, 0)), 2)

    def test_map_guard_rejects_unreadable_cross_boundary_and_ambiguous(self):
        good = FakeMap()
        self.assertIs(MODULE.containing_map([good], 0x1100, 8), good)
        for maps, address, size in (
            ([FakeMap(perms="-w-")], 0x1100, 8),
            ([good], 0x1FFC, 8),
            ([good, FakeMap()], 0x1100, 8),
        ):
            with self.assertRaises(MODULE.ParseError):
                MODULE.containing_map(maps, address, size)

    def test_accepts_bounded_pointer_table(self):
        data = struct.pack("<2Q", 0x1100, 0x1110)
        self.assertEqual(
            MODULE.decode_pointer_table(data, 2, [FakeMap()]),
            [0x1100, 0x1110],
        )

    def test_rejects_pointer_count_and_size(self):
        with self.assertRaises(MODULE.ParseError):
            MODULE.decode_pointer_table(b"", 0, [FakeMap()])
        with self.assertRaisesRegex(MODULE.ParseError, "size"):
            MODULE.decode_pointer_table(struct.pack("<Q", 0x1100), 2, [FakeMap()])

    def test_rejects_null_or_unaligned_pointer(self):
        for pointer in (0, 0x1101):
            with self.subTest(pointer=pointer):
                with self.assertRaisesRegex(MODULE.ParseError, "null or unaligned"):
                    MODULE.decode_pointer_table(struct.pack("<Q", pointer), 1, [FakeMap()])

    def test_rejects_pointer_outside_readable_map(self):
        with self.assertRaisesRegex(MODULE.ParseError, "readable map"):
            MODULE.decode_pointer_table(struct.pack("<Q", 0x3000), 1, [FakeMap()])


if __name__ == "__main__":
    unittest.main()
