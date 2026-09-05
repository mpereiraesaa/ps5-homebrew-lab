import importlib.util
import sys
import unittest
from dataclasses import replace
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "agc_create_shader_planner", HERE / "agc_create_shader_planner.py"
)
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.dst = M.Region(0x1000, 8, True, True, "destination")
        self.header = M.Region(0x2000, 0x400, True, True, "header")
        self.code = M.Region(0x4000, 0x200, True, False, "code")
        self.facts = M.HeaderFacts(
            M.MAGIC, M.VERSION, 0x400, 0x100, 10, 0, 0,
            {0x08: 0x78, 0x18: 0xa0, 0x20: 0xb0,
             0x28: 0, 0x30: 0xd0, 0x38: 0xe0},
            2, 2, 1, 1,
        )
        self.user = M.UserDataFacts(
            {0: 0x38, 8: 0x38, 16: 0x38, 24: 0x38, 32: 0x38},
            1, (0, 0, 0, 0),
        )
        self.pre = M.Preconditions(True, True, True, 0x20c, 0, 0x840f80)

    def test_accepts_fully_bounded_synthetic_plan(self):
        plan = M.build_plan(self.dst, self.header, self.code, self.facts, self.pre, self.user)
        self.assertTrue(plan["approved"])
        self.assertFalse(plan["console_execution_authorized"])

    def test_rejects_bad_magic_version_stage_or_bound_code(self):
        for changes in ({"magic": 0}, {"version": 0}, {"stage": 8}, {"code_field": 1}):
            with self.subTest(changes=changes):
                with self.assertRaises(M.PlanError):
                    M.build_plan(self.dst, self.header, self.code,
                                 replace(self.facts, **changes), self.pre, self.user)

    def test_rejects_alignment_sizes_and_permissions(self):
        cases = (
            (self.dst, self.header, M.Region(0x4001, 0x200, True, False, "code"), self.facts),
            (self.dst, self.header, self.code, replace(self.facts, shader_size=0x20)),
            (self.dst, self.header, self.code, replace(self.facts, shader_size=0x300)),
            (self.dst, M.Region(0x2000, 0x400, True, False, "header"), self.code, self.facts),
        )
        for dst, header, code, facts in cases:
            with self.assertRaises(M.PlanError):
                M.build_plan(dst, header, code, facts, self.pre, self.user)

    def test_rejects_relative_pointer_and_array_escape(self):
        for field, raw in ((0x20, 0x100000000), (0x20, 0x500)):
            pointers = dict(self.facts.relative_pointers)
            pointers[field] = raw
            with self.subTest(raw=raw):
                with self.assertRaises(M.PlanError):
                    M.build_plan(self.dst, self.header, self.code,
                                 replace(self.facts, relative_pointers=pointers), self.pre, self.user)
        with self.assertRaises(M.PlanError):
            M.build_plan(self.dst, self.header, self.code,
                         replace(self.facts, num_sh_registers=255,
                                 relative_pointers={**self.facts.relative_pointers,
                                                    0x20: 0x300}), self.pre, self.user)

    def test_rejects_unproven_dynamic_preconditions(self):
        for field in ("footer_marker_valid", "stage_register_match_proven"):
            with self.subTest(field=field):
                with self.assertRaises(M.PlanError):
                    M.build_plan(self.dst, self.header, self.code, self.facts,
                                 replace(self.pre, **{field: False}), self.user)

    def test_target_policy_matches_all_special_branches(self):
        for target, flag in ((10, 1), (12, 0), (13, 1), (15, 0)):
            with self.subTest(target=target, flag=flag):
                with self.assertRaises(M.PlanError):
                    M.validate_target_policy(target, flag, 0x840f80, False)
        for target, flag in ((10, 0), (11, 0), (12, 1), (13, 0), (14, 0), (15, 1)):
            M.validate_target_policy(target, flag, 0x840f80, False)
        with self.assertRaisesRegex(M.PlanError, "SDK policy"):
            M.validate_target_policy(14, 0, 0x840fc7, False)
        with self.assertRaisesRegex(M.PlanError, "helper"):
            M.validate_target_policy(0x8000000a, 0, 0x840f80, False)

    def test_rejects_runtime_mode_sentinel(self):
        with self.assertRaisesRegex(M.PlanError, "runtime"):
            M.build_plan(self.dst, self.header, self.code, self.facts,
                         replace(self.pre, runtime_mode_word=0x10000000), self.user)

    def test_validates_nested_user_data_bounds(self):
        bad = replace(self.user, direct_resource_count=0x400)
        with self.assertRaisesRegex(M.PlanError, "nested"):
            M.build_plan(self.dst, self.header, self.code, self.facts, self.pre, bad)
        missing = replace(self.user, relative_pointers={**self.user.relative_pointers, 0: 0})
        with self.assertRaisesRegex(M.PlanError, "absent"):
            M.build_plan(self.dst, self.header, self.code, self.facts, self.pre, missing)

    def test_rejects_missing_user_data_structure_even_with_zero_resources(self):
        pointers = dict(self.facts.relative_pointers)
        pointers[0x08] = 0
        with self.assertRaisesRegex(M.PlanError, "mandatory"):
            M.build_plan(self.dst, self.header, self.code,
                         replace(self.facts, relative_pointers=pointers),
                         self.pre, None)

    def test_retirement_requires_no_references_and_quiescence(self):
        self.assertEqual(M.retire(constructed=True, downstream_references=0,
                                  gpu_quiescent=True),
                         "caller_may_release_header_and_code")
        for args in ((False, 0, True), (True, 1, True), (True, 0, False)):
            with self.assertRaises(M.PlanError):
                M.retire(constructed=args[0], downstream_references=args[1],
                         gpu_quiescent=args[2])

    def test_constructor_result_state_machine(self):
        self.assertEqual(M.classify_constructor_result(0), "constructed_alias")
        for error in M.PREMUTATION_ERRORS:
            self.assertEqual(M.classify_constructor_result(error),
                             "rejected_before_mutation")
        self.assertEqual(M.classify_constructor_result(0x8A6C0005),
                         "consumed_partial_mutation_discard_copy")
        self.assertEqual(M.classify_constructor_result(0xDEADBEEF),
                         "indeterminate_retain_do_not_retry")
        success = M.mock_constructor(0)
        self.assertTrue(success.destination_published and success.header_mutated)
        early = M.mock_constructor(0x8A6C0003)
        self.assertTrue(early.caller_may_retry_same_copy)
        self.assertFalse(early.destination_published or early.header_mutated)
        partial = M.mock_constructor(0x8A6C0005)
        self.assertTrue(partial.header_mutated)
        self.assertFalse(partial.destination_published or partial.caller_may_retry_same_copy)


if __name__ == "__main__":
    unittest.main()
