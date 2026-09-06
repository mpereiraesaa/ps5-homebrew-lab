import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "night_supervisor", ROOT / "tools" / "night_supervisor.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeSupervisor(MODULE.Supervisor):
    def __init__(self, output, states):
        self.output = output
        self.states = iter(states)
        self.events = []

    def require_bigapp(self, expected):
        self.events.append(("precondition", expected))

    def run_elfldr(self, helper):
        self.events.append(("helper", helper.name))
        return self.output

    def bigapp(self):
        return next(self.states)

    def require_health(self):
        self.events.append(("health",))

    def record(self, event, **fields):
        self.events.append((event, fields))


class CloseVerificationTests(unittest.TestCase):
    def test_xash3d_uses_dedicated_exact_title_helper(self):
        helper_makefile = (ROOT / "tools/bigapp-control/Makefile").read_text()
        self.assertIn("launch-xash3d.elf", helper_makefile)
        self.assertIn("close-xash3d.elf", helper_makefile)
        self.assertIn("PPSA99996", helper_makefile)

        sup = FakeSupervisor(
            "bigapp-control action=close target=PPSA99996 "
            "app_id=57368 identify_rc=0 running=PPSA99996\n",
            [{"app_id": -1, "title_id": ""}],
        )
        sup.checked_close("PPSA99996")
        self.assertIn(("precondition", "PPSA99996"), sup.events)
        self.assertIn(("helper", "close-xash3d.elf"), sup.events)

    def test_native_close_requires_valid_network_manifest(self):
        class NativeSupervisor(FakeSupervisor):
            def __init__(self):
                super().__init__("", [])

            def checked_close(self, title_id):
                self.events.append(("close", title_id))

        refused = NativeSupervisor()
        with self.assertRaisesRegex(MODULE.SafetyStop, "network-evidence"):
            refused.checked_close_agc_native_sce()
        self.assertNotIn(("close", "PPSA99998"), refused.events)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = (
                b"HELLO ps5log/1 title=PPSA99998 app=agc-native-sce boot=0x42\n"
                b"1\t100\tINFO\tLOG_BOOT_MONOTONIC_NS=0x42\n"
                b"2\t101\tINFO\tSETFLIP_TRANSACTION_STARTED\n"
                b"3\t102\tINFO\tSTAGE_B_GPU_FENCE_ZERO\n"
                b"4\t103\tINFO\tSTAGE_B_VIDEOOUT_EVENT_ONE\n"
                b"5\t104\tINFO\tAGC stage B exit result=0\n"
                b"BYE seq=5 reason=cleanup-complete\n")
            log = root / "run.log"
            log.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            manifest = root / "run.json"
            manifest.write_text(json.dumps({
                "protocol": "ps5log/1", "transport": "tcp", "hello": True,
                "clean": True, "bye": True, "gaps": [],
                "oversized_lines": 0, "records": 5, "raw_lines": 0,
                "last_seq": 5, "bytes": len(data), "sha256": digest,
                "log_path": "run.log", "identity": {
                    "title": "PPSA99998", "app": "agc-native-sce",
                    "boot": "0x42"},
                "bye_fields": {"seq": "5", "reason": "cleanup-complete"},
            }))
            accepted = NativeSupervisor()
            accepted.checked_close_agc_native_sce("0x42", digest,
                                                  str(manifest))
            self.assertIn(("close", "PPSA99998"), accepted.events)

    def test_accepts_exact_title_with_external_closed_status(self):
        sup = FakeSupervisor(
            "bigapp-control action=close target=PPSA03524 "
            "app_id=57368 identify_rc=0 running=PPSA03524\n",
            [{"app_id": -1, "title_id": ""}],
        )
        sup.checked_close("PPSA03524")
        self.assertIn(
            ("close_verified", {
                "title_id": "PPSA03524", "verification": "external_status"
            }),
            sup.events,
        )

    def test_rejects_output_without_exact_running_title(self):
        sup = FakeSupervisor(
            "bigapp-control action=close target=PPSA03524 "
            "app_id=1 identify_rc=0 running=FAKE00000\n",
            [],
        )
        with self.assertRaisesRegex(MODULE.SafetyStop, "exact title"):
            sup.checked_close("PPSA03524")

    def test_rejects_different_bigapp_after_request(self):
        sup = FakeSupervisor(
            "bigapp-control action=close target=PPSA03524 "
            "app_id=57368 identify_rc=0 running=PPSA03524\n",
            [{"app_id": 9, "title_id": "FAKE00000"}],
        )
        with self.assertRaisesRegex(MODULE.SafetyStop, "unexpected BigApp"):
            sup.checked_close("PPSA03524")


if __name__ == "__main__":
    unittest.main()
