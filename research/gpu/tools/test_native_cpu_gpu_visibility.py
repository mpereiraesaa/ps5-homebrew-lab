#!/usr/bin/env python3
import unittest

from verify_native_cpu_gpu_visibility import (
    addresses,
    cache_line_instruction_addresses,
)


class CacheInstructionClassifierTests(unittest.TestCase):
    def test_mfence_is_not_classified_as_cache_line_maintenance(self) -> None:
        self.assertEqual(cache_line_instruction_addresses(bytes.fromhex("0faef0"), 0x1000), [])

    def test_clflush_memory_modrm_is_detected(self) -> None:
        self.assertEqual(
            cache_line_instruction_addresses(bytes.fromhex("0fae38"), 0x2000),
            ["0x2000"],
        )

    def test_clflushopt_and_clwb_memory_forms_are_detected(self) -> None:
        blob = bytes.fromhex("660fae38660fae30")
        self.assertEqual(
            cache_line_instruction_addresses(blob, 0x3000),
            ["0x3000", "0x3004"],
        )

    def test_register_modrm_forms_are_rejected(self) -> None:
        self.assertEqual(
            cache_line_instruction_addresses(bytes.fromhex("0faef8660faef0"), 0x4000),
            [],
        )

    def test_literal_address_scan(self) -> None:
        self.assertEqual(addresses(b"xx\x0f\x09yy", b"\x0f\x09", 0x5000), ["0x5002"])


if __name__ == "__main__":
    unittest.main()
