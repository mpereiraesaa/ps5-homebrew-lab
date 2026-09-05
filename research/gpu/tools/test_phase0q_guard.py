#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from phase0q_guard import State, classify


class Phase0QGuardTests(unittest.TestCase):
    START = "phase0Q start; type=0x0c BatchMap prot=0xcf2; no AGC, queue or submit\n"

    def assert_state(self, log: str, state: State, close: bool) -> None:
        result = classify(log)
        self.assertEqual(result["state"], state.value)
        self.assertEqual(result["close_allowed"], close)
        self.assertEqual(result["retain_process_and_mapping_state"], not close)

    def test_empty_refuses_close(self) -> None:
        self.assert_state("", State.NOT_STARTED, False)

    def test_success_with_canaries_is_clean(self) -> None:
        self.assert_state(
            self.START + "open rc=0 state=3 va=0x1000000000\n"
            "cpu_canaries=yes\nclose rc=0 state=0\n"
            "phase0Q exit result=0 submitted=no\n",
            State.MAP_ACCEPTED_CLEAN, True,
        )

    def test_canary_failure_after_clean_unmap_is_close_safe(self) -> None:
        result = classify(
            self.START + "open rc=0 state=3 va=0x1000000000\n"
            "cpu_canaries=no\nclose rc=0 state=0\n"
            "phase0Q exit result=20 submitted=no\n"
        )
        self.assertTrue(result["close_allowed"])
        self.assertFalse(result["cpu_canaries_passed"])

    def test_definite_rejection_and_cleanup_is_clean(self) -> None:
        self.assert_state(
            self.START + "open rc=-4 state=2 va=0x1000000000\n"
            "definite map failure cleanup rc=0 state=0\n"
            "phase0Q exit result=-4 submitted=no\n",
            State.MAP_REJECTED_CLEAN, True,
        )

    def test_park_overrides_stale_success(self) -> None:
        self.assert_state(
            self.START + "PARKED_PHASE0Q watchdog\nopen rc=0 state=3 va=0x1\n"
            "cpu_canaries=yes\nclose rc=0 state=0\n"
            "phase0Q exit result=0 submitted=no\n",
            State.PARKED, False,
        )

    def test_truncated_or_exit_only_refuses_close(self) -> None:
        for log in ("open rc=0 state=3 va=0x1\n", "phase0Q exit result=0 submitted=no\n"):
            with self.subTest(log=log):
                self.assert_state(log, State.UNKNOWN_RETAIN, False)

    def test_contradictory_canary_and_exit_refuses_close(self) -> None:
        self.assert_state(
            self.START + "open rc=0 state=3 va=0x1\n"
            "cpu_canaries=yes\nclose rc=0 state=0\n"
            "phase0Q exit result=20 submitted=no\n",
            State.UNKNOWN_RETAIN, False,
        )

    def test_duplicate_sequence_refuses_close(self) -> None:
        sequence = (
            self.START + "open rc=0 state=3 va=0x1\n"
            "cpu_canaries=yes\nclose rc=0 state=0\n"
            "phase0Q exit result=0 submitted=no\n"
        )
        self.assert_state(sequence + sequence, State.UNKNOWN_RETAIN, False)


class SupervisorPhase0QIntegrationTests(unittest.TestCase):
    @staticmethod
    def supervisor_types():
        import sys
        tools_dir = Path(__file__).resolve().parents[3] / "tools"
        sys.path.insert(0, str(tools_dir))
        from night_supervisor import SafetyStop, Supervisor
        return SafetyStop, Supervisor

    def test_supervisor_refuses_ambiguous_cleanup(self) -> None:
        SafetyStop, Supervisor = self.supervisor_types()
        with tempfile.TemporaryDirectory() as directory:
            supervisor = Supervisor("127.0.0.1", Path(directory) / "journal.jsonl")
            with self.assertRaises(SafetyStop):
                supervisor.require_phase0q_cleanup_safe("PARKED_PHASE0Q watchdog\n")

    def test_supervisor_accepts_clean_rejection(self) -> None:
        _, Supervisor = self.supervisor_types()
        with tempfile.TemporaryDirectory() as directory:
            supervisor = Supervisor("127.0.0.1", Path(directory) / "journal.jsonl")
            decision = supervisor.require_phase0q_cleanup_safe(
                Phase0QGuardTests.START + "open rc=-4 state=2 va=0x1\n"
                "definite map failure cleanup rc=0 state=0\n"
                "phase0Q exit result=-4 submitted=no\n"
            )
            self.assertTrue(decision["close_allowed"])


if __name__ == "__main__":
    unittest.main()
