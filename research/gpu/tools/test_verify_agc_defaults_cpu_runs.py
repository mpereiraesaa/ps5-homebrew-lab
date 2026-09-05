import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "verify_agc_defaults_cpu_runs", HERE / "verify_agc_defaults_cpu_runs.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
CAPTURE = json.loads((HERE.parent / "captures/agc-defaults-cpu-run1.json").read_text())
CAPTURE["termination_model"] = "count-delimited; no sentinel"


class CpuRunVerifierTests(unittest.TestCase):
    def test_accepts_independent_equal_runs(self):
        second = copy.deepcopy(CAPTURE)
        second["pid_ephemeral"] += 1
        MODULE.verify_pair(CAPTURE, second)

    def test_rejects_same_pid(self):
        with self.assertRaisesRegex(MODULE.VerificationError, "independent"):
            MODULE.verify_pair(CAPTURE, copy.deepcopy(CAPTURE))

    def test_rejects_mutated_hash_index_pointer_and_terminator(self):
        mutations = (
            ("hash", lambda c: c.__setitem__("type_table_sha256", "z" * 64)),
            ("index", lambda c: c["banks"][0].__setitem__("index_max", 82)),
            ("pointer", lambda c: c["banks"][1].__setitem__("target_min", "0x0")),
            ("terminator", lambda c: c.__setitem__("termination_model", "sentinel")),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                bad = copy.deepcopy(CAPTURE)
                mutate(bad)
                with self.assertRaises(MODULE.VerificationError):
                    MODULE.validate_capture(bad)

    def test_rejects_changed_safety_envelope(self):
        bad = copy.deepcopy(CAPTURE)
        bad["safety"]["writes"] = 1
        with self.assertRaisesRegex(MODULE.VerificationError, "safety"):
            MODULE.validate_capture(bad)


if __name__ == "__main__":
    unittest.main()
