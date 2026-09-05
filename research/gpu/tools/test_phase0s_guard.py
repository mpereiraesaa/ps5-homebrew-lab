#!/usr/bin/env python3
import unittest

from phase0s_guard import START, classify


class Phase0SGuardTests(unittest.TestCase):
    def test_complete_allows_close(self):
        log = (START + "\nqueue pristine and BatchMap accepted state=3\n"
               "SubmitDcb returned rc=0x00000000\n"
               "GPU ownership complete fence=0\n"
               "phase0S exit result=0 submitted=yes-complete\n")
        decision = classify(log)
        self.assertTrue(decision["close_allowed"])
        self.assertTrue(decision["completion_proven"])

    def test_park_forbids_close(self):
        log = (START + "\nqueue pristine and BatchMap accepted state=3\n"
               "SubmitDcb returned rc=0x00000000\n"
               "PARKED_PHASE0S reason=fence timeout; retain driver, process and "
               "mapping; DO_NOT_CLOSE_FAKE00000\n")
        self.assertFalse(classify(log)["close_allowed"])

    def test_empty_and_truncated_forbid_close(self):
        self.assertFalse(classify("")["close_allowed"])
        self.assertFalse(classify(START + "\n")["close_allowed"])

    def test_pre_submit_clean_allows_close(self):
        log = START + "\nphase0S exit result=11 submitted=no\n"
        decision = classify(log)
        self.assertTrue(decision["close_allowed"])
        self.assertFalse(decision["completion_proven"])


if __name__ == "__main__":
    unittest.main()
