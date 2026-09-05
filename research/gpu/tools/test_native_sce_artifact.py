import json
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "legacy/apps/agc-native-sce"


class NativeSceArtifactTests(unittest.TestCase):
    def test_probe_parks_and_exact_close_helper_is_bound(self):
        source = (ROOT / "legacy/apps/agc-native-sce/direct_main.cpp").read_text(encoding="utf-8")
        self.assertIn("cleanup complete; parked-safe; close exact title PPSA99998", source)
        self.assertIn("sceKernelAllocateDirectMemory", source)
        self.assertIn("sceAgcCreateShader", source)
        self.assertIn("sceAgcLinkShaders", source)
        self.assertIn("sceKernelMunmap", source)
        self.assertIn("sceKernelReleaseDirectMemory", source)
        helper = (ROOT / "tools/bigapp-control/close-agc-native-sce.elf").read_bytes()
        self.assertIn(b"PPSA99998", helper)

    def test_local_gate_and_proof(self):
        subprocess.run(["python3", "verify.py"], cwd=APP, check=True,
                       stdout=subprocess.DEVNULL)
        proof = json.loads((
            ROOT / "research/gpu/captures/agc-native-sce-phase0-local-proof.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(proof["elf"]["type"], "0xfe10")
        self.assertEqual(proof["elf"]["program_header_count"], 14)
        self.assertEqual(proof["elf"]["process_parameter_magic"], "ORBI")
        self.assertEqual(proof["metadata"]["application_drm_type"], "free")
        self.assertTrue(proof["scope"]["cpu_create_and_link_only"])
        self.assertEqual(proof["scope"]["direct_memory_arena"]["bytes"], 0x10000)
        self.assertFalse(proof["scope"]["queue_or_submit_present"])
        self.assertFalse(proof["launchability_on_fw_12_02_proven"])

    def test_deployment_plan_is_hidden_then_atomic(self):
        spec = importlib.util.spec_from_file_location(
            "native_sce_deploy_test", APP / "deploy.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        plan = module.plan()
        self.assertEqual(plan["final"], "/data/homebrew/PPSA99998")
        self.assertTrue(plan["staging"].startswith(
            "/data/homebrew/.PPSA99998.staging-"
        ))
        self.assertIn("/system_ex/app/PPSA99998", plan["collision_paths"])
        self.assertIn("/user/app/PPSA99998", plan["collision_paths"])
        relatives = {item["relative"] for item in plan["files"]}
        self.assertEqual(relatives, {
            "eboot.bin", "sce_module/libc.prx", "sce_sys/icon0.png",
            "sce_sys/param.json",
        })


if __name__ == "__main__":
    unittest.main()
