#!/usr/bin/env python3
import unittest

from stage_c_guard import State, classify


SUCCESS = """AGC native Stage C v1
stage_c_fill_bytes=0x00000100
STAGE_C_TRANSACTION_STARTED
stage_c_submit=0x00000000
STAGE_C_GPU_FENCE_ZERO
stage_c_target_matches=true
stage_c_prefix_canary_intact=true
stage_c_suffix_canary_intact=true
stage_c_outside_untouched=true
stage_c_arenas_scrubbed=true
data_batch_unmap=0x00000000
data_batch_unmap_processed=0x00000001
data_direct_release=0x00000000
data_virtual_release=0x00000000
command_batch_unmap=0x00000000
command_batch_unmap_processed=0x00000001
command_direct_release=0x00000000
command_virtual_release=0x00000000
agc_unload=0x00000000
STAGE_C_COMPLETE cleanup complete; parked-safe; close exact title PPSA99998
"""


class StageCGuardTests(unittest.TestCase):
    def test_complete(self):
        result = classify(SUCCESS, 256)
        self.assertEqual(result["state"], State.COMPLETE.value)
        self.assertTrue(result["close_allowed"])

    def test_wrong_size_retains(self):
        result = classify(SUCCESS, 4096)
        self.assertFalse(result["close_allowed"])

    def test_each_required_observation_retains(self):
        for marker in (
            "stage_c_submit=0x00000000", "STAGE_C_GPU_FENCE_ZERO",
            "stage_c_target_matches=true", "stage_c_prefix_canary_intact=true",
            "stage_c_suffix_canary_intact=true", "stage_c_outside_untouched=true",
            "data_batch_unmap=0x00000000", "agc_unload=0x00000000",
        ):
            with self.subTest(marker=marker):
                self.assertFalse(classify(SUCCESS.replace(marker, ""), 256)["close_allowed"])

    def test_park_overrides_complete(self):
        result = classify(SUCCESS + "PARKED_STAGE_C_TRANSACTION\n", 256)
        self.assertEqual(result["state"], State.PARKED.value)
        self.assertFalse(result["close_allowed"])

    def test_out_of_order_retains(self):
        altered = SUCCESS.replace(
            "STAGE_C_GPU_FENCE_ZERO\nstage_c_target_matches=true",
            "stage_c_target_matches=true\nSTAGE_C_GPU_FENCE_ZERO",
        )
        self.assertFalse(classify(altered, 256)["close_allowed"])

    def test_pretransaction_cleanup_is_close_safe(self):
        result = classify("STAGE_C_PRE_TRANSACTION_CLEANUP_COMPLETE\n", 256)
        self.assertEqual(result["state"], State.PRE_TRANSACTION_EXIT.value)
        self.assertTrue(result["close_allowed"])


if __name__ == "__main__":
    unittest.main()
