#!/usr/bin/env python3
"""Mirror a built title directory to the console over the lab FTP service.

Usage: PS5_HOST=<host> deploy_title_ftp.py <local_dist_dir> <remote_title_dir>
Example: PS5_HOST=ps5.local deploy_title_ftp.py \\
    projects/ps5-xash3d/dist/engine-boot/PPSA99996 /data/homebrew/PPSA99996

Every regular file is uploaded with STOR and read back for verification.
The helper disables ftpsrv's transparent SELF-to-ELF conversion on each FTP
connection, so every file, including eboot.bin and signed PRXs, must match the
stored size and SHA-256 exactly.
"""
from __future__ import annotations

import ftplib
import hashlib
import io
import os
import sys
import time
from pathlib import Path

PORT = 2121

from ps5_ftp import is_self_container, verify_remote_file


def ensure_dir(ftp: ftplib.FTP, remote_dir: str) -> None:
    parts = remote_dir.strip("/").split("/")
    path = ""
    for part in parts:
        path += "/" + part
        try:
            ftp.mkd(path)
        except ftplib.error_perm:
            pass


def main() -> int:
    if len(sys.argv) not in {3, 4}:
        print(
            "usage: deploy_title_ftp.py <local_dist_dir> <remote_title_dir> "
            "[legacy-eboot.elf]",
            file=sys.stderr,
        )
        return 2
    host = os.environ.get("PS5_HOST")
    if not host:
        print("PS5_HOST is required", file=sys.stderr)
        return 2
    local_root = Path(sys.argv[1]).resolve()
    remote_root = sys.argv[2].rstrip("/")
    files = sorted(p for p in local_root.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print(f"files={len(files)} bytes={total} -> {host}:{PORT}{remote_root}")
    started = time.time()
    with ftplib.FTP() as ftp:
        ftp.connect(host, PORT, 30)
        ftp.login()
        ftp.set_pasv(True)
        done_dirs: set[str] = set()
        sent = 0
        for index, local in enumerate(files, 1):
            relative = local.relative_to(local_root).as_posix()
            remote = f"{remote_root}/{relative}"
            remote_dir = remote.rsplit("/", 1)[0]
            if remote_dir not in done_dirs:
                ensure_dir(ftp, remote_dir)
                done_dirs.add(remote_dir)
            data = local.read_bytes()
            for attempt in range(3):
                try:
                    ftp.storbinary(f"STOR {remote}", io.BytesIO(data))
                    verify_remote_file(
                        ftp,
                        remote,
                        len(data),
                        hashlib.sha256(data).hexdigest(),
                        is_self_container(data),
                    )
                    break
                except RuntimeError as exc:
                    print(f"VERIFY FAILED {relative}: {exc}", file=sys.stderr)
                    return 1
                except (ftplib.Error, OSError) as exc:
                    print(f"retry {attempt + 1} {relative}: {exc}", file=sys.stderr)
                    ftp.close()
                    ftp.connect(host, PORT, 30)
                    ftp.login()
                    ftp.set_pasv(True)
            else:
                print(f"FAILED {relative}", file=sys.stderr)
                return 1
            how = "exact-self" if is_self_container(data) else "exact"
            sent += len(data)
            if index % 100 == 0 or local.name in ("eboot.bin", "dev.conf") or index == len(files):
                print(f"[{index}/{len(files)}] {relative} verified ({how}) {sent}/{total} bytes "
                      f"{time.time() - started:.0f}s")
    eboot = local_root / "eboot.bin"
    if eboot.exists():
        print(f"deploy complete; local eboot.bin sha256={hashlib.sha256(eboot.read_bytes()).hexdigest()}")
    else:
        print("deploy complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
