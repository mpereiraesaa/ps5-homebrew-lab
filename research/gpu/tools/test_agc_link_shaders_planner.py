#!/usr/bin/env python3
import unittest

from agc_link_shaders_planner import (CX_BYTES, UC_BYTES, LinkState, PlanError, Region,
                                      ShaderFacts, build_plan, mock_link, retire)


def shader(role="pre_raster", type_raw=2, base=0x3000, inputs=(), outputs=(0xF,)):
    return ShaderFacts(role, type_raw, base, 0x200, base + 0x80, 0x30,
                       base + 0xC0 if inputs else 0, tuple(inputs),
                       base + 0x100 if outputs else 0, tuple(outputs),
                       base + 0x120, 2, base + 0x140, 2,
                       ((base + 0x160, 1), (0, 0), (0, 0), (0, 0), (0, 0)), True)


class PlannerTests(unittest.TestCase):
    def good(self, **changes):
        args = dict(
            cx=Region(0x1000, CX_BYTES, True, True, "cx"),
            uc=Region(0x2000, UC_BYTES, True, True, "uc"),
            pre_region=Region(0x3000, 0x200, True, False, "pre"),
            pixel_region=Region(0x4000, 0x200, True, False, "pixel"),
            pre=shader(), pixel=shader("pixel", 1, 0x4000, (0xF,), ()),
            primitive_type=6, outputs_fresh=True, ownership_proven=True)
        args.update(changes)
        return build_plan(**args)

    def test_positive_pair(self): self.assertEqual(self.good()["matched_semantic_keys"], [15])
    def test_cx_short(self):
        with self.assertRaises(PlanError): self.good(cx=Region(0x1000, CX_BYTES-1, True, True, "cx"))
    def test_uc_short(self):
        with self.assertRaises(PlanError): self.good(uc=Region(0x2000, UC_BYTES-1, True, True, "uc"))
    def test_cx_misaligned(self):
        with self.assertRaises(PlanError): self.good(cx=Region(0x1001, CX_BYTES, True, True, "cx"))
    def test_output_readonly(self):
        with self.assertRaises(PlanError): self.good(cx=Region(0x1000, CX_BYTES, True, False, "cx"))
    def test_alias(self):
        with self.assertRaises(PlanError): self.good(uc=Region(0x1100, UC_BYTES, True, True, "uc"))
    def test_stale_output(self):
        with self.assertRaises(PlanError): self.good(outputs_fresh=False)
    def test_ownership(self):
        with self.assertRaises(PlanError): self.good(ownership_proven=False)
    def test_bad_primitive(self):
        with self.assertRaises(PlanError): self.good(primitive_type=0)
    def test_wrong_pre_stage(self):
        with self.assertRaises(PlanError): self.good(pre=shader(type_raw=1))
    def test_wrong_pixel_stage(self):
        with self.assertRaises(PlanError): self.good(pixel=shader("pixel", 2, 0x4000, (0xF,), ()))
    def test_semantic_mismatch(self):
        with self.assertRaises(PlanError): self.good(pixel=shader("pixel", 1, 0x4000, (0xE,), ()))
    def test_duplicate_semantic(self):
        with self.assertRaises(PlanError): self.good(pixel=shader("pixel", 1, 0x4000, (0xF, 0xF), ()))
    def test_semantic_capacity(self):
        with self.assertRaises(PlanError): self.good(pixel=shader("pixel", 1, 0x4000, tuple(range(33)), ()))
    def test_bad_nested_range(self):
        with self.assertRaises(PlanError): self.good(pre=ShaderFacts("pre_raster", 2, 0x3000, 0x200,
            0x5000, 0x30, 0, (), 0x3100, (0xF,)))
    def test_aux_presence_mismatch(self):
        with self.assertRaises(PlanError): self.good(aux_region=Region(0x5000, 0x200, True, False, "aux"))
    def test_mock_and_retire(self):
        linked = mock_link(planner_approved=True)
        self.assertEqual(retire(state=linked, downstream_references=0, gpu_quiescent=True),
                         "caller_may_release_outputs_then_shader_storage")
        self.assertEqual(mock_link(planner_approved=False).state, "rejected_before_call")
        with self.assertRaises(PlanError): retire(state=LinkState("linked_host_model", True, False),
                                                  downstream_references=1, gpu_quiescent=True)
    def test_inconsistent_nonzero_firmware_result(self):
        outcome = mock_link(planner_approved=True, firmware_return=1)
        self.assertEqual(outcome.state, "abi_or_firmware_drift_indeterminate")
        self.assertFalse(outcome.reusable)
        with self.assertRaises(PlanError):
            retire(state=outcome, downstream_references=0, gpu_quiescent=True)


if __name__ == "__main__":
    unittest.main()
