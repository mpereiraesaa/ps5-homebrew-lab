#!/usr/bin/env python3
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "agc_net_monitor", ROOT / "tools/agc_net_monitor.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ObservabilityTests(unittest.TestCase):
    def test_network_only_contract_cannot_silently_regress(self):
        app = (ROOT / "legacy/apps/agc-native-sce/stage_b_main.cpp").read_text()
        build = (ROOT / "legacy/apps/agc-native-sce/build_stage_f.sh").read_text()
        helper = (ROOT / "tools/bigapp-control/main.c").read_text()
        monitor = (ROOT / "tools/agc_net_monitor.py").read_text()
        supervisor = (ROOT / "tools/night_supervisor.py").read_text()
        operations = (ROOT / "docs/OPERATIONS.md").read_text()
        deploy = (ROOT / "legacy/apps/agc-native-sce/deploy.py").read_text()
        self.assertIn('ps5log_init(&log_config', app)
        self.assertIn('LOG_TRANSPORT=ps5log/1 tcp structured', app)
        self.assertIn('LOG_FS_SINKS=disabled', app)
        self.assertIn('LOG_BOOT_MONOTONIC_NS=', app)
        self.assertIn('PS5LOG_NATIVE_TRANSPORT_SMOKE_COMPLETE', app)
        for forbidden in ('/usb0', '/mnt/usb0', '/download0', 'fsync('):
            self.assertNotIn(forbidden, app)
        self.assertIn('ps5log.o', build)
        self.assertIn('ps5log_ps5_net.o', build)
        self.assertIn('-include "$ps5log/ps5log_ps5_net.h"', build)
        self.assertIn('cp "$dev_conf" "$dist/dev.conf"', build)
        self.assertNotIn('nmount(', helper)
        self.assertNotIn('attach_usb_log_mount', helper)
        self.assertIn('deployment requires packaged /app0/dev.conf', deploy)
        self.assertIn('config_sha256', deploy)
        self.assertIn('BACKUP_NAME.fullmatch', deploy)
        self.assertIn('"backup_retained": False', deploy)
        adapter = (ROOT / 'projects/logging_server/client/ps5log_ps5_net.c').read_text()
        for native_call in ('sceNetSocket(', 'sceNetConnect(', 'sceNetSend(',
                            'sceNetSocketClose(', 'sceNetEpollWait('):
            self.assertIn(native_call, adapter)
        self.assertNotIn('ftplib', monitor)
        self.assertIn('validate_manifest', monitor)
        self.assertIn("int(match.group(1), 16) >= 0x80000000", monitor)
        self.assertIn('agc_net_monitor.py', operations)
        self.assertIn('--expected-ps5log-manifest', supervisor)
        self.assertNotIn('/mnt/usb0/PS5/agc-gears/agc-gears.log', supervisor)
        self.assertNotIn('usb sandbox mount verified=true', supervisor)
        for retired in ('"run-agc-cpu-link"', '"run-native-label-submit"',
                        '"run-stage-b"', '"run-stage-e"',
                        '"run-stage-c-256"'):
            self.assertNotIn(retired, supervisor[supervisor.index('def main()'):])
        for script in ('build.sh', 'build_submit.sh', 'build_stage_b.sh',
                       'build_stage_c.sh', 'build_stage_d.sh',
                       'build_stage_e.sh', 'build_stage_e_cpu.sh'):
            source = (ROOT / 'legacy/apps/agc-native-sce' / script).read_text()
            self.assertIn('deprecated:', '\n'.join(source.splitlines()[:5]))

    def test_only_app0_configuration_is_used_by_agc_runtime(self):
        app = (ROOT / "legacy/apps/agc-native-sce/stage_b_main.cpp").read_text()
        self.assertIn('const char *const log_paths[] = {"/app0/dev.conf"}', app)

    def test_clean_completion_exits_but_ambiguous_state_parks(self):
        app = (ROOT / "legacy/apps/agc-native-sce/stage_b_main.cpp").read_text()
        completion = app[app.index('result = cleanup_resources();',
                                   app.index('int main()')):]
        self.assertIn('STAGE_E_COMPLETE cleanup complete; immediate process exit follows',
                      completion)
        self.assertIn('ps5log_close("cleanup-complete")', completion)
        self.assertIn('_exit(0);', completion)
        self.assertIn('[[noreturn]] void park(const char *reason)', app)
        self.assertIn('for (;;) (void)pause();', app[app.index(
            '[[noreturn]] void park(const char *reason)'):])

    def test_g21_and_g22_differ_only_by_depth_enable_switch(self):
        g21 = (ROOT / "legacy/apps/agc-native-sce/stage_g_main.cpp").read_text()
        g22 = (ROOT / "legacy/apps/agc-native-sce/stage_g22_main.cpp").read_text()
        self.assertNotIn("STAGE_G_DEPTH_ENABLE_TEST", g21)
        self.assertIn("#define STAGE_G_DEPTH_ENABLE_TEST 1", g22)
        normalized = g22.replace("#define STAGE_G_DEPTH_ENABLE_TEST 1\n", "")
        self.assertEqual(g21, normalized)

    def test_g23_pair_differs_only_by_depth_enable_switch(self):
        apps = ROOT / "legacy" / "apps" / "agc-native-sce"
        off = (apps / "stage_g23off_main.cpp").read_text()
        on = (apps / "stage_g23on_main.cpp").read_text()
        self.assertNotIn("STAGE_G_DEPTH_ENABLE_TEST", off)
        normalized = on.replace("#define STAGE_G_DEPTH_ENABLE_TEST 1\n", "")
        self.assertEqual(off, normalized)

    def test_stage_h_consumes_validated_depth_state(self):
        stage_h = (ROOT / "legacy/apps/agc-native-sce/stage_h_main.cpp").read_text()
        self.assertIn("#define STAGE_H_GEARS 1", stage_h)
        self.assertIn("#define STAGE_G_DEPTH_ENABLE_TEST 1", stage_h)
        self.assertIn("#define STAGE_G_DEPTH 1", stage_h)
        runtime = (ROOT / "legacy/apps/agc-native-sce/stage_b_main.cpp").read_text()
        self.assertIn('#include "stage_metadata_contract.h"', runtime)
        self.assertIn('(table_address >> 32) != UINT64_C(2)', runtime)

    def test_variant_metadata_mismatch_is_compile_error(self):
        header = ROOT / "legacy/apps/agc-native-sce/stage_metadata_contract.h"
        cases = (
            (("STAGE_F_CUBE", "STAGE_F_CUBE_METADATA"), True),
            (("STAGE_H_GEARS", "STAGE_H_GEARS_METADATA"), True),
            (("STAGE_H_GEARS", "STAGE_F_CUBE_METADATA"), False),
            (("STAGE_F_CUBE", "STAGE_H_GEARS_METADATA"), False),
            (("STAGE_H_GEARS",), False),
            (("STAGE_F_CUBE",), False),
        )
        for defines, expected in cases:
            with self.subTest(defines=defines), tempfile.TemporaryDirectory() as td:
                source = Path(td) / "contract.c"
                source.write_text(f'#include "{header}"\nint main(void) {{ return 0; }}\n')
                command = ["cc", "-std=c11", "-fsyntax-only", str(source)]
                command.extend(f"-D{name}=1" for name in defines)
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, expected,
                                 result.stderr)

    def test_stage_i_inherits_validated_gears_depth_contract(self):
        stage_i = (ROOT / "legacy/apps/agc-native-sce/stage_i_main.cpp").read_text()
        for define in ("STAGE_I_ANIMATED", "STAGE_H_GEARS",
                       "STAGE_G_DEPTH_ENABLE_TEST", "STAGE_G_DEPTH"):
            self.assertIn(f"#define {define} 1", stage_i)
        runtime = (ROOT / "legacy/apps/agc-native-sce/stage_b_main.cpp").read_text()
        self.assertIn("runner_input.frame_count = STAGE_I_FRAME_COUNT", runtime)
        self.assertIn("depth_registers=22", runtime)
        for name, count in (("stage_i_main.cpp", "300"),
                            ("stage_i1000_main.cpp", "1000"),
                            ("stage_i10000_main.cpp", "10000")):
            source = (ROOT / "legacy/apps/agc-native-sce" / name).read_text()
            self.assertIn(f"STAGE_I_FRAME_COUNT {count}", source)

    def test_gears_variant_uses_reference_black_clear(self):
        runtime = (ROOT / "legacy/apps/agc-native-sce/stage_b_main.cpp").read_text()
        guarded = runtime[runtime.index("#ifdef STAGE_H_GEARS\n/* es2gears reference clear color"):
                          runtime.index("constexpr std::uint32_t kRecoveryColor")]
        self.assertIn("UINT32_C(0xff000000)", guarded)
        self.assertIn("#else", guarded)


if __name__ == "__main__":
    unittest.main()
