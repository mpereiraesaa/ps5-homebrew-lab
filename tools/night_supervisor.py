#!/usr/bin/env python3
"""Conservative one-cycle PS5 homebrew supervisor.

This tool intentionally has no infinite autonomous test loop. An outer agent may
invoke one checked cycle at a time, inspect its JSONL journal, and decide whether
the next stage is safe.
"""

from __future__ import annotations

import argparse
import ftplib
import hashlib
import json
import re
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rehd_mods"))
sys.path.insert(0, str(ROOT / "homebrew_ps5" / "research" / "gpu" / "tools"))
try:
    from ps5debug import PS5Debug  # noqa: E402
except ModuleNotFoundError:  # Host-only contract tests do not need live CUA.
    PS5Debug = None
from phase0m_guard import classify as classify_phase0m_log  # noqa: E402
from phase0q_guard import classify as classify_phase0q_log  # noqa: E402
from phase0r_guard import classify as classify_phase0r_log  # noqa: E402
from phase0s_guard import classify as classify_phase0s_log  # noqa: E402
from stage_b_guard import classify as classify_stage_b_log  # noqa: E402
from stage_c_guard import classify as classify_stage_c_log  # noqa: E402
from native_label_guard import classify as classify_native_label_log  # noqa: E402
from ps5log_evidence import EvidenceError, validate_manifest  # noqa: E402


ALLOWED_TITLES = {"FAKE00000", "PPSA03524", "AGCP12002", "AGCP12003",
                  "PPSA99996", "PPSA99997", "PPSA99998", "PPSA99999"}
REQUIRED_PORTS = {"ps5debug": 744, "ftp": 2121, "shsrv": 2323,
                  "elfldr": 9021}
HELPERS = Path(__file__).resolve().parent / "bigapp-control"
AGC_APP = ROOT / "homebrew_ps5" / "legacy" / "apps" / "agc-phase0-native"
AGC_NATIVE_APP = ROOT / "homebrew_ps5" / "legacy" / "apps" / "agc-native-sce"
DMA_BUILDONLY = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
                 "ps5-agc-phase0d-dma-buildonly.elf")
DMA_BUILDONLY_REMOTE = "/data/homebrew/bin/ps5-agc-phase0d-dma-buildonly"
DMA_BUILDONLY_LOG = "/data/ps5-agc-phase0d-dma-buildonly.log"
QUEUE_STATE = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
               "ps5-agc-phase0e-driver-queue-state.elf")
QUEUE_STATE_REMOTE = "/data/homebrew/bin/ps5-agc-phase0e-driver-queue-state"
QUEUE_STATE_LOG = "/data/ps5-agc-phase0e-driver-queue-state.log"
QUEUE_HOLD = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
              "ps5-agc-phase0f-driver-queue-hold.elf")
QUEUE_HOLD_REMOTE = "/data/homebrew/bin/ps5-agc-phase0f-driver-queue-hold"
QUEUE_HOLD_LOG = "/data/ps5-agc-phase0f-driver-queue-hold.log"
MEMORY_POLICY = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
                 "ps5-agc-phase0n-memory-policy.elf")
MEMORY_POLICY_REMOTE = "/data/homebrew/bin/ps5-agc-phase0n-memory-policy"
MEMORY_POLICY_LOG = "/data/ps5-agc-phase0n-memory-policy.log"
FIXED_MAPPING = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
                 "ps5-agc-phase0o-fixed-mapping.elf")
FIXED_MAPPING_REMOTE = "/data/homebrew/bin/ps5-agc-phase0o-fixed-mapping"
FIXED_MAPPING_LOG = "/data/ps5-agc-phase0o-fixed-mapping.log"
BACKEND_STATE = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
                 "ps5-agc-phase0p-backend-state.elf")
BACKEND_STATE_REMOTE = "/data/homebrew/bin/ps5-agc-phase0p-backend-state"
BACKEND_STATE_LOG = "/data/ps5-agc-phase0p-backend-state.log"
PHASE0Q = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
           "ps5-agc-phase0q-batch-mapping.elf")
PHASE0Q_REMOTE = "/data/homebrew/bin/ps5-agc-phase0q-batch-mapping"
PHASE0Q_LOG = "/data/ps5-agc-phase0q-batch-mapping.log"
PHASE0Q_SHA256 = "8786fb7657574108d25a770a9c0984e48453d2cb47015cad1ca4963fdf6f6829"
PHASE0R = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
           "ps5-agc-phase0r-batch-first-submit.elf")
PHASE0R_REMOTE = "/data/homebrew/bin/ps5-agc-phase0r-batch-first-submit"
PHASE0R_LOG = "/data/ps5-agc-phase0r-batch-first-submit.log"
PHASE0R_SHA256 = "0f01bd8ba3fa9bfc84121ec6104572ecb744841202827253f5ba52984f5d8c44"
PHASE0S = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
           "ps5-agc-phase0s-batch-fence-submit.elf")
PHASE0S_REMOTE = "/data/homebrew/bin/ps5-agc-phase0s-batch-fence-submit"
PHASE0S_LOG = "/data/ps5-agc-phase0s-batch-fence-submit.log"
PHASE0S_SHA256 = "a6f20997c1f15f3f37f4747d8439211228fefd5b4d5a7a2fc925eaffd8f98af2"
PHASE0T = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
           "ps5-agc-phase0t-libagc-load-queue.elf")
PHASE0T_REMOTE = "/data/homebrew/bin/ps5-agc-phase0t-libagc-load-queue"
PHASE0T_LOG = "/data/ps5-agc-phase0t-libagc-load-queue.log"
PHASE0T_SHA256 = "daa6977e037745b0020826247ad369e9d048bbb2fe4addc2437d14e0941de774"
PHASE0U = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
           "ps5-agc-phase0u-context-bootstrap.elf")
PHASE0U_REMOTE = "/data/homebrew/bin/ps5-agc-phase0u-context-bootstrap"
PHASE0U_LOG = "/data/ps5-agc-phase0u-context-bootstrap.log"
PHASE0U_SHA256 = "e47af8a81f90ecf75d529b14e89ac1b6d72249e2147971b3fec887388666fff7"
PHASE0V = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
           "ps5-agc-phase0v-fs-table-va.elf")
PHASE0V_REMOTE = "/data/homebrew/bin/ps5-agc-phase0v-fs-table-va"
PHASE0V_LOG = "/data/ps5-agc-phase0v-fs-table-va.log"
PHASE0V_SHA256 = "5728f916abc8909d065d68db4e655eac0f91c142dca17ab7ba4e0df310801794"
PHASE0W = (ROOT / "homebrew_ps5" / "legacy" / "probes" / "ps5-agc-phase0" /
           "ps5-agc-phase0w-fixed-fs-bootstrap.elf")
PHASE0W_REMOTE = "/data/homebrew/bin/ps5-agc-phase0w-fixed-fs-bootstrap"
PHASE0W_LOG = "/data/ps5-agc-phase0w-fixed-fs-bootstrap.log"
PHASE0W_SHA256 = "e5c6f82741b6f05a6e63dabc18845b2c8136756ccb7da68ddbb340d07c19271a"
STAGE_B_FSELF_SHA256 = "64d9512ae5ab4d722fa9ee6394413d127ea2b38330c694839abc1c5216549571"
STAGE_C_FSELF_SHA256 = {
    256: "7c7d25a9ad4c87992463e9b9373ded9b42d465bdec009a658338659001c377de",
    4096: "0a21ffc45fe2b872a1c125e9d8aebd37f75a1173c1f40a636d5b8a5b87f6f2e5",
    65536: "fdf87d76bea6d628ca04ae40d836afcc2af53a1c9afc6fafdd4b14bf85d77bc9",
}


class SafetyStop(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Supervisor:
    def __init__(self, host: str, journal: Path, timeout: float = 5.0):
        self.host = host
        self.journal = journal
        self.timeout = timeout

    def record(self, event: str, **fields: object) -> None:
        entry = {"at_utc": utc_now(), "event": event, **fields}
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with self.journal.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(entry, sort_keys=True) + "\n")
            fp.flush()
        print(json.dumps(entry, sort_keys=True), flush=True)

    def port_open(self, port: int) -> bool:
        try:
            with socket.create_connection((self.host, port), self.timeout):
                return True
        except OSError:
            return False

    def health(self) -> dict[str, bool]:
        state = {name: self.port_open(port)
                 for name, port in REQUIRED_PORTS.items()}
        self.record("health", services=state)
        return state

    def require_health(self) -> None:
        state = self.health()
        failed = [name for name, ok in state.items() if not ok]
        if failed:
            raise SafetyStop("required services unavailable: " + ", ".join(failed))

    def require_phase0m_cleanup_safe(self, log: str) -> dict[str, object]:
        """Forbid cleanup when a phase 0M log cannot prove completion."""
        decision = classify_phase0m_log(log)
        self.record("phase0m_cleanup_gate", **decision)
        if not decision["close_allowed"]:
            raise SafetyStop(
                "phase 0M cleanup forbidden; retain FAKE00000, module and mapping"
            )
        return decision

    def require_phase0q_cleanup_safe(self, log: str) -> dict[str, object]:
        """Forbid close unless the mapping-only probe proves complete cleanup."""
        decision = classify_phase0q_log(log)
        self.record("phase0q_cleanup_gate", **decision)
        if not decision["close_allowed"]:
            raise SafetyStop(
                "phase 0Q close forbidden; retain FAKE00000 and mapping state"
            )
        return decision

    def require_phase0r_cleanup_safe(self, log: str) -> dict[str, object]:
        """Never close a phase 0R host without pre-submit cleanup or GPU ownership."""
        decision = classify_phase0r_log(log)
        self.record("phase0r_cleanup_gate", **decision)
        if not decision["close_allowed"]:
            raise SafetyStop(
                "phase 0R close forbidden; retain FAKE00000, driver, and mapping"
            )
        return decision

    def require_phase0s_cleanup_safe(self, log: str) -> dict[str, object]:
        """Never close phase 0S without pre-submit cleanup or fence completion."""
        decision = classify_phase0s_log(log)
        self.record("phase0s_cleanup_gate", **decision)
        if not decision["close_allowed"]:
            raise SafetyStop(
                "phase 0S close forbidden; retain FAKE00000, driver, and mapping"
            )
        return decision

    def require_stage_b_cleanup_safe(self, log: str) -> dict[str, object]:
        """Forbid cleanup unless GPU and VideoOut completion are both proven."""
        decision = classify_stage_b_log(log)
        self.record("stage_b_cleanup_gate", **decision)
        if not decision["cleanup_allowed"]:
            raise SafetyStop(
                "stage B cleanup forbidden; retain PPSA99998, VideoOut, "
                "driver, buffers and mappings"
            )
        return decision

    def require_stable_health(self, interval: float = 5.0) -> None:
        self.require_health()
        time.sleep(interval)
        self.require_health()
        self.record("stable_health_verified", interval_seconds=interval)

    def ftp_directory_exists(self, path: str) -> bool:
        try:
            with ftplib.FTP() as ftp:
                ftp.connect(self.host, REQUIRED_PORTS["ftp"], self.timeout)
                ftp.login()
                ftp.cwd(path)
            return True
        except ftplib.error_perm as exc:
            if str(exc).startswith("550"):
                return False
            raise SafetyStop("FTP permission error during collision check") from exc
        except (OSError, ftplib.Error) as exc:
            raise SafetyStop("FTP collision check failed") from exc

    def verify_ftp_file(self, ftp: ftplib.FTP, local: Path,
                        remote: str) -> int:
        """Verify an upload despite the PS5 FTP server's SELF transformation."""
        local_data = local.read_bytes()
        if local_data.startswith(b"O\x15=\x1d"):
            remote_size = self.shsrv_file_size(remote)
            if remote_size != len(local_data):
                raise SafetyStop(f"shsrv size verification failed: {remote}")
            return remote_size

        remote_data = bytearray()
        ftp.retrbinary(f"RETR {remote}", remote_data.extend)
        if (len(remote_data) != len(local_data) or
                hashlib.sha256(remote_data).digest() !=
                hashlib.sha256(local_data).digest()):
            raise SafetyStop(f"FTP content verification failed: {remote}")
        return len(remote_data)

    def shsrv_file_size(self, path: str) -> int:
        """Return a stored file size using shsrv's read-only stat command."""
        data = bytearray()
        with socket.create_connection(
                (self.host, REQUIRED_PORTS["shsrv"]), self.timeout) as sock:
            sock.settimeout(self.timeout)
            while b"$ " not in data and len(data) < 16384:
                data.extend(sock.recv(4096))
            sock.sendall(f"stat {path}\n".encode("ascii"))
            response_start = len(data)
            while len(data) < 32768:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
                if b"$ " in data[response_start:]:
                    break
        text = data[response_start:].decode("utf-8", "replace")
        match = re.search(r"(?:^|\n)size: (\d+)(?:\r?$|\n)", text,
                          re.MULTILINE)
        if not match:
            raise SafetyStop(f"shsrv stat was not parseable: {path}")
        return int(match.group(1))

    def shsrv_command(self, command: str, timeout: float = 20.0) -> str:
        if not re.fullmatch(r"hbldr /data/homebrew/bin/[A-Za-z0-9._-]+", command):
            raise SafetyStop("shsrv command is outside the restricted hbldr form")
        data = bytearray()
        with socket.create_connection(
                (self.host, REQUIRED_PORTS["shsrv"]), self.timeout) as sock:
            sock.settimeout(timeout)
            while b"$ " not in data and len(data) < 16384:
                data.extend(sock.recv(4096))
            response_start = len(data)
            sock.sendall((command + "\n").encode("ascii"))
            while len(data) < 65536:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                data.extend(chunk)
                if b"$ " in data[response_start:]:
                    break
        output = data[response_start:].decode("utf-8", "replace")
        output = "\n".join(
            line for line in output.splitlines() if not line.startswith("S/N:")
        )
        self.record("shsrv", command=command, output=output[-4096:])
        return output

    def upload_verified(self, local: Path, remote: str) -> None:
        if not local.is_file() or local.stat().st_size == 0:
            raise SafetyStop(f"missing local artifact: {local.name}")
        with ftplib.FTP() as ftp:
            ftp.connect(self.host, REQUIRED_PORTS["ftp"], self.timeout)
            ftp.login()
            with local.open("rb") as fp:
                ftp.storbinary(f"STOR {remote}", fp)
            size = self.verify_ftp_file(ftp, local, remote)
        self.record("upload_verified", remote=remote, bytes=size)

    def ftp_read_text(self, remote: str) -> str:
        data = bytearray()
        with ftplib.FTP() as ftp:
            ftp.connect(self.host, REQUIRED_PORTS["ftp"], self.timeout)
            ftp.login()
            ftp.retrbinary(f"RETR {remote}", data.extend)
        text = data.decode("utf-8", "replace")
        self.record("log_fetched", remote=remote, bytes=len(data),
                    output=text[-4096:])
        return text

    def preflight_agc_phase0(self) -> None:
        self.require_stable_health()
        self.require_bigapp(None)
        expected = "AGCP12002"
        for filename in ("eboot.elf", "installer.elf",
                         f"{expected}/eboot.bin",
                         f"{expected}/sce_sys/param.json",
                         f"{expected}/sce_sys/param.json.system",
                         f"{expected}/sce_sys/icon0.png"):
            path = AGC_APP / filename
            if not path.is_file() or path.stat().st_size == 0:
                raise SafetyStop(f"missing local AGC artifact: {filename}")
        for filename in (f"{expected}/sce_sys/param.json",
                         f"{expected}/sce_sys/param.json.system"):
            metadata = json.loads((AGC_APP / filename).read_text(encoding="utf-8"))
            if metadata.get("titleId") != expected:
                raise SafetyStop(f"title mismatch in local metadata: {filename}")
        collisions = {
            path: self.ftp_directory_exists(path)
            for path in (f"/system_ex/app/{expected}", f"/user/app/{expected}")
        }
        self.record("agc_phase0_preflight", title_id=expected,
                    remote_collisions=collisions)
        if any(collisions.values()):
            raise SafetyStop("AGCP12002 already exists; backup/ownership review required")

    def install_agc_phase0(self) -> None:
        self.preflight_agc_phase0()
        title_id = "AGCP12002"
        system_root = f"/system_ex/app/{title_id}"
        user_root = f"/user/app/{title_id}"
        created_dirs: list[str] = []
        uploaded_files: list[str] = []
        registered = False

        def cleanup_new_paths(ftp: ftplib.FTP) -> None:
            for path in reversed(uploaded_files):
                try:
                    ftp.delete(path)
                except ftplib.all_errors:
                    pass
            for path in reversed(created_dirs):
                try:
                    ftp.rmd(path)
                except ftplib.all_errors:
                    pass

        try:
            with ftplib.FTP() as ftp:
                ftp.connect(self.host, REQUIRED_PORTS["ftp"], self.timeout)
                ftp.login()
                response = ftp.sendcmd("MTRW")
                self.record("ftp_mtrw", accepted=response.startswith("200"))
                if not response.startswith("200"):
                    raise SafetyStop("FTP did not accept MTRW")
                for path in (system_root, f"{system_root}/sce_sys",
                             user_root, f"{user_root}/sce_sys"):
                    ftp.mkd(path)
                    created_dirs.append(path)

                uploads = (
                    (AGC_APP / f"{title_id}/eboot.bin",
                     f"{system_root}/eboot.bin"),
                    (AGC_APP / f"{title_id}/sce_sys/param.json.system",
                     f"{system_root}/sce_sys/param.json"),
                    (AGC_APP / f"{title_id}/sce_sys/param.json",
                     f"{user_root}/sce_sys/param.json"),
                    (AGC_APP / f"{title_id}/sce_sys/icon0.png",
                     f"{user_root}/sce_sys/icon0.png"),
                )
                for local, remote in uploads:
                    with local.open("rb") as fp:
                        ftp.storbinary(f"STOR {remote}", fp)
                    uploaded_files.append(remote)
                    remote_size = self.verify_ftp_file(ftp, local, remote)
                    self.record("upload_verified", remote=remote,
                                bytes=remote_size)

                output = self.run_elfldr(AGC_APP / "installer.elf")
                match = re.search(r"install AGCP12002=0x([0-9a-fA-F]+)", output)
                if not match or int(match.group(1), 16) != 0:
                    raise SafetyStop("AppInstUtil registration was not successful")
                registered = True
        except SafetyStop:
            if not registered:
                try:
                    with ftplib.FTP() as ftp:
                        ftp.connect(self.host, REQUIRED_PORTS["ftp"], self.timeout)
                        ftp.login()
                        ftp.sendcmd("MTRW")
                        cleanup_new_paths(ftp)
                except ftplib.all_errors:
                    pass
            raise
        except ftplib.all_errors as exc:
            if not registered:
                try:
                    with ftplib.FTP() as ftp:
                        ftp.connect(self.host, REQUIRED_PORTS["ftp"], self.timeout)
                        ftp.login()
                        ftp.sendcmd("MTRW")
                        cleanup_new_paths(ftp)
                except ftplib.all_errors:
                    pass
            raise SafetyStop("FTP install transaction failed") from exc

        self.require_health()
        self.record("agc_phase0_installed", title_id=title_id)

    def install_agc_phase0_v2(self) -> None:
        """Install the corrected image under a new, collision-free title ID."""
        self.require_stable_health()
        self.require_bigapp(None)
        title_id = "AGCP12003"
        system_root = f"/system_ex/app/{title_id}"
        user_root = f"/user/app/{title_id}"
        local_root = AGC_APP / title_id
        installer = AGC_APP / "installer-agcp12003.elf"
        required = (
            local_root / "eboot.bin",
            local_root / "sce_sys/param.json",
            local_root / "sce_sys/param.json.system",
            local_root / "sce_sys/icon0.png",
            installer,
        )
        if any(not path.is_file() or path.stat().st_size == 0 for path in required):
            raise SafetyStop("missing local AGCP12003 artifact")
        collisions = {
            path: self.ftp_directory_exists(path)
            for path in (system_root, user_root)
        }
        self.record("agc_phase0_v2_preflight", title_id=title_id,
                    remote_collisions=collisions)
        if any(collisions.values()):
            raise SafetyStop("AGCP12003 already exists; no overwrite attempted")

        created_dirs: list[str] = []
        uploaded_files: list[str] = []
        registered = False

        def cleanup_new_paths(ftp: ftplib.FTP) -> None:
            for path in reversed(uploaded_files):
                try:
                    ftp.delete(path)
                except ftplib.all_errors:
                    pass
            for path in reversed(created_dirs):
                try:
                    ftp.rmd(path)
                except ftplib.all_errors:
                    pass

        try:
            with ftplib.FTP() as ftp:
                ftp.connect(self.host, REQUIRED_PORTS["ftp"], self.timeout)
                ftp.login()
                response = ftp.sendcmd("MTRW")
                self.record("ftp_mtrw", accepted=response.startswith("200"))
                if not response.startswith("200"):
                    raise SafetyStop("FTP did not accept MTRW")
                for path in (system_root, f"{system_root}/sce_sys",
                             user_root, f"{user_root}/sce_sys"):
                    ftp.mkd(path)
                    created_dirs.append(path)
                uploads = (
                    (local_root / "eboot.bin", f"{system_root}/eboot.bin"),
                    (local_root / "sce_sys/param.json.system",
                     f"{system_root}/sce_sys/param.json"),
                    (local_root / "sce_sys/param.json",
                     f"{user_root}/sce_sys/param.json"),
                    (local_root / "sce_sys/icon0.png",
                     f"{user_root}/sce_sys/icon0.png"),
                )
                for local, remote in uploads:
                    with local.open("rb") as fp:
                        ftp.storbinary(f"STOR {remote}", fp)
                    uploaded_files.append(remote)
                    remote_size = self.verify_ftp_file(ftp, local, remote)
                    self.record("upload_verified", remote=remote,
                                bytes=remote_size)
                output = self.run_elfldr(installer)
                match = re.search(r"install AGCP12003=0x([0-9a-fA-F]+)", output)
                if not match or int(match.group(1), 16) != 0:
                    raise SafetyStop("AGCP12003 registration was not successful")
                registered = True
        except (SafetyStop, ftplib.Error, OSError) as exc:
            if not registered:
                try:
                    with ftplib.FTP() as ftp:
                        ftp.connect(self.host, REQUIRED_PORTS["ftp"], self.timeout)
                        ftp.login()
                        ftp.sendcmd("MTRW")
                        cleanup_new_paths(ftp)
                except (ftplib.Error, OSError):
                    pass
            if isinstance(exc, SafetyStop):
                raise
            raise SafetyStop("AGCP12003 install transaction failed") from exc
        self.require_health()
        self.record("agc_phase0_v2_installed", title_id=title_id)

    def foreground(self) -> dict[str, object]:
        try:
            with PS5Debug(self.host, REQUIRED_PORTS["ps5debug"], 15) as dbg:
                app = dbg.get_foreground_app()
            result = {"pid": app.pid, "name": app.name,
                      "title_id": app.titleid, "app_version": app.app_ver}
        except Exception as exc:
            result = {"error": type(exc).__name__}
        self.record("foreground", **result)
        return result

    def bigapp(self) -> dict[str, object]:
        output = self.run_elfldr(HELPERS / "status.elf")
        match = re.search(r"app_id=(-?\d+) identify_rc=(-?\d+) running=([^\s]+)",
                          output)
        if not match:
            raise SafetyStop("BigApp status response was not parseable")
        app_id = int(match.group(1))
        identify_rc = int(match.group(2))
        title_id = "" if match.group(3) == "none" else match.group(3)
        state = {"app_id": app_id, "identify_rc": identify_rc,
                 "title_id": title_id}
        self.record("bigapp", **state)
        return state

    def require_bigapp(self, expected: str | None) -> dict[str, object]:
        state = self.bigapp()
        actual = str(state.get("title_id") or "")
        if expected is None:
            if int(state["app_id"]) > 0:
                raise SafetyStop(f"unexpected BigApp: {actual or 'unidentified'}")
        elif actual != expected:
            raise SafetyStop(f"expected {expected}, found {actual or 'none'}")
        return state

    def run_elfldr(self, elf: Path) -> str:
        data = elf.read_bytes()
        if len(data) < 4 or data[:4] != b"\x7fELF":
            raise SafetyStop(f"not an ELF: {elf}")
        output = bytearray()
        with socket.create_connection((self.host, REQUIRED_PORTS["elfldr"]),
                                      self.timeout) as sock:
            sock.settimeout(15)
            sock.sendall(data)
            sock.shutdown(socket.SHUT_WR)
            while len(output) < 65536:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                output.extend(chunk)
        text = output.decode("utf-8", "replace")
        self.record("elfldr", elf=elf.name, bytes=len(data),
                    output=text[-4096:])
        return text

    def checked_close(self, title_id: str) -> None:
        if title_id not in ALLOWED_TITLES:
            raise SafetyStop(f"title is not allowlisted: {title_id}")
        helpers = {
            "FAKE00000": "close-fake.elf",
            "PPSA03524": "close-san-andreas.elf",
            "AGCP12002": "close-agc-phase0.elf",
            "AGCP12003": "close-agc-phase0-v2.elf",
            "PPSA99996": "close-xash3d.elf",
            "PPSA99997": "close-agc-gears.elf",
            "PPSA99998": "close-agc-native-sce.elf",
            "PPSA99999": "close-native-hello-world.elf",
        }
        helper = HELPERS / helpers[title_id]
        self.require_bigapp(title_id)
        output = self.run_elfldr(helper)
        expected_identity = f"target={title_id} "
        expected_running = f"running={title_id}"
        if expected_identity not in output or expected_running not in output:
            raise SafetyStop("close helper did not identify the exact title")
        if "title mismatch" in output or "close refused" in output:
            raise SafetyStop("close helper refused the request")

        # Killing a BigApp can tear down the helper before its final stdout is
        # delivered.  Preserve the exact-title precondition above, then allow
        # the independent status helper to prove the same clean transition.
        verification = "helper"
        deadline = time.monotonic() + 10
        while True:
            if "verified closed" in output:
                time.sleep(1)
            state = self.bigapp()
            actual = str(state.get("title_id") or "")
            if int(state["app_id"]) <= 0:
                if "verified closed" not in output:
                    verification = "external_status"
                break
            if actual != title_id:
                raise SafetyStop(
                    f"unexpected BigApp after close request: {actual or 'unidentified'}"
                )
            if time.monotonic() >= deadline:
                raise SafetyStop("clean close was not externally verified")
            time.sleep(0.5)
        self.require_health()
        self.record("close_verified", title_id=title_id,
                    verification=verification)

    def checked_close_agc_native_sce(self, expected_boot_token: str = "",
                                     expected_log_sha256: str = "",
                                     expected_manifest: str = "") -> None:
        """Close PPSA99998 only from validated local ps5logd evidence."""
        title_id = "PPSA99998"
        self.require_bigapp(title_id)
        if not expected_boot_token or not expected_log_sha256 or not expected_manifest:
            raise SafetyStop(
                "network-evidence close requires boot token, log hash and ps5log manifest")
        try:
            evidence = validate_manifest(
                Path(expected_manifest), expected_boot=expected_boot_token)
        except EvidenceError as exc:
            raise SafetyStop(f"ps5log evidence validation failed: {exc}") from exc
        if evidence["log_sha256"] != expected_log_sha256:
            raise SafetyStop("ps5log transcript hash changed; close refused")
        decision = classify_stage_b_log(
            bytes(evidence["log_bytes"]).decode("utf-8", "replace"))
        if not decision["close_allowed"]:
            raise SafetyStop("ps5log transcript does not prove safe completion")
        self.record("agc_native_sce_network_completion_verified",
                    title_id=title_id, boot_token=evidence["boot"],
                    log_sha256=evidence["log_sha256"],
                    manifest=evidence["manifest_path"])
        self.checked_close(title_id)

    def operator_close_agc_native_sce(self, operator_present: bool) -> None:
        """Exact-title close after an operator explicitly accepts retained state."""
        if not operator_present:
            raise SafetyStop("operator-present is required for retained-state close")
        title_id = "PPSA99998"
        self.require_bigapp(title_id)
        self.record("operator_retained_state_close_authorized",
                    title_id=title_id)
        self.checked_close(title_id)

    def run_agc_cpu_link(self) -> None:
        """Build, swap, rescan, run and safely collect the CPU-only AGC probe."""
        self.require_stable_health(interval=2.0)
        self.require_bigapp(None)
        subprocess.run(["bash", str(AGC_NATIVE_APP / "build.sh")],
                       cwd=ROOT / "homebrew_ps5", check=True)
        subprocess.run([sys.executable, str(AGC_NATIVE_APP / "verify.py")],
                       cwd=ROOT / "homebrew_ps5", check=True,
                       stdout=subprocess.DEVNULL)
        sys.path.insert(0, str(AGC_NATIVE_APP))
        import deploy as native_deploy
        native_deploy.swap_eboot(
            self.host, REQUIRED_PORTS["ftp"],
            ROOT / "homebrew_ps5/research/gpu/sessions/agc-cpu-link-deploy.jsonl")
        self.checked_restart_shadowmount()
        self.checked_launch("PPSA99998")
        log_path = "/mnt/sandbox/PPSA99998_000/download0/agc-native-sce-phase0.log"
        deadline = time.monotonic() + 45
        log = ""
        while time.monotonic() < deadline:
            try:
                log = self.ftp_read_text(log_path)
            except ftplib.all_errors:
                log = ""
            if "parked-safe; close exact title PPSA99998" in log:
                break
            time.sleep(1)
        else:
            raise SafetyStop("CPU link probe did not reach a safe parked state")
        required = (
            "AGC CPU direct-memory link probe v2",
            "preflight_embedded_sizes=true", "preflight_arena_layout=true",
            "direct_allocate=0x00000000", "direct_map=0x00000000",
            "preflight_asset_hashes=true", "preflight_ranges=true",
            "preflight_mapping_alignment=true",
            "agc_load=0x00000000", "agc_init=0x00000000",
            "create_pre_raster=0x00000000", "create_pixel=0x00000000",
            "link=0x00000000", "canaries_intact=true",
            "headers_unchanged_after_link=true", "code_unchanged=true",
            "cx_matches_host_and_static=true",
            "uc_matches_host_and_static=true", "transform_complete=true",
            "direct_arena_scrubbed=true", "agc_unload=0x00000000",
            "direct_unmap=0x00000000", "direct_release=0x00000000",
            "probe_complete=true",
        )
        missing = [item for item in required if item not in log]
        self.record("agc_cpu_link_result", passed=not missing, missing=missing,
                    log_sha256=hashlib.sha256(log.encode()).hexdigest())
        self.checked_close_agc_native_sce()
        self.require_stable_health(interval=2.0)
        if missing:
            raise SafetyStop("CPU link result was safely collected but did not pass")

    def run_native_label_submit(self, operator_present: bool) -> None:
        """Run one native four-byte ownership-fenced submit, never auto-close ambiguity."""
        if not operator_present:
            raise SafetyStop("native GPU submit requires a physically present operator")
        self.require_stable_health(interval=2.0)
        self.require_bigapp(None)
        subprocess.run(["bash", str(AGC_NATIVE_APP / "build_submit.sh")],
                       cwd=ROOT / "homebrew_ps5", check=True)
        proof = json.loads((ROOT / "homebrew_ps5/research/gpu/captures/"
                            "agc-native-label-local-proof.json").read_text())
        expected = "33de8177372a9d988dbf8b80ba2939ec802fa423e23746e58f3c043937cf11f5"
        if proof.get("fself_sha256") != expected:
            raise SafetyStop("native label artifact differs from audited SHA-256")
        sys.path.insert(0, str(AGC_NATIVE_APP))
        import deploy as native_deploy
        native_deploy.swap_eboot(
            self.host, REQUIRED_PORTS["ftp"],
            ROOT / "homebrew_ps5/research/gpu/sessions/native-label-deploy.jsonl",
            AGC_NATIVE_APP / "dist-submit/PPSA99998")
        self.checked_restart_shadowmount()
        self.checked_launch("PPSA99998")
        path = "/mnt/sandbox/PPSA99998_000/download0/agc-native-sce-phase0.log"
        deadline = time.monotonic() + 18
        log = ""
        while time.monotonic() < deadline:
            try:
                log = self.ftp_read_text(path)
            except ftplib.all_errors:
                log = ""
            decision = classify_native_label_log(log)
            if (decision["close_allowed"] or
                    decision["state"] == "parked_retain"):
                break
            time.sleep(0.5)
        decision = classify_native_label_log(log)
        self.record("native_label_result", **decision,
                    log_sha256=hashlib.sha256(log.encode()).hexdigest())
        if not decision["close_allowed"]:
            raise SafetyStop(
                "native label submit is ambiguous; PPSA99998 intentionally retained"
            )
        self.checked_close_agc_native_sce()
        self.require_stable_health(interval=2.0)
        if not decision["completion_proven"]:
            raise SafetyStop("native label failed cleanly before submit")

    def run_stage_b(self, operator_present: bool) -> None:
        """Build and run one CPU-filled AGC/VideoOut presentation transaction."""
        if not operator_present:
            raise SafetyStop("stage B requires a physically present operator")
        self.require_stable_health(interval=2.0)
        self.require_bigapp(None)
        subprocess.run(["bash", str(AGC_NATIVE_APP / "build_stage_b.sh")],
                       cwd=ROOT / "homebrew_ps5", check=True)
        proof = json.loads((ROOT / "homebrew_ps5/research/gpu/captures/"
                            "agc-stage-b-local-proof.json").read_text())
        if (not proof.get("approved_for_supervised_execution") or
                proof.get("fself_sha256") != STAGE_B_FSELF_SHA256):
            raise SafetyStop("stage B artifact differs from audited SHA-256")
        sys.path.insert(0, str(AGC_NATIVE_APP))
        import deploy as native_deploy
        native_deploy.swap_eboot(
            self.host, REQUIRED_PORTS["ftp"],
            ROOT / "homebrew_ps5/research/gpu/sessions/stage-b-deploy.jsonl",
            AGC_NATIVE_APP / "dist-stage-b/PPSA99998")
        self.checked_restart_shadowmount()
        self.checked_launch("PPSA99998")
        path = "/mnt/sandbox/PPSA99998_000/download0/agc-native-sce-phase0.log"
        deadline = time.monotonic() + 30
        log = ""
        decision: dict[str, object] = {}
        while time.monotonic() < deadline:
            try:
                log = self.ftp_read_text(path)
            except ftplib.all_errors:
                log = ""
            if "AGC native Stage B v1" not in log:
                time.sleep(0.5)
                continue
            decision = classify_stage_b_log(log)
            if (decision["cleanup_allowed"] or
                    decision["state"] == "parked"):
                break
            time.sleep(0.5)
        log = latest_nonempty_log or log
        decision = classify_stage_b_log(log)
        self.record("stage_b_result", **decision,
                    artifact_sha256=STAGE_B_FSELF_SHA256,
                    log_sha256=hashlib.sha256(log.encode()).hexdigest())
        if not decision["cleanup_allowed"]:
            raise SafetyStop(
                "stage B is incomplete or ambiguous; PPSA99998 intentionally retained"
            )
        self.checked_close_agc_native_sce()
        self.require_stable_health(interval=2.0)
        if not decision["completion_proven"]:
            raise SafetyStop("stage B failed cleanly before SetFlip")

    def run_stage_e(self, operator_present: bool) -> None:
        """Build and execute exactly one supervised gfx1013 triangle submit."""
        if not operator_present:
            raise SafetyStop("stage E requires a physically present operator")
        self.require_stable_health(interval=2.0)
        self.require_bigapp(None)
        subprocess.run(["bash", str(AGC_NATIVE_APP / "build_stage_e.sh")],
                       cwd=ROOT / "homebrew_ps5", check=True)
        gate_path = (ROOT / "homebrew_ps5/research/gpu/captures/"
                     "agc-stage-e-shader-execution-gate.json")
        subprocess.run([sys.executable, str(ROOT / "homebrew_ps5/research/gpu/tools/"
                                            "verify_stage_e_shader_execution_gate.py")],
                       cwd=ROOT / "homebrew_ps5", check=True)
        proof = json.loads((ROOT / "homebrew_ps5/research/gpu/captures/"
                            "agc-stage-e-live-local-proof.json").read_text())
        gate = json.loads(gate_path.read_text())
        if (proof.get("runtime_checkpoint") != 6 or
                proof.get("submission_reachable_in_this_build") is not True or
                proof.get("submission_limit") != 2 or
                gate.get("submit_ready") is not True):
            raise SafetyStop("Stage E visual artifact did not pass its submit gate")
        artifact_sha = str(proof.get("fself_sha256", ""))
        artifact = AGC_NATIVE_APP / "dist-stage-e/PPSA99998/eboot.bin"
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != artifact_sha:
            raise SafetyStop("Stage E artifact changed after verification")
        sys.path.insert(0, str(AGC_NATIVE_APP))
        import deploy as native_deploy
        native_deploy.swap_eboot(
            self.host, REQUIRED_PORTS["ftp"],
            ROOT / "homebrew_ps5/research/gpu/sessions/stage-e-visual-deploy.jsonl",
            AGC_NATIVE_APP / "dist-stage-e/PPSA99998")
        self.checked_restart_shadowmount()
        path = "/mnt/sandbox/PPSA99998_000/download0/agc-native-sce-phase0.log"
        old_log = ""
        try:
            old_log = self.ftp_read_text(path)
        except ftplib.all_errors:
            pass
        self.require_bigapp(None)
        output = self.run_elfldr(HELPERS / "launch-agc-native-sce.elf")
        match = re.search(r"launch rc=0x([0-9a-fA-F]{8})", output)
        if not match or int(match.group(1), 16) >= 0x80000000:
            raise SafetyStop("Stage E launch request was rejected")
        self.record("stage_e_launch_requested", launch_rc=match.group(1))
        # Read the persistent log immediately. Requiring BigApp first can miss
        # a short-lived process and would hide whether the transaction began.
        # The sandbox mount can briefly expose the previous completed log before
        # the new process truncates it.  Give startup one polling interval so a
        # stale completion cannot be classified as the current artifact.
        time.sleep(0.30)
        deadline = time.monotonic() + 45
        log = ""
        latest_nonempty_log = ""
        while time.monotonic() < deadline:
            try:
                candidate = self.ftp_read_text(path)
                if candidate and candidate != old_log:
                    log = candidate
                    latest_nonempty_log = candidate
            except ftplib.all_errors:
                log = latest_nonempty_log
            if "AGC native Stage E v1" not in log:
                time.sleep(0.25)
                continue
            decision = classify_stage_b_log(log)
            if decision["cleanup_allowed"] or decision["state"] == "parked":
                break
            time.sleep(0.25)
        log = latest_nonempty_log or log
        decision = classify_stage_b_log(log)
        self.record("stage_e_visual_result", **decision,
                    artifact_sha256=artifact_sha,
                    log_sha256=hashlib.sha256(log.encode()).hexdigest())
        if not decision["cleanup_allowed"]:
            raise SafetyStop(
                "Stage E is incomplete or ambiguous; PPSA99998 intentionally retained")
        self.checked_close_agc_native_sce()
        if not decision["completion_proven"]:
            raise SafetyStop("Stage E failed cleanly before its single submit")
        self.run_cleanup(True)

    def run_stage_c(self, operator_present: bool, fill_bytes: int) -> None:
        """Build and run one prerequisite-gated private-memory Stage C fill."""
        if not operator_present:
            raise SafetyStop("stage C requires a physically present operator")
        if fill_bytes not in STAGE_C_FSELF_SHA256:
            raise SafetyStop("Stage C fill size is not allowlisted")
        prerequisite = {4096: 256, 65536: 4096}.get(fill_bytes)
        if prerequisite is not None:
            prior_path = (ROOT / "homebrew_ps5/research/gpu/captures" /
                          f"agc-stage-c-{prerequisite}-runtime.json")
            if not prior_path.is_file():
                raise SafetyStop("previous Stage C runtime step is missing")
            prior = json.loads(prior_path.read_text())
            if not (prior.get("fill_bytes") == prerequisite and
                    prior.get("cleanup_complete") is True and
                    prior.get("target_matches") is True and
                    prior.get("prefix_canary_intact") is True and
                    prior.get("suffix_canary_intact") is True and
                    prior.get("outside_untouched") is True and
                    prior.get("process_close_verified") is True):
                raise SafetyStop("previous Stage C runtime step is not proven complete")
        self.require_stable_health(interval=2.0)
        self.require_bigapp(None)
        subprocess.run([
            "bash", str(AGC_NATIVE_APP / "build_stage_c.sh"), str(fill_bytes),
        ], cwd=ROOT / "homebrew_ps5", check=True)
        proof = json.loads((ROOT / "homebrew_ps5/research/gpu/captures/"
                            f"agc-stage-c-{fill_bytes}-local-proof.json").read_text())
        if (not proof.get("approved_for_supervised_execution") or
                proof.get("fself_sha256") != STAGE_C_FSELF_SHA256[fill_bytes]):
            raise SafetyStop("Stage C artifact differs from audited SHA-256")
        sys.path.insert(0, str(AGC_NATIVE_APP))
        import deploy as native_deploy
        native_deploy.swap_eboot(
            self.host, REQUIRED_PORTS["ftp"],
            ROOT / "homebrew_ps5/research/gpu/sessions/stage-c-deploy.jsonl",
            AGC_NATIVE_APP / f"dist-stage-c-{fill_bytes}/PPSA99998")
        self.checked_restart_shadowmount()
        self.checked_launch("PPSA99998")
        path = "/mnt/sandbox/PPSA99998_000/download0/agc-native-sce-phase0.log"
        deadline = time.monotonic() + 30
        log = ""
        while time.monotonic() < deadline:
            try:
                log = self.ftp_read_text(path)
            except ftplib.all_errors:
                log = ""
            if "AGC native Stage C v1" not in log:
                time.sleep(0.5)
                continue
            decision = classify_stage_c_log(log, fill_bytes)
            if decision["close_allowed"] or decision["state"] == "parked":
                break
            time.sleep(0.5)
        decision = classify_stage_c_log(log, fill_bytes)
        self.record("stage_c_result", **decision,
                    artifact_sha256=STAGE_C_FSELF_SHA256[fill_bytes],
                    log_sha256=hashlib.sha256(log.encode()).hexdigest())
        if not decision["close_allowed"]:
            raise SafetyStop(
                "Stage C is incomplete or ambiguous; PPSA99998 intentionally retained"
            )
        self.checked_close_agc_native_sce()
        self.require_stable_health(interval=2.0)
        if not decision["completion_proven"]:
            raise SafetyStop("Stage C failed cleanly before submit")

    def checked_launch(self, title_id: str) -> None:
        if title_id in {"AGCP12002", "AGCP12003"}:
            raise SafetyStop(
                f"{title_id} launch permanently disabled after pre-entry "
                "system-software failure CE-108262-9"
            )
        helpers = {
            "PPSA03524": "launch-san-andreas.elf",
            "PPSA99996": "launch-xash3d.elf",
            "PPSA99997": "launch-agc-gears.elf",
            "PPSA99998": "launch-agc-native-sce.elf",
        }
        if title_id not in helpers:
            raise SafetyStop(f"title is not launch-allowlisted: {title_id}")
        self.require_bigapp(None)
        output = self.run_elfldr(HELPERS / helpers[title_id])
        match = re.search(r"launch rc=0x([0-9a-fA-F]{8})", output)
        if not match or int(match.group(1), 16) >= 0x80000000:
            raise SafetyStop("launch helper did not report success")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            time.sleep(2)
            state = self.bigapp()
            if state.get("title_id") == title_id:
                self.require_health()
                self.record("launch_verified", title_id=title_id)
                return
        raise SafetyStop(f"{title_id} launch was not observed")

    def checked_restart_shadowmount(self) -> None:
        """Restart ShadowMountPlus through its supported single-instance path.

        A second ShadowMountPlus instance signals the existing instance, waits
        for its orderly teardown, and then performs startup mounting again.
        Never do this while a BigApp is active.
        """
        self.require_bigapp(None)
        payload = ROOT / "elf-arsenal" / "payloads" / "shadowmountplus.elf"
        if not payload.is_file():
            raise SafetyStop(f"ShadowMountPlus payload missing: {payload}")

        self.record("shadowmount_restart_requested", payload=str(payload),
                    bytes=payload.stat().st_size)
        self.run_elfldr(payload)

        deadline = time.monotonic() + 75
        last_log = ""
        while time.monotonic() < deadline:
            time.sleep(2)
            try:
                last_log = self.ftp_read_text("/data/shadowmount/debug.log")
            except ftplib.all_errors:
                last_log = ""
            if ("[STARTUP] scanner startup sync done" in last_log and
                    "[RESTART] Previous instance stopped" in last_log):
                self.require_health()
                self.require_bigapp(None)
                self.record("shadowmount_restart_verified",
                            startup_sync=True, bigapp_active=False)
                return
        raise SafetyStop(
            "ShadowMountPlus restart was not verified in debug.log; "
            f"tail={last_log[-500:]!r}"
        )

    def run_cleanup(self, operator_present: bool,
                    intro_wait_seconds: float = 8.0) -> None:
        """Displace residual app state through one clean GTA launch/close cycle.

        This never bypasses the PPSA99998 parked-safe marker and never handles
        an unexpected title.  San Andreas is used only through LNC launch/close;
        no debugger attach or process-memory operation occurs.
        """
        if not operator_present:
            raise SafetyStop("cleanup requires a physically present operator")
        if not 3.0 <= intro_wait_seconds <= 30.0:
            raise SafetyStop("cleanup intro wait must be between 3 and 30 seconds")
        self.require_stable_health(interval=2.0)
        state = self.bigapp()
        active = str(state.get("title_id") or "")
        if active == "PPSA99998":
            self.operator_close_agc_native_sce(operator_present)
        elif active == "PPSA03524":
            self.checked_close("PPSA03524")
        elif int(state["app_id"]) > 0:
            raise SafetyStop(f"cleanup refuses unexpected BigApp: {active or 'unidentified'}")
        self.require_bigapp(None)
        self.checked_launch("PPSA03524")
        self.record("cleanup_intro_wait_started",
                    seconds=intro_wait_seconds, title_id="PPSA03524")
        time.sleep(intro_wait_seconds)
        self.require_bigapp("PPSA03524")
        self.checked_close("PPSA03524")
        self.require_stable_health(interval=2.0)
        self.require_bigapp(None)
        self.record("cleanup_complete", displaced_with="PPSA03524",
                    debugger_attach=False, process_memory_access=False,
                    restart_used=False)

    def run_dma_buildonly(self) -> None:
        """Run the CPU-only packet audit through the validated BigApp host."""
        self.require_stable_health()
        self.require_bigapp(None)
        self.upload_verified(DMA_BUILDONLY, DMA_BUILDONLY_REMOTE)
        self.shsrv_command(f"hbldr {DMA_BUILDONLY_REMOTE}")

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = self.bigapp()
            if state.get("title_id") == "FAKE00000":
                break
            time.sleep(1)
        else:
            raise SafetyStop("FAKE00000 host was not identified after hbldr")

        log = self.ftp_read_text(DMA_BUILDONLY_LOG)
        required = (
            "AGC phase 0D start; CPU build-only; no modules, queue or submit",
            "template=c0055000 c0300000 00000000 00000000 00000000 00000000 00000004",
            "destination patched to private CPU address; guards intact",
            "AGC phase 0D exit result=0; submitted=no",
        )
        log_ok = all(line in log for line in required)
        self.checked_close("FAKE00000")
        self.require_stable_health(interval=2.0)
        if not log_ok:
            raise SafetyStop("phase 0D log did not prove every build-only invariant")
        self.record("dma_buildonly_verified", submitted=False)

    def run_phase0q_mapping(self) -> None:
        """Run one supervised mapping-only BatchMap transaction; never submit."""
        self.require_stable_health()
        self.require_bigapp(None)
        if hashlib.sha256(PHASE0Q.read_bytes()).hexdigest() != PHASE0Q_SHA256:
            raise SafetyStop("phase 0Q artifact hash differs from audited binary")

        old_log = ""
        try:
            old_log = self.ftp_read_text(PHASE0Q_LOG)
        except ftplib.all_errors:
            pass
        self.upload_verified(PHASE0Q, PHASE0Q_REMOTE)
        self.shsrv_command(f"hbldr {PHASE0Q_REMOTE}")

        host_seen = False
        log = ""
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = self.bigapp()
            if state.get("title_id") == "FAKE00000":
                host_seen = True
                break
            time.sleep(0.25)
        if not host_seen:
            raise SafetyStop("FAKE00000 host was not identified for phase 0Q")

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                candidate = self.ftp_read_text(PHASE0Q_LOG)
            except ftplib.all_errors:
                candidate = ""
            if candidate and candidate != old_log:
                log = candidate
            if "PARKED_PHASE0Q" in log or "phase0Q exit result=" in log:
                break
            time.sleep(0.25)

        decision = self.require_phase0q_cleanup_safe(log)
        self.checked_close("FAKE00000")
        self.require_stable_health(interval=2.0)
        self.record("phase0q_mapping_verified",
                    mapping_accepted=decision["mapping_accepted"],
                    cpu_canaries_passed=decision["cpu_canaries_passed"],
                    submitted=False)

    def run_phase0r_first_submit(self, operator_present: bool,
                                 confirmed_sha256: str) -> None:
        """Run exactly one ownership-fenced submit with fail-closed cleanup."""
        if not operator_present:
            raise SafetyStop("phase 0R requires an explicitly present operator")
        if confirmed_sha256 != PHASE0R_SHA256:
            raise SafetyStop("phase 0R confirmation hash mismatch")
        self.require_stable_health()
        self.require_bigapp(None)
        if hashlib.sha256(PHASE0R.read_bytes()).hexdigest() != PHASE0R_SHA256:
            raise SafetyStop("phase 0R artifact hash differs from audited binary")

        old_log = ""
        try:
            old_log = self.ftp_read_text(PHASE0R_LOG)
        except ftplib.all_errors:
            pass
        self.upload_verified(PHASE0R, PHASE0R_REMOTE)
        self.shsrv_command(f"hbldr {PHASE0R_REMOTE}", timeout=15.0)

        host_seen = False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = self.bigapp()
            if state.get("title_id") == "FAKE00000":
                host_seen = True
                break
            time.sleep(0.25)
        if not host_seen:
            raise SafetyStop("FAKE00000 host was not identified for phase 0R")

        log = ""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                candidate = self.ftp_read_text(PHASE0R_LOG)
            except ftplib.all_errors:
                candidate = ""
            if candidate and candidate != old_log:
                log = candidate
            if "PARKED_PHASE0R" in log or "phase0R exit result=" in log:
                break
            time.sleep(0.25)

        decision = self.require_phase0r_cleanup_safe(log)
        self.checked_close("FAKE00000")
        self.require_stable_health(interval=2.0)
        self.record("phase0r_first_submit_verified",
                    completion_proven=decision["completion_proven"],
                    submitted=decision["completion_proven"],
                    target_zero=decision["completion_proven"],
                    fence_zero=decision["completion_proven"])

    def run_phase0s_fence_submit(self, operator_present: bool,
                                 confirmed_sha256: str) -> None:
        """Run one fence-only submit to isolate command fetch from DMA_DATA."""
        if not operator_present:
            raise SafetyStop("phase 0S requires an explicitly present operator")
        if confirmed_sha256 != PHASE0S_SHA256:
            raise SafetyStop("phase 0S confirmation hash mismatch")
        self.require_stable_health()
        self.require_bigapp(None)
        if hashlib.sha256(PHASE0S.read_bytes()).hexdigest() != PHASE0S_SHA256:
            raise SafetyStop("phase 0S artifact hash differs from audited binary")

        old_log = ""
        try:
            old_log = self.ftp_read_text(PHASE0S_LOG)
        except ftplib.all_errors:
            pass
        self.upload_verified(PHASE0S, PHASE0S_REMOTE)
        self.shsrv_command(f"hbldr {PHASE0S_REMOTE}", timeout=15.0)

        host_seen = False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = self.bigapp()
            if state.get("title_id") == "FAKE00000":
                host_seen = True
                break
            time.sleep(0.25)
        if not host_seen:
            raise SafetyStop("FAKE00000 host was not identified for phase 0S")

        log = ""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                candidate = self.ftp_read_text(PHASE0S_LOG)
            except ftplib.all_errors:
                candidate = ""
            if candidate and candidate != old_log:
                log = candidate
            if "PARKED_PHASE0S" in log or "phase0S exit result=" in log:
                break
            time.sleep(0.25)

        decision = self.require_phase0s_cleanup_safe(log)
        self.checked_close("FAKE00000")
        self.require_stable_health(interval=2.0)
        self.record("phase0s_fence_submit_verified",
                    completion_proven=decision["completion_proven"],
                    submitted=decision["completion_proven"],
                    fence_zero=decision["completion_proven"],
                    dma_data_used=False)

    def run_phase0t_libagc_load(self, confirmed_sha256: str) -> None:
        """Load libSceAgc and compare queue fields without mapping or submit."""
        if confirmed_sha256 != PHASE0T_SHA256:
            raise SafetyStop("phase 0T confirmation hash mismatch")
        self.require_stable_health()
        self.require_bigapp(None)
        if hashlib.sha256(PHASE0T.read_bytes()).hexdigest() != PHASE0T_SHA256:
            raise SafetyStop("phase 0T artifact hash differs from audited binary")
        old_log = ""
        try:
            old_log = self.ftp_read_text(PHASE0T_LOG)
        except ftplib.all_errors:
            pass
        self.upload_verified(PHASE0T, PHASE0T_REMOTE)
        self.shsrv_command(f"hbldr {PHASE0T_REMOTE}", timeout=15.0)
        host_seen = False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = self.bigapp()
            if state.get("title_id") == "FAKE00000":
                host_seen = True
                break
            time.sleep(0.25)
        if not host_seen:
            raise SafetyStop("FAKE00000 host was not identified for phase 0T")
        log = ""
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                candidate = self.ftp_read_text(PHASE0T_LOG)
            except ftplib.all_errors:
                candidate = ""
            if candidate and candidate != old_log:
                log = candidate
            if "phase0T exit result=" in log or "phase0T watchdog" in log:
                break
            time.sleep(0.25)
        matches = re.findall(r"^phase0T exit result=(-?\d+) submitted=no$", log,
                             re.MULTILINE)
        if len(matches) != 1 or int(matches[0]) != 0:
            raise SafetyStop("phase 0T did not prove a unique clean exit")
        self.checked_close("FAKE00000")
        self.require_stable_health(interval=2.0)
        self.record("phase0t_libagc_load_verified", submitted=False,
                    log=log)

    def run_phase0u_context_bootstrap(self, confirmed_sha256: str) -> None:
        """Run the native AGC v8 context bootstrap without mapping or submit."""
        if confirmed_sha256 != PHASE0U_SHA256:
            raise SafetyStop("phase 0U confirmation hash mismatch")
        self.require_stable_health()
        self.require_bigapp(None)
        if hashlib.sha256(PHASE0U.read_bytes()).hexdigest() != PHASE0U_SHA256:
            raise SafetyStop("phase 0U artifact hash differs from audited binary")
        old_log = ""
        try:
            old_log = self.ftp_read_text(PHASE0U_LOG)
        except ftplib.all_errors:
            pass
        self.upload_verified(PHASE0U, PHASE0U_REMOTE)
        self.shsrv_command(f"hbldr {PHASE0U_REMOTE}", timeout=15.0)
        host_seen = False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = self.bigapp()
            if state.get("title_id") == "FAKE00000":
                host_seen = True
                break
            time.sleep(0.25)
        if not host_seen:
            raise SafetyStop("FAKE00000 host was not identified for phase 0U")
        log = ""
        deadline = time.monotonic() + 18
        while time.monotonic() < deadline:
            try:
                candidate = self.ftp_read_text(PHASE0U_LOG)
            except ftplib.all_errors:
                candidate = ""
            if candidate and candidate != old_log:
                log = candidate
            if "phase0U exit result=" in log or "phase0U watchdog" in log:
                break
            time.sleep(0.25)
        matches = re.findall(r"^phase0U exit result=(-?\d+) submitted=no$", log,
                             re.MULTILINE)
        if len(matches) != 1:
            raise SafetyStop("phase 0U did not produce one terminal record")
        state = self.bigapp()
        if state.get("title_id") == "FAKE00000":
            self.checked_close("FAKE00000")
        elif int(state.get("app_id", -1)) > 0:
            raise SafetyStop("unexpected BigApp after phase 0U")
        self.require_stable_health(interval=2.0)
        self.record("phase0u_context_bootstrap_observed", submitted=False,
                    result=int(matches[0]), log=log)

    def run_phase0v_fs_table_va(self, confirmed_sha256: str) -> None:
        """Test exact FS-table VA reservation without AGC or physical memory."""
        if confirmed_sha256 != PHASE0V_SHA256:
            raise SafetyStop("phase 0V confirmation hash mismatch")
        self.require_stable_health()
        self.require_bigapp(None)
        if hashlib.sha256(PHASE0V.read_bytes()).hexdigest() != PHASE0V_SHA256:
            raise SafetyStop("phase 0V artifact hash differs from audited binary")
        old_log = ""
        try: old_log = self.ftp_read_text(PHASE0V_LOG)
        except ftplib.all_errors: pass
        self.upload_verified(PHASE0V, PHASE0V_REMOTE)
        self.shsrv_command(f"hbldr {PHASE0V_REMOTE}", timeout=15.0)
        deadline=time.monotonic()+20; host_seen=False
        while time.monotonic()<deadline:
            if self.bigapp().get("title_id")=="FAKE00000": host_seen=True; break
            time.sleep(0.25)
        if not host_seen: raise SafetyStop("FAKE00000 host was not identified for phase 0V")
        log=""; deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            try: candidate=self.ftp_read_text(PHASE0V_LOG)
            except ftplib.all_errors: candidate=""
            if candidate and candidate!=old_log: log=candidate
            if "phase0V exit result=" in log: break
            time.sleep(0.25)
        matches=re.findall(r"^phase0V exit result=(-?\d+) submitted=no$",log,re.MULTILINE)
        if len(matches)!=1: raise SafetyStop("phase 0V did not produce one terminal record")
        state=self.bigapp()
        if state.get("title_id")=="FAKE00000": self.checked_close("FAKE00000")
        elif int(state.get("app_id",-1))>0: raise SafetyStop("unexpected BigApp after phase 0V")
        self.require_stable_health(interval=2.0)
        self.record("phase0v_fs_table_va_observed",submitted=False,
                    result=int(matches[0]),log=log)

    def run_phase0w_fixed_fs_bootstrap(self, confirmed_sha256: str) -> None:
        """Bootstrap with one private fixed FS-table page; never submit."""
        if confirmed_sha256 != PHASE0W_SHA256:
            raise SafetyStop("phase 0W confirmation hash mismatch")
        self.require_stable_health()
        self.require_bigapp(None)
        if hashlib.sha256(PHASE0W.read_bytes()).hexdigest() != PHASE0W_SHA256:
            raise SafetyStop("phase 0W artifact hash differs from audited binary")
        old_log = ""
        try: old_log = self.ftp_read_text(PHASE0W_LOG)
        except ftplib.all_errors: pass
        self.upload_verified(PHASE0W, PHASE0W_REMOTE)
        self.shsrv_command(f"hbldr {PHASE0W_REMOTE}", timeout=15.0)
        deadline=time.monotonic()+20; host_seen=False
        while time.monotonic()<deadline:
            if self.bigapp().get("title_id")=="FAKE00000": host_seen=True; break
            time.sleep(0.25)
        if not host_seen: raise SafetyStop("FAKE00000 host was not identified for phase 0W")
        log=""; deadline=time.monotonic()+18
        while time.monotonic()<deadline:
            try: candidate=self.ftp_read_text(PHASE0W_LOG)
            except ftplib.all_errors: candidate=""
            if candidate and candidate!=old_log: log=candidate
            if "phase0W exit result=" in log or "phase0W watchdog" in log: break
            time.sleep(0.25)
        matches=re.findall(r"^phase0W exit result=(-?\d+) submitted=no mapping_lifetime=process$",
                           log,re.MULTILINE)
        if len(matches)!=1: raise SafetyStop("phase 0W did not produce one terminal record")
        state=self.bigapp()
        if state.get("title_id")=="FAKE00000": self.checked_close("FAKE00000")
        elif int(state.get("app_id",-1))>0: raise SafetyStop("unexpected BigApp after phase 0W")
        self.require_stable_health(interval=2.0)
        self.record("phase0w_fixed_fs_bootstrap_observed",submitted=False,
                    result=int(matches[0]),log=log)

    def run_memory_policy(self) -> None:
        """Compare two small mappings without loading AGC or submitting work."""
        self.require_stable_health()
        self.require_bigapp(None)
        self.upload_verified(MEMORY_POLICY, MEMORY_POLICY_REMOTE)
        self.shsrv_command(f"hbldr {MEMORY_POLICY_REMOTE}")

        host_seen = False
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                state = self.bigapp()
                if state.get("title_id") == "FAKE00000":
                    host_seen = True
                    break
                time.sleep(0.5)
            if not host_seen:
                raise SafetyStop("FAKE00000 host was not identified for phase 0N")

            deadline = time.monotonic() + 15
            log = ""
            while time.monotonic() < deadline:
                try:
                    log = self.ftp_read_text(MEMORY_POLICY_LOG)
                except ftplib.all_errors:
                    log = ""
                if "AGC phase 0N exit completed_cases=2" in log:
                    break
                time.sleep(0.5)
            else:
                raise SafetyStop("phase 0N did not produce a complete terminal log")
            if "submitted=no" not in log or "no AGC, queue or submit" not in log:
                raise SafetyStop("phase 0N log did not prove its no-submit boundary")
        finally:
            if host_seen:
                self.checked_close("FAKE00000")
                self.require_stable_health(interval=2.0)
        self.record("memory_policy_verified", submitted=False)

    def run_fixed_mapping(self) -> None:
        """Validate one fixed-VA mapping without AGC or GPU submission."""
        self.require_stable_health()
        self.require_bigapp(None)
        self.upload_verified(FIXED_MAPPING, FIXED_MAPPING_REMOTE)
        self.shsrv_command(f"hbldr {FIXED_MAPPING_REMOTE}")
        host_seen = False
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                state = self.bigapp()
                if state.get("title_id") == "FAKE00000":
                    host_seen = True
                    break
                time.sleep(0.5)
            if not host_seen:
                raise SafetyStop("FAKE00000 host was not identified for phase 0O")
            deadline = time.monotonic() + 15
            log = ""
            while time.monotonic() < deadline:
                try:
                    log = self.ftp_read_text(FIXED_MAPPING_LOG)
                except ftplib.all_errors:
                    log = ""
                if "AGC phase 0O exit result=" in log:
                    break
                time.sleep(0.5)
            else:
                raise SafetyStop("phase 0O did not produce a terminal log")
            if "submitted=no" not in log or "no AGC, queue or submit" not in log:
                raise SafetyStop("phase 0O log did not prove its no-submit boundary")
        finally:
            if host_seen:
                self.checked_close("FAKE00000")
                self.require_stable_health(interval=2.0)
        self.record("fixed_mapping_verified", submitted=False)

    def run_queue_state(self) -> None:
        """Read bounded AgcDriver queue metadata without queue calls/submit."""
        self.require_stable_health()
        self.require_bigapp(None)
        self.upload_verified(QUEUE_STATE, QUEUE_STATE_REMOTE)
        self.shsrv_command(f"hbldr {QUEUE_STATE_REMOTE}")

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = self.bigapp()
            if state.get("title_id") == "FAKE00000":
                break
            time.sleep(1)
        else:
            raise SafetyStop("FAKE00000 host was not identified after hbldr")

        log = self.ftp_read_text(QUEUE_STATE_LOG)
        required = (
            "AGC phase 0E start; driver queue state read-only; no libAgc, CreateQueue or submit",
            "module base validated; wrappers match firmware 12.02",
            "default graphics queue header size=0x38",
            "AGC phase 0E exit result=0; called_create_queue=no; submitted=no",
        )
        state_line_ok = re.search(
            r"queue state nonzero: token=(yes|no) lock_context=(yes|no) aux=(yes|no)",
            log,
        ) is not None
        log_ok = all(line in log for line in required) and state_line_ok
        self.checked_close("FAKE00000")
        self.require_stable_health(interval=2.0)
        if not log_ok:
            raise SafetyStop("phase 0E log did not prove every read-only invariant")
        self.record("queue_state_verified", submitted=False,
                    called_create_queue=False)

    def run_backend_state(self) -> None:
        """Read only the three statically pinned AgcDriver backend fields."""
        self.require_stable_health()
        self.require_bigapp(None)
        self.upload_verified(BACKEND_STATE, BACKEND_STATE_REMOTE)
        self.shsrv_command(f"hbldr {BACKEND_STATE_REMOTE}")
        host_seen = False
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                state = self.bigapp()
                if state.get("title_id") == "FAKE00000":
                    host_seen = True
                    break
                time.sleep(0.5)
            if not host_seen:
                raise SafetyStop("FAKE00000 host was not identified for phase 0P")
            deadline = time.monotonic() + 15
            log = ""
            while time.monotonic() < deadline:
                try:
                    log = self.ftp_read_text(BACKEND_STATE_LOG)
                except ftplib.all_errors:
                    log = ""
                if "AGC phase 0P exit result=" in log:
                    break
                time.sleep(0.5)
            else:
                raise SafetyStop("phase 0P did not produce a terminal log")
            required = (
                "bounded backend-state read; no code reads, dlsym, queue calls, writes or submit",
                "callback_is_base_plus_1100=yes",
                "AGC phase 0P exit result=0; data_bytes_read=16; writes=0; submitted=no",
            )
            if not all(marker in log for marker in required):
                raise SafetyStop("phase 0P log did not prove every read-only invariant")
        finally:
            if host_seen:
                self.checked_close("FAKE00000")
                self.require_stable_health(interval=2.0)
        self.record("backend_state_verified", submitted=False)

    def run_queue_hold_inspection(self) -> None:
        """Inspect our held AgcDriver mapping externally, without attachment."""
        self.require_stable_health()
        self.require_bigapp(None)
        self.upload_verified(QUEUE_HOLD, QUEUE_HOLD_REMOTE)
        self.shsrv_command(f"hbldr {QUEUE_HOLD_REMOTE}")

        host_seen = False
        inspection = None
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                state = self.bigapp()
                if state.get("title_id") == "FAKE00000":
                    host_seen = True
                    break
                time.sleep(0.5)
            if not host_seen:
                raise SafetyStop("FAKE00000 host was not identified during hold")

            with PS5Debug(self.host, REQUIRED_PORTS["ps5debug"], 15) as dbg:
                candidates = []
                for proc in dbg.get_process_list():
                    if proc.name != "eboot.bin":
                        continue
                    info = dbg.get_process_info(proc.pid)
                    maps = dbg.get_process_maps(proc.pid)
                    code_maps = [m for m in maps
                                 if "libSceAgcDriver" in m.name and
                                 "x" in m.perms]
                    if code_maps:
                        candidates.append((proc.pid, info, code_maps))
                if len(candidates) != 1:
                    raise SafetyStop(
                        "expected one eboot with executable AgcDriver map, "
                        f"found {len(candidates)}"
                    )
                pid, info, code_maps = candidates[0]
                self.record("queue_probe_process_selected", pid=pid,
                            process_name=info.name,
                            title_id_reported=info.titleid or "unreported",
                            selection="unique eboot with AgcDriver executable map")
                if len(code_maps) != 1:
                    raise SafetyStop(
                        f"expected one executable AgcDriver map, found {len(code_maps)}"
                    )
                base = code_maps[0].start
                submit = dbg.read_memory(pid, base + 0x2960, 15)
                expected = bytes.fromhex(
                    "48 89 fe 48 8d 3d 4e ff 01 00 e9 41 f0 ff ff"
                )
                if submit != expected:
                    raise SafetyStop("runtime SubmitDcb wrapper mismatch")
                queue = dbg.read_memory(pid, base + 0x228b8, 0x50)
                size, queue_type = struct.unpack_from("<II", queue, 0)
                if size != 0x38:
                    raise SafetyStop(f"unexpected queue header size: {size:#x}")
                token = struct.unpack_from("<Q", queue, 8)[0]
                lock_context = struct.unpack_from("<Q", queue, 0x38)[0]
                aux = struct.unpack_from("<Q", queue, 0x40)[0]
                inspection = {
                    "queue_type": queue_type,
                    "token_nonzero": bool(token),
                    "lock_context_nonzero": bool(lock_context),
                    "aux_nonzero": bool(aux),
                    "target_writes": 0,
                    "debugger_attach": False,
                    "remote_calls": 0,
                }
                self.record("queue_mapping_inspected", **inspection)

            deadline = time.monotonic() + 35
            log = ""
            while time.monotonic() < deadline:
                try:
                    log = self.ftp_read_text(QUEUE_HOLD_LOG)
                except ftplib.all_errors:
                    log = ""
                if "AGC phase 0F exit result=0; attached=no; writes=0; submitted=no" in log:
                    break
                time.sleep(1)
            else:
                raise SafetyStop("phase 0F did not finish and unload in time")
        finally:
            if host_seen:
                self.checked_close("FAKE00000")
                self.require_stable_health(interval=2.0)
        if inspection is None:
            raise SafetyStop("phase 0F produced no queue inspection")
        self.record("queue_hold_inspection_verified", submitted=False,
                    target_writes=0, debugger_attach=False)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--journal", type=Path,
                        default=ROOT / "homebrew_ps5" / "research" / "gpu" /
                        "sessions" / "night-supervisor.jsonl")
    parser.add_argument("--operator-present", action="store_true")
    parser.add_argument("--cleanup-wait-seconds", type=float, default=8.0)
    parser.add_argument("--phase0r-sha", default="")
    parser.add_argument("--phase0s-sha", default="")
    parser.add_argument("--phase0t-sha", default="")
    parser.add_argument("--phase0u-sha", default="")
    parser.add_argument("--phase0v-sha", default="")
    parser.add_argument("--phase0w-sha", default="")
    parser.add_argument("--expected-boot-token", default="")
    parser.add_argument("--expected-log-sha256", default="")
    parser.add_argument("--expected-ps5log-manifest", default="")
    parser.add_argument("action", choices=("health", "status", "close-fake",
                                           "launch-gta", "close-gta",
                                           "preflight-agc-phase0",
                                           "install-agc-phase0",
                                           "install-agc-phase0-v2",
                                           "launch-agc-phase0-v2",
                                           "close-agc-phase0-v2",
                                           "close-agc-native-sce",
                                           "operator-close-agc-native-sce",
                                           "launch-agc-native-sce",
                                           "launch-xash3d", "close-xash3d",
                                           "cleanup",
                                           "restart-shadowmount",
                                           "run-dma-buildonly",
                                           "run-phase0q-mapping",
                                           "run-phase0r-first-submit",
                                           "run-phase0s-fence-submit",
                                           "run-phase0t-libagc-load",
                                           "run-phase0u-context-bootstrap",
                                           "run-phase0v-fs-table-va",
                                           "run-phase0w-fixed-fs-bootstrap"))
    args = parser.parse_args()
    sup = Supervisor(args.host, args.journal)
    try:
        sup.require_health()
        if args.action == "status":
            sup.foreground()
            sup.bigapp()
        elif args.action == "close-fake":
            sup.checked_close("FAKE00000")
        elif args.action == "launch-gta":
            sup.checked_launch("PPSA03524")
        elif args.action == "close-gta":
            sup.checked_close("PPSA03524")
        elif args.action == "preflight-agc-phase0":
            sup.preflight_agc_phase0()
        elif args.action == "install-agc-phase0":
            sup.install_agc_phase0()
        elif args.action == "install-agc-phase0-v2":
            sup.install_agc_phase0_v2()
        elif args.action == "launch-agc-phase0-v2":
            sup.checked_launch("AGCP12003")
        elif args.action == "close-agc-phase0-v2":
            sup.checked_close("AGCP12003")
        elif args.action == "close-agc-native-sce":
            sup.checked_close_agc_native_sce(
                args.expected_boot_token, args.expected_log_sha256,
                args.expected_ps5log_manifest)
        elif args.action == "operator-close-agc-native-sce":
            sup.operator_close_agc_native_sce(args.operator_present)
        elif args.action == "launch-agc-native-sce":
            sup.checked_launch("PPSA99998")
        elif args.action == "launch-xash3d":
            sup.checked_launch("PPSA99996")
        elif args.action == "close-xash3d":
            sup.checked_close("PPSA99996")
        elif args.action == "cleanup":
            sup.run_cleanup(args.operator_present, args.cleanup_wait_seconds)
        elif args.action == "restart-shadowmount":
            sup.checked_restart_shadowmount()
        elif args.action == "run-dma-buildonly":
            sup.run_dma_buildonly()
        elif args.action == "run-phase0q-mapping":
            sup.run_phase0q_mapping()
        elif args.action == "run-phase0r-first-submit":
            sup.run_phase0r_first_submit(args.operator_present, args.phase0r_sha)
        elif args.action == "run-phase0s-fence-submit":
            sup.run_phase0s_fence_submit(args.operator_present, args.phase0s_sha)
        elif args.action == "run-phase0t-libagc-load":
            sup.run_phase0t_libagc_load(args.phase0t_sha)
        elif args.action == "run-phase0u-context-bootstrap":
            sup.run_phase0u_context_bootstrap(args.phase0u_sha)
        elif args.action == "run-phase0v-fs-table-va":
            sup.run_phase0v_fs_table_va(args.phase0v_sha)
        elif args.action == "run-phase0w-fixed-fs-bootstrap":
            sup.run_phase0w_fixed_fs_bootstrap(args.phase0w_sha)
        return 0
    except SafetyStop as exc:
        sup.record("safety_stop", reason=str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
