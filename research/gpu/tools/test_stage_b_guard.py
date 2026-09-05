#!/usr/bin/env python3
import unittest
import tempfile
from pathlib import Path

from stage_b_guard import PARK_MARKERS, State, classify


class StageBGuardTests(unittest.TestCase):
    def assert_state(self, log: str, state: State, cleanup: bool) -> None:
        result = classify(log)
        self.assertEqual(result["state"], state.value)
        self.assertEqual(result["cleanup_allowed"], cleanup)
        self.assertEqual(result["retain_all_resources"], not cleanup)
        if not cleanup:
            for action in ("close_ppsa99998", "unregister_video_buffers",
                           "close_videoout", "unmap_command_memory",
                           "unmap_video_memory", "unload_agc_driver"):
                self.assertIn(action, result["automated_actions_forbidden"])

    def test_empty_retains(self):
        self.assert_state("", State.NOT_STARTED, False)

    def test_pre_transaction_exit_allows_cleanup(self):
        self.assert_state("STAGE_B_PRE_TRANSACTION_CLEANUP_COMPLETE\n"
                          "AGC stage B exit result=0x00000018\n",
                          State.PRE_TRANSACTION_EXIT, True)

    def test_pre_transaction_exit_without_cleanup_retains(self):
        self.assert_state("AGC stage B exit result=0x00000018\n",
                          State.UNKNOWN_RETAIN, False)

    def test_complete_transaction_allows_cleanup(self):
        self.assert_state(
            "SETFLIP_TRANSACTION_STARTED\n"
            "STAGE_B_GPU_FENCE_ZERO\n"
            "STAGE_B_VIDEOOUT_EVENT_ONE\n"
            "AGC stage B exit result=0\n",
            State.PRESENT_COMPLETE, True)

    def test_complete_stage_e_allows_cleanup(self):
        self.assert_state(
            "AGC native Stage E v1\n"
            "STAGE_E_PREFLIGHT_COMPLETE\n"
            "STAGE_E_TRANSACTION_STARTED one_submit=true\n"
            "stage_e_submit=0x00000000\n"
            "STAGE_B_GPU_FENCE_ZERO\n"
            "STAGE_E_GUARDS_INTACT\n"
            "STAGE_E_RECOVERY_BUFFER_UNTOUCHED\n"
            "STAGE_B_VIDEOOUT_EVENT_ONE\n"
            "STAGE_E_VISIBLE_HOLD_COMPLETE\n"
            "STAGE_E_SHADER_ARENA_SCRUBBED\n"
            "AGC stage B exit result=0\n"
            "STAGE_E_COMPLETE cleanup complete\n",
            State.PRESENT_COMPLETE, True)

    def test_stage_e_missing_scrub_retains(self):
        self.assert_state(
            "AGC native Stage E v1\n"
            "STAGE_E_PREFLIGHT_COMPLETE\n"
            "STAGE_E_TRANSACTION_STARTED one_submit=true\n"
            "stage_e_submit=0x00000000\n"
            "STAGE_B_GPU_FENCE_ZERO\n"
            "STAGE_E_GUARDS_INTACT\n"
            "STAGE_E_RECOVERY_BUFFER_UNTOUCHED\n"
            "STAGE_B_VIDEOOUT_EVENT_ONE\n"
            "STAGE_E_VISIBLE_HOLD_COMPLETE\n"
            "AGC stage B exit result=0\n"
            "STAGE_E_COMPLETE cleanup complete\n",
            State.UNKNOWN_RETAIN, False)

    def test_stage_g_uses_extended_completion_contract(self):
        self.assert_state(
            "AGC native Stage G v1\n"
            "STAGE_E_PREFLIGHT_COMPLETE\n"
            "STAGE_E_TRANSACTION_STARTED one_submit=true\n"
            "stage_e_submit=0x00000000\n"
            "STAGE_B_GPU_FENCE_ZERO\n"
            "STAGE_E_GUARDS_INTACT\n"
            "STAGE_E_RECOVERY_BUFFER_UNTOUCHED\n"
            "STAGE_B_VIDEOOUT_EVENT_ONE\n"
            "STAGE_E_VISIBLE_HOLD_COMPLETE\n"
            "STAGE_E_SHADER_ARENA_SCRUBBED\n"
            "AGC stage B exit result=0\n"
            "STAGE_E_COMPLETE cleanup complete\n",
            State.PRESENT_COMPLETE, True)

    def test_stage_g22_uses_extended_completion_contract(self):
        log = (
            "AGC native Stage G/22 v1; gfx1013 cube + D32 LESS_EQUAL depth test\n"
            "stage_g_depth_register_count=0x00000016\n"
            "STAGE_E_PREFLIGHT_COMPLETE\n"
            "STAGE_E_TRANSACTION_STARTED one_submit=true\n"
            "stage_e_submit=0x00000000\n"
            "STAGE_B_GPU_FENCE_ZERO\n"
            "STAGE_E_GUARDS_INTACT\n"
            "STAGE_E_RECOVERY_BUFFER_UNTOUCHED\n"
            "STAGE_B_VIDEOOUT_EVENT_ONE\n"
            "STAGE_E_VISIBLE_HOLD_COMPLETE\n"
            "STAGE_E_SHADER_ARENA_SCRUBBED\n"
            "AGC stage B exit result=0\n"
            "STAGE_E_COMPLETE cleanup complete\n")
        result = classify(log)
        self.assertTrue(result["stage_e"])
        self.assert_state(log, State.PRESENT_COMPLETE, True)

    def test_stage_g23_banners_use_extended_completion_contract(self):
        for banner in ("AGC native Stage G/23 OFF v1",
                       "AGC native Stage G/23 ON v1"):
            with self.subTest(banner=banner):
                log = (
                    banner + "\nSTAGE_E_PREFLIGHT_COMPLETE\n"
                    "STAGE_E_TRANSACTION_STARTED one_submit=true\n"
                    "stage_e_submit=0x00000000\nSTAGE_B_GPU_FENCE_ZERO\n"
                    "STAGE_E_GUARDS_INTACT\n"
                    "STAGE_E_RECOVERY_BUFFER_UNTOUCHED\n"
                    "STAGE_B_VIDEOOUT_EVENT_ONE\n"
                    "STAGE_E_VISIBLE_HOLD_COMPLETE\n"
                    "STAGE_E_SHADER_ARENA_SCRUBBED\n"
                    "AGC stage B exit result=0\n"
                    "STAGE_E_COMPLETE cleanup complete\n")
                self.assert_state(log, State.PRESENT_COMPLETE, True)

    def test_stage_g_submit_without_fence_retains(self):
        self.assert_state(
            "AGC native Stage G v1\n"
            "STAGE_E_TRANSACTION_STARTED one_submit=true\n"
            "stage_e_submit=0x00000000\n",
            State.UNKNOWN_RETAIN, False)

    def test_stage_h_uses_extended_completion_contract(self):
        self.assert_state(
            "AGC native Stage H v1\n"
            "STAGE_E_PREFLIGHT_COMPLETE\n"
            "STAGE_E_TRANSACTION_STARTED one_submit=true\n"
            "stage_e_submit=0x00000000\n"
            "STAGE_B_GPU_FENCE_ZERO\n"
            "STAGE_E_GUARDS_INTACT\n"
            "STAGE_E_RECOVERY_BUFFER_UNTOUCHED\n"
            "STAGE_B_VIDEOOUT_EVENT_ONE\n"
            "STAGE_E_VISIBLE_HOLD_COMPLETE\n"
            "STAGE_E_SHADER_ARENA_SCRUBBED\n"
            "AGC stage B exit result=0\n"
            "STAGE_E_COMPLETE cleanup complete\n",
            State.PRESENT_COMPLETE, True)

    def stage_i_complete_log(self) -> str:
        return (
            "AGC native Stage I v1\n"
            "STAGE_E_PREFLIGHT_COMPLETE\n"
            "STAGE_I_DOUBLE_PIPELINE_READY\n"
            "STAGE_I_RT_CLEAR_READY method=fullscreen_triangle vertices=3 color_dma=false\n"
            "STAGE_I_LOOP_BEGIN buffers=2 depth_registers=22\n"
            "stage_i_frames_requested=0x000000000000012c\n"
            "STAGE_I_TELEMETRY_BEGIN\n"
            "stage_i_frames_completed=0x000000000000012c\n"
            "STAGE_I_TELEMETRY_END\n"
            "stage_i_max_frames_in_flight=0x00000002\n"
            "stage_i_loop_elapsed_ns=0x0000000129fd1641\n"
            "stage_i_frame_interval_ns_average=0x0000000000fe489b\n"
            "STAGE_I_GPU_FENCE_ZERO\n"
            "STAGE_I_VIDEOOUT_EVENT_EXACT\n"
            "STAGE_I_GUARDS_INTACT color=true depth=true\n"
            "STAGE_I_LOOP_COMPLETE\n"
            "stage_i_frames_verified=0x000000000000012c\n"
            "STAGE_I_VISIBLE_HOLD_COMPLETE\n"
            "STAGE_E_SHADER_ARENA_SCRUBBED\n"
            "AGC stage B exit result=0\n"
            "STAGE_E_COMPLETE cleanup complete\n")

    def test_stage_i_complete_allows_cleanup(self):
        result = classify(self.stage_i_complete_log())
        self.assertTrue(result["stage_i"])
        self.assert_state(self.stage_i_complete_log(),
                          State.PRESENT_COMPLETE, True)

    def test_stage_i_missing_terminal_telemetry_retains(self):
        log = self.stage_i_complete_log().replace(
            "stage_i_frames_completed=0x000000000000012c\n", "")
        self.assert_state(log, State.UNKNOWN_RETAIN, False)

    def test_stage_i_missing_two_frames_in_flight_proof_retains(self):
        log = self.stage_i_complete_log().replace(
            "stage_i_max_frames_in_flight=0x00000002\n", "")
        self.assert_state(log, State.UNKNOWN_RETAIN, False)

    def test_stage_i_dma_color_clear_retains(self):
        log = self.stage_i_complete_log().replace(
            "STAGE_I_RT_CLEAR_READY method=fullscreen_triangle vertices=3 color_dma=false\n",
            "")
        self.assert_state(log, State.UNKNOWN_RETAIN, False)

    def test_stage_i_mismatched_soak_count_retains(self):
        log = self.stage_i_complete_log().replace(
            "stage_i_frames_verified=0x000000000000012c",
            "stage_i_frames_verified=0x00000000000003e8")
        self.assert_state(log, State.UNKNOWN_RETAIN, False)

    def test_stage_i_reordered_terminal_markers_retain(self):
        log = self.stage_i_complete_log().replace(
            "STAGE_I_GPU_FENCE_ZERO\nSTAGE_I_VIDEOOUT_EVENT_EXACT\n",
            "STAGE_I_VIDEOOUT_EVENT_EXACT\nSTAGE_I_GPU_FENCE_ZERO\n")
        self.assert_state(log, State.UNKNOWN_RETAIN, False)

    def test_each_park_marker_retains(self):
        for marker in PARK_MARKERS:
            with self.subTest(marker=marker):
                self.assert_state(marker + "\n", State.PARKED, False)

    def test_transaction_start_only_retains(self):
        self.assert_state("SETFLIP_TRANSACTION_STARTED\n",
                          State.UNKNOWN_RETAIN, False)

    def test_fence_without_videoout_retains(self):
        self.assert_state("SETFLIP_TRANSACTION_STARTED\nSTAGE_B_GPU_FENCE_ZERO\n",
                          State.UNKNOWN_RETAIN, False)

    def test_videoout_without_fence_retains(self):
        self.assert_state("SETFLIP_TRANSACTION_STARTED\nSTAGE_B_VIDEOOUT_EVENT_ONE\n",
                          State.UNKNOWN_RETAIN, False)

    def test_normal_exit_missing_one_completion_retains(self):
        self.assert_state(
            "SETFLIP_TRANSACTION_STARTED\nSTAGE_B_GPU_FENCE_ZERO\n"
            "AGC stage B exit result=0\n",
            State.UNKNOWN_RETAIN, False)

    def test_out_of_order_completion_retains(self):
        self.assert_state(
            "SETFLIP_TRANSACTION_STARTED\n"
            "STAGE_B_VIDEOOUT_EVENT_ONE\n"
            "STAGE_B_GPU_FENCE_ZERO\n"
            "AGC stage B exit result=0\n",
            State.UNKNOWN_RETAIN, False)

    def test_park_overrides_complete_sequence(self):
        self.assert_state(
            "SETFLIP_TRANSACTION_STARTED\nSTAGE_B_GPU_FENCE_ZERO\n"
            "STAGE_B_VIDEOOUT_EVENT_ONE\nAGC stage B exit result=0\n"
            "PARKED_STAGE_B_VIDEOOUT_TIMEOUT\n",
            State.PARKED, False)


class SupervisorStageBIntegrationTests(unittest.TestCase):
    @staticmethod
    def supervisor_types():
        import sys
        tools_dir = Path(__file__).resolve().parents[3] / "tools"
        sys.path.insert(0, str(tools_dir))
        from night_supervisor import SafetyStop, Supervisor
        return SafetyStop, Supervisor

    def test_supervisor_refuses_partial_presentation_cleanup(self):
        SafetyStop, Supervisor = self.supervisor_types()
        with tempfile.TemporaryDirectory() as directory:
            supervisor = Supervisor("127.0.0.1", Path(directory) / "journal.jsonl")
            with self.assertRaises(SafetyStop):
                supervisor.require_stage_b_cleanup_safe(
                    "SETFLIP_TRANSACTION_STARTED\nSTAGE_B_GPU_FENCE_ZERO\n"
                )

    def test_supervisor_accepts_both_completions_and_exit(self):
        _, Supervisor = self.supervisor_types()
        with tempfile.TemporaryDirectory() as directory:
            supervisor = Supervisor("127.0.0.1", Path(directory) / "journal.jsonl")
            decision = supervisor.require_stage_b_cleanup_safe(
                "SETFLIP_TRANSACTION_STARTED\n"
                "STAGE_B_GPU_FENCE_ZERO\n"
                "STAGE_B_VIDEOOUT_EVENT_ONE\n"
                "AGC stage B exit result=0\n"
            )
            self.assertTrue(decision["cleanup_allowed"])


if __name__ == "__main__":
    unittest.main()
