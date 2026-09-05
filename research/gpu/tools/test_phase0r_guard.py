#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from phase0r_guard import START, State, classify


class Phase0RGuardTests(unittest.TestCase):
    def assert_state(self, log: str, state: State, close: bool) -> None:
        result = classify(log)
        self.assertEqual(result["state"], state.value)
        self.assertEqual(result["close_allowed"], close)

    def test_complete_allows_close(self) -> None:
        self.assert_state(
            START + "\nqueue pristine and BatchMap accepted state=3\n"
            "SubmitDcb returned rc=0x00000000\n"
            "GPU ownership complete fence=0 target=0\n"
            "phase0R exit result=0 submitted=yes-complete\n",
            State.GPU_COMPLETE, True,
        )

    def test_normal_pre_submit_failure_allows_close(self) -> None:
        self.assert_state(
            START + "\nphase0R exit result=11 submitted=no\n",
            State.PRE_SUBMIT_CLEAN, True,
        )

    def test_park_or_timeout_refuses_close(self) -> None:
        for suffix in (
            "PARKED_PHASE0R reason=fence timeout; retain driver, process and mapping; DO_NOT_CLOSE_FAKE00000\n",
            "watchdog before submit; exit=124 submitted=no\n",
        ):
            with self.subTest(suffix=suffix):
                self.assert_state(START + "\n" + suffix,
                                  State.PARKED if "PARKED" in suffix else State.UNKNOWN_RETAIN,
                                  False)

    def test_submit_return_without_completion_refuses_close(self) -> None:
        self.assert_state(
            START + "\nqueue pristine and BatchMap accepted state=3\n"
            "SubmitDcb returned rc=0x00000000\n",
            State.UNKNOWN_RETAIN, False,
        )

    def test_duplicate_or_contradictory_refuses_close(self) -> None:
        complete = (
            START + "\nqueue pristine and BatchMap accepted state=3\n"
            "SubmitDcb returned rc=0x00000000\n"
            "GPU ownership complete fence=0 target=0\n"
            "phase0R exit result=0 submitted=yes-complete\n"
        )
        self.assert_state(complete + complete, State.UNKNOWN_RETAIN, False)
        self.assert_state(complete.replace("0x00000000", "0x00000001"),
                          State.UNKNOWN_RETAIN, False)


class SupervisorPhase0RIntegrationTests(unittest.TestCase):
    @staticmethod
    def supervisor():
        import sys
        tools_dir = Path(__file__).resolve().parents[3] / "tools"
        sys.path.insert(0, str(tools_dir))
        from night_supervisor import SafetyStop, Supervisor
        directory = tempfile.TemporaryDirectory()
        return SafetyStop, Supervisor("127.0.0.1", Path(directory.name) / "j.jsonl"), directory

    def test_supervisor_refuses_parked(self) -> None:
        SafetyStop, supervisor, directory = self.supervisor()
        self.addCleanup(directory.cleanup)
        with self.assertRaises(SafetyStop):
            supervisor.require_phase0r_cleanup_safe(
                START + "\nPARKED_PHASE0R reason=fence timeout; DO_NOT_CLOSE_FAKE00000\n"
            )

    def test_supervisor_accepts_gpu_complete(self) -> None:
        _, supervisor, directory = self.supervisor()
        self.addCleanup(directory.cleanup)
        decision = supervisor.require_phase0r_cleanup_safe(
            START + "\nqueue pristine and BatchMap accepted state=3\n"
            "SubmitDcb returned rc=0x00000000\n"
            "GPU ownership complete fence=0 target=0\n"
            "phase0R exit result=0 submitted=yes-complete\n"
        )
        self.assertTrue(decision["completion_proven"])

    def test_execution_refuses_absent_operator_before_network(self) -> None:
        SafetyStop, supervisor, directory = self.supervisor()
        self.addCleanup(directory.cleanup)
        with self.assertRaisesRegex(SafetyStop, "explicitly present operator"):
            supervisor.run_phase0r_first_submit(False, "")

    def test_execution_refuses_wrong_hash_before_network(self) -> None:
        SafetyStop, supervisor, directory = self.supervisor()
        self.addCleanup(directory.cleanup)
        with self.assertRaisesRegex(SafetyStop, "confirmation hash mismatch"):
            supervisor.run_phase0r_first_submit(True, "not-the-audited-hash")

    def transaction_supervisor(self, runtime_log: str):
        import sys
        tools_dir = Path(__file__).resolve().parents[3] / "tools"
        sys.path.insert(0, str(tools_dir))
        import night_supervisor

        class FakeSupervisor(night_supervisor.Supervisor):
            def __init__(self):
                super().__init__("127.0.0.1", Path("/tmp/unused-phase0r-journal"))
                self.logs = iter(("stale log", runtime_log))
                self.closed = False
                self.events = []
            def record(self, event, **fields): self.events.append((event, fields))
            def require_stable_health(self, interval=5.0): pass
            def require_bigapp(self, expected): return {"app_id": -1, "title_id": ""}
            def ftp_read_text(self, remote): return next(self.logs)
            def upload_verified(self, local, remote): pass
            def shsrv_command(self, command, timeout=20.0): return ""
            def bigapp(self): return {"app_id": 7, "title_id": "FAKE00000"}
            def checked_close(self, title_id): self.closed = title_id == "FAKE00000"

        return night_supervisor, FakeSupervisor()

    def test_full_transaction_closes_only_after_completion(self) -> None:
        night_supervisor, supervisor = self.transaction_supervisor(
            START + "\nqueue pristine and BatchMap accepted state=3\n"
            "SubmitDcb returned rc=0x00000000\n"
            "GPU ownership complete fence=0 target=0\n"
            "phase0R exit result=0 submitted=yes-complete\n"
        )
        supervisor.run_phase0r_first_submit(True, night_supervisor.PHASE0R_SHA256)
        self.assertTrue(supervisor.closed)
        self.assertTrue(any(event == "phase0r_first_submit_verified"
                            for event, _ in supervisor.events))

    def test_full_transaction_does_not_close_parked_host(self) -> None:
        night_supervisor, supervisor = self.transaction_supervisor(
            START + "\nqueue pristine and BatchMap accepted state=3\n"
            "SubmitDcb returned rc=0x00000000\n"
            "PARKED_PHASE0R reason=fence timeout; DO_NOT_CLOSE_FAKE00000\n"
        )
        with self.assertRaises(night_supervisor.SafetyStop):
            supervisor.run_phase0r_first_submit(True, night_supervisor.PHASE0R_SHA256)
        self.assertFalse(supervisor.closed)


if __name__ == "__main__":
    unittest.main()
