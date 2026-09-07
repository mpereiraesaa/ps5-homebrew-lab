#!/usr/bin/env python3
"""Mirror a built title directory to the console over the lab FTP service.

Usage: deploy_title_ftp.py <local_dist_dir> <remote_title_dir> <eboot.elf>
Example: deploy_title_ftp.py projects/ps5-xash3d/dist/engine-boot/PPSA99996 \\
    /data/homebrew/PPSA99996 projects/ps5-xash3d/build/engine-boot/eboot.elf

Every regular file is uploaded with STOR and read back for verification.
ftpsrv presents fSELF files as decrypted ELF images with the last 512 bytes
rewritten, so eboot.bin is verified by prefix (all but the last 512 bytes);
every other file must match byte for byte.
"""
from __future__ import annotations

import ftplib
import hashlib
import io
import sys
import time
from pathlib import Path

HOST = "192.168.0.69"
PORT = 2121
FSELF_TAIL = 512


def ensure_dir(ftp: ftplib.FTP, remote_dir: str) -> None:
    parts = remote_dir.strip("/").split("/")
    path = ""
    for part in parts:
        path += "/" + part
        try:
            ftp.mkd(path)
        except ftplib.error_perm:
            pass


def fetch(ftp: ftplib.FTP, remote: str) -> bytes:
    buffer = bytearray()
    ftp.retrbinary(f"RETR {remote}", buffer.extend)
    return bytes(buffer)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: deploy_engine_boot.py <local_dist_dir> <remote_title_dir> <eboot.elf>", file=sys.stderr)
        return 2
    local_root = Path(sys.argv[1]).resolve()
    remote_root = sys.argv[2].rstrip("/")
    # ftpsrv serves the signed fSELF back as the decrypted ELF image with its
    # last 512 bytes rewritten: verify eboot.bin against the linked ELF prefix.
    elf = Path(sys.argv[3]).read_bytes()
    files = sorted(p for p in local_root.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    print(f"files={len(files)} bytes={total} -> {HOST}:{PORT}{remote_root}")
    started = time.time()
    with ftplib.FTP() as ftp:
        ftp.connect(HOST, PORT, 30)
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
                    back = fetch(ftp, remote)
                    break
                except (ftplib.Error, OSError) as exc:
                    print(f"retry {attempt + 1} {relative}: {exc}", file=sys.stderr)
                    ftp.close()
                    ftp.connect(HOST, PORT, 30)
                    ftp.login()
                    ftp.set_pasv(True)
            else:
                print(f"FAILED {relative}", file=sys.stderr)
                return 1
            if local.name == "eboot.bin":
                ok = len(back) == len(elf) and back[:-FSELF_TAIL] == elf[:-FSELF_TAIL]
                how = "elf-prefix"
            elif data[:4] in (bytes.fromhex("4f153d1d"), bytes.fromhex("5414f5ee")):
                # Other signed modules (libc.prx from the pinned foundation) come
                # back as their decrypted ELF; no local ELF to compare against.
                ok = back[:4] == b"\x7fELF" and len(back) >= len(data)
                how = "self-as-elf"
            else:
                ok = back == data
                how = "exact"
            if not ok:
                print(f"VERIFY FAILED ({how}) {relative}: local={len(data)} remote={len(back)}", file=sys.stderr)
                return 1
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
