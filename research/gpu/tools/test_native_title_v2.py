import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "night_supervisor_v2_test", ROOT / "tools/night_supervisor.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class NativeTitleV2Tests(unittest.TestCase):
    def test_metadata_and_artifact_identity_are_exact(self):
        app = ROOT / "legacy/apps/agc-phase0-native"
        for name in ("param.json", "param.json.system"):
            metadata = json.loads(
                (app / "AGCP12003/sce_sys" / name).read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["titleId"], "AGCP12003")
        self.assertTrue((app / "AGCP12003/eboot.bin").read_bytes().startswith(
            bytes.fromhex("4f153d1d")
        ))
        installer = (app / "installer-agcp12003.elf").read_bytes()
        self.assertIn(b"AGCP12003", installer)
        self.assertNotIn(b"AGCP12002", installer)

    def test_exact_launch_and_close_helpers_exist(self):
        helpers = ROOT / "tools/bigapp-control"
        launch = (helpers / "launch-agc-phase0-v2.elf").read_bytes()
        close = (helpers / "close-agc-phase0-v2.elf").read_bytes()
        for blob in (launch, close):
            self.assertIn(b"AGCP12003", blob)
            self.assertNotIn(b"AGCP12002", blob)

    def test_collision_stops_before_any_write(self):
        class CollisionSupervisor(MODULE.Supervisor):
            def __init__(self):
                self.checked = []

            def require_stable_health(self, interval=5.0):
                self.checked.append("health")

            def require_bigapp(self, expected):
                self.checked.append(("bigapp", expected))

            def ftp_directory_exists(self, path):
                self.checked.append(("collision", path))
                return path.endswith("AGCP12003")

            def record(self, event, **fields):
                self.checked.append((event, fields))

        supervisor = CollisionSupervisor()
        with self.assertRaisesRegex(MODULE.SafetyStop, "no overwrite attempted"):
            supervisor.install_agc_phase0_v2()
        self.assertNotIn("MTRW", supervisor.checked)

    def test_crashing_static_title_is_refused_before_network(self):
        supervisor = MODULE.Supervisor("unreachable.invalid", Path("/tmp/unused"))
        with self.assertRaisesRegex(MODULE.SafetyStop, "CE-108262-9"):
            supervisor.checked_launch("AGCP12003")


if __name__ == "__main__":
    unittest.main()
