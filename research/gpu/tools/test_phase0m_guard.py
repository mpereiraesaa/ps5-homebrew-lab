#!/usr/bin/env python3
import unittest
import tempfile
from pathlib import Path

from phase0m_guard import State, classify


class Phase0MGuardTests(unittest.TestCase):
    def assert_state(self, log: str, state: State, close: bool) -> None:
        result = classify(log)
        self.assertEqual(result["state"], state.value)
        self.assertEqual(result["close_allowed"], close)
        self.assertEqual(result["retain_process_module_mapping"], not close)
        if close:
            self.assertEqual(result["automated_actions_forbidden"], [])
        else:
            self.assertIn("close_fake00000",
                          result["automated_actions_forbidden"])
            self.assertIn("stop_automation", result["automated_actions_allowed"])
            self.assertNotEqual(result["operator_recovery"], "none")

    def test_empty_is_not_started(self) -> None:
        self.assert_state("", State.NOT_STARTED, False)

    def test_pre_submit_failure_may_close(self) -> None:
        self.assert_state("AGC phase 0M exit result=11\n",
                          State.PRE_SUBMIT_EXIT, True)

    def test_proven_completion_may_close(self) -> None:
        self.assert_state("SubmitDcb returned rc=0x00000000\n"
                          "GPU completion verified target=0 fence=0\n"
                          "AGC phase 0M exit result=0\n",
                          State.GPU_COMPLETE, True)

    def test_each_park_marker_forbids_close(self) -> None:
        for marker in ("PARKED_AFTER_SUBMIT", "PARKED_SUBMIT_ERROR",
                       "PARKED_FENCE_TIMEOUT"):
            with self.subTest(marker=marker):
                self.assert_state(marker + "\n", State.PARKED, False)

    def test_truncated_after_submit_forbids_close(self) -> None:
        self.assert_state("SubmitDcb returned rc=0x00000000\n",
                          State.UNKNOWN_RETAIN, False)

    def test_completion_without_exit_forbids_close(self) -> None:
        self.assert_state("GPU completion verified target=0 fence=0\n",
                          State.UNKNOWN_RETAIN, False)

    def test_exit_after_submit_without_completion_forbids_close(self) -> None:
        self.assert_state("SubmitDcb returned rc=0x00000000\n"
                          "AGC phase 0M exit result=17\n",
                          State.UNKNOWN_RETAIN, False)

    def test_park_overrides_forged_or_stale_completion(self) -> None:
        self.assert_state("PARKED_FENCE_TIMEOUT\n"
                          "GPU completion verified target=0 fence=0\n"
                          "AGC phase 0M exit result=0\n",
                          State.PARKED, False)


class SupervisorIntegrationTests(unittest.TestCase):
    @staticmethod
    def supervisor_types():
        import sys
        tools_dir = Path(__file__).resolve().parents[3] / "tools"
        sys.path.insert(0, str(tools_dir))
        from night_supervisor import SafetyStop, Supervisor
        return SafetyStop, Supervisor

    def test_supervisor_refuses_parked_cleanup(self) -> None:
        SafetyStop, Supervisor = self.supervisor_types()
        with tempfile.TemporaryDirectory() as directory:
            supervisor = Supervisor("127.0.0.1", Path(directory) / "journal.jsonl")
            with self.assertRaises(SafetyStop):
                supervisor.require_phase0m_cleanup_safe("PARKED_FENCE_TIMEOUT\n")

    def test_supervisor_accepts_proven_completion(self) -> None:
        _, Supervisor = self.supervisor_types()
        with tempfile.TemporaryDirectory() as directory:
            supervisor = Supervisor("127.0.0.1", Path(directory) / "journal.jsonl")
            result = supervisor.require_phase0m_cleanup_safe(
                "SubmitDcb returned rc=0x00000000\n"
                "GPU completion verified target=0 fence=0\n"
                "AGC phase 0M exit result=0\n"
            )
            self.assertTrue(result["close_allowed"])


if __name__ == "__main__":
    unittest.main()
