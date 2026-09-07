#!/usr/bin/env python3
"""Transactional folder deployment for the isolated native SCE probe."""

from __future__ import annotations

import argparse
import ftplib
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from ps5_ftp import verify_remote_file  # noqa: E402


ROOT = Path(__file__).resolve().parent
TITLE_ID = "PPSA99998"
LOCAL_ROOT = ROOT / "dist" / TITLE_ID
REMOTE_BASE = PurePosixPath("/data/homebrew")
BACKUP_NAME = re.compile(r"^\.(?:eboot\.bin|dev\.conf)\.previous-[0-9a-f]{12}(?:-\d+)?$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files() -> list[Path]:
    return sorted(path for path in LOCAL_ROOT.rglob("*") if path.is_file())


def plan() -> dict[str, object]:
    eboot = LOCAL_ROOT / "eboot.bin"
    suffix = digest(eboot)[:12]
    staging = REMOTE_BASE / f".{TITLE_ID}.staging-{suffix}"
    final = REMOTE_BASE / TITLE_ID
    items = []
    for local in files():
        relative = local.relative_to(LOCAL_ROOT).as_posix()
        items.append({
            "local": str(local),
            "relative": relative,
            "remote_staging": str(staging / relative),
            "bytes": local.stat().st_size,
            "sha256": digest(local),
            "self_container": local.read_bytes()[:4] in (
                bytes.fromhex("4f153d1d"), bytes.fromhex("5414f5ee")
            ),
        })
    return {
        "title_id": TITLE_ID,
        "staging": str(staging),
        "final": str(final),
        "collision_paths": [
            str(final),
            f"/system_ex/app/{TITLE_ID}",
            f"/user/app/{TITLE_ID}",
            str(staging),
        ],
        "files": items,
    }


def exists(ftp: ftplib.FTP, path: str) -> bool:
    current = ftp.pwd()
    try:
        ftp.cwd(path)
        return True
    except ftplib.error_perm as exc:
        if str(exc).startswith("550"):
            return False
        raise
    finally:
        ftp.cwd(current)


def file_exists(ftp: ftplib.FTP, path: str) -> bool:
    try:
        size = ftp.size(path)
        # The console FTP server exposes SIZE(-1) as unsigned UINT64_MAX for a
        # missing hidden path instead of returning 550.
        return size is not None and size != 0xFFFFFFFFFFFFFFFF
    except ftplib.error_perm as exc:
        if str(exc).startswith("550"):
            return False
        raise


def delete_file(ftp: ftplib.FTP, path: str) -> None:
    """Delete a file, accepting ftpsrv's nonstandard successful 226 reply."""
    try:
        ftp.delete(path)
    except ftplib.error_reply as exc:
        if str(exc) != "226 File deleted":
            raise


def ensure_parent_dirs(ftp: ftplib.FTP, root: str, relative: str,
                       created: list[str]) -> None:
    parent = PurePosixPath(relative).parent
    current = PurePosixPath(root)
    for component in parent.parts:
        if component in ("", "."):
            continue
        current /= component
        path = str(current)
        if not exists(ftp, path):
            ftp.mkd(path)
            created.append(path)


def verify_upload(ftp: ftplib.FTP, host: str, item: dict[str, object]) -> None:
    del host  # compatibility with existing callers
    remote = str(item["remote_staging"])
    verify_remote_file(ftp, remote, int(item["bytes"]), str(item["sha256"]),
                       bool(item["self_container"]))


def deploy(host: str, port: int, journal: Path) -> None:
    manifest = plan()
    created_dirs: list[str] = []
    uploaded: list[str] = []
    promoted = False

    def record(event: str, **fields: object) -> None:
        journal.parent.mkdir(parents=True, exist_ok=True)
        entry = {"at_utc": datetime.now(timezone.utc).isoformat(),
                 "event": event, **fields}
        with journal.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
        print(json.dumps(entry, sort_keys=True), flush=True)

    with ftplib.FTP() as ftp:
        ftp.connect(host, port, 8)
        ftp.login()
        collisions = {path: exists(ftp, path) for path in manifest["collision_paths"]}
        record("native_sce_collision_check", collisions=collisions)
        if any(collisions.values()):
            raise RuntimeError("deployment collision; no write attempted")
        staging = str(manifest["staging"])
        try:
            ftp.mkd(staging)
            created_dirs.append(staging)
            for item in manifest["files"]:
                ensure_parent_dirs(ftp, staging, str(item["relative"]), created_dirs)
                remote = str(item["remote_staging"])
                with Path(str(item["local"])).open("rb") as stream:
                    ftp.storbinary(f"STOR {remote}", stream)
                uploaded.append(remote)
                verify_upload(ftp, host, item)
                record("native_sce_upload_verified", remote=remote,
                       bytes=item["bytes"], sha256=item["sha256"])
            ftp.rename(staging, str(manifest["final"]))
            promoted = True
            record("native_sce_promoted", source=staging, destination=manifest["final"])
        finally:
            if not promoted:
                for path in reversed(uploaded):
                    try:
                        ftp.delete(path)
                    except ftplib.all_errors:
                        pass
                for path in reversed(created_dirs):
                    try:
                        ftp.rmd(path)
                    except ftplib.all_errors:
                        pass


def swap_eboot(host: str, port: int, journal: Path,
               local_root: Path = LOCAL_ROOT,
               allow_missing_dev_conf: bool = False) -> None:
    """Replace eboot.bin and synchronize its optional /app0 dev.conf."""
    local = local_root / "eboot.bin"
    suffix = digest(local)[:12]
    root = REMOTE_BASE / TITLE_ID
    live = str(root / "eboot.bin")
    staged = str(root / f".eboot.bin.new-{suffix}")
    backup_base = str(root / f".eboot.bin.previous-{suffix}")
    with ftplib.FTP() as ftp:
        ftp.connect(host, port, 8)
        ftp.login()
        backup = backup_base
        generation = 1
        while file_exists(ftp, backup):
            generation += 1
            backup = f"{backup_base}-{generation}"
        state = {"root": exists(ftp, str(root)), "staged": file_exists(ftp, staged),
                 "backup": False, "live": file_exists(ftp, live),
                 "backup_generation": generation}
        if not state["root"] or state["staged"] or not state["live"]:
            raise RuntimeError(f"swap precondition/collision failed; no write attempted: {state}")
        with local.open("rb") as stream:
            ftp.storbinary(f"STOR {staged}", stream)
        item = {"remote_staging": staged, "bytes": local.stat().st_size,
                "sha256": digest(local), "self_container": True}
        verify_upload(ftp, host, item)

        config = local_root / "dev.conf"
        if not config.is_file() and not allow_missing_dev_conf:
            raise RuntimeError("deployment requires packaged /app0/dev.conf")
        config_live = str(root / "dev.conf")
        config_hash = digest(config) if config.is_file() else None
        config_backup = None
        if config.is_file():
            config_staged = str(root / f".dev.conf.new-{config_hash[:12]}")
            config_backup = str(root / f".dev.conf.previous-{config_hash[:12]}")
            generation = 1
            while file_exists(ftp, config_backup):
                generation += 1
                config_backup = str(
                    root / f".dev.conf.previous-{config_hash[:12]}-{generation}")
            if file_exists(ftp, config_staged):
                raise RuntimeError("logging config staging collision; no promotion attempted")
            with config.open("rb") as stream:
                ftp.storbinary(f"STOR {config_staged}", stream)
            config_item = {"remote_staging": config_staged,
                           "bytes": config.stat().st_size,
                           "sha256": config_hash, "self_container": False}
            verify_upload(ftp, host, config_item)
            config_promoted = False
            try:
                if file_exists(ftp, config_live):
                    ftp.rename(config_live, config_backup)
                ftp.rename(config_staged, config_live)
                config_promoted = True
            finally:
                if not config_promoted:
                    try:
                        if (not file_exists(ftp, config_live) and
                                file_exists(ftp, config_backup)):
                            ftp.rename(config_backup, config_live)
                    finally:
                        try:
                            delete_file(ftp, config_staged)
                        except ftplib.all_errors:
                            pass
        elif file_exists(ftp, config_live):
            delete_file(ftp, config_live)
        promoted = False
        try:
            ftp.rename(live, backup)
            ftp.rename(staged, live)
            promoted = True
        finally:
            if not promoted:
                try:
                    if not file_exists(ftp, live) and file_exists(ftp, backup):
                        ftp.rename(backup, live)
                finally:
                    try:
                        ftp.delete(staged)
                    except ftplib.all_errors:
                        pass
        if promoted:
            for transient_backup in (backup, config_backup):
                if transient_backup is None:
                    continue
                try:
                    delete_file(ftp, transient_backup)
                except ftplib.error_perm as exc:
                    if not str(exc).startswith("550"):
                        raise
    entry = {"at_utc": datetime.now(timezone.utc).isoformat(),
             "event": "native_sce_eboot_swapped", "live": live,
             "backup": backup, "bytes": local.stat().st_size,
             "sha256": digest(local), "backup_retained": False,
             "config_live": config_live if config.is_file() else None,
             "config_bytes": config.stat().st_size if config.is_file() else 0,
             "config_sha256": config_hash}
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")
    print(json.dumps(entry, sort_keys=True))


def prune_backups(host: str, port: int, apply: bool) -> None:
    """Remove only obsolete deploy-generated backups from the title root."""
    root = str(REMOTE_BASE / TITLE_ID)
    with ftplib.FTP() as ftp:
        ftp.connect(host, port, 8)
        ftp.login()
        listing: list[str] = []
        ftp.retrlines(f"LIST {root}", listing.append)
        names = sorted(line.split(None, 8)[-1] for line in listing
                       if len(line.split(None, 8)) == 9)
        targets = [name for name in names if BACKUP_NAME.fullmatch(name)]
        print(json.dumps({"event": "native_sce_backup_prune_plan",
                          "root": root, "targets": targets,
                          "count": len(targets), "apply": apply},
                         sort_keys=True))
        if apply:
            for name in targets:
                delete_file(ftp, str(PurePosixPath(root) / name))
            print(json.dumps({"event": "native_sce_backup_prune_complete",
                              "removed": len(targets)}, sort_keys=True))


def inspect_swap(host: str, port: int, local_root: Path = LOCAL_ROOT) -> None:
    local = local_root / "eboot.bin"
    suffix = digest(local)[:12]
    root = REMOTE_BASE / TITLE_ID
    paths = [str(root / name) for name in (
        "eboot.bin", f".eboot.bin.new-{suffix}",
        f".eboot.bin.previous-{suffix}")]
    result = {}
    with ftplib.FTP() as ftp:
        ftp.connect(host, port, 8); ftp.login()
        for path in paths:
            result[path] = ftp.size(path) if file_exists(ftp, path) else None
    print(json.dumps({"local_size": local.stat().st_size, "paths": result}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=2121)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--swap-eboot", action="store_true")
    parser.add_argument("--inspect-swap", action="store_true")
    parser.add_argument("--prune-backups", action="store_true")
    parser.add_argument("--allow-missing-dev-conf", action="store_true",
                        help="explicit PS5_NO_LOG A/B control only")
    parser.add_argument("--local-root", type=Path, default=LOCAL_ROOT)
    parser.add_argument("--journal", type=Path,
                        default=ROOT.parents[2] / "research/gpu/sessions/native-sce-deploy.jsonl")
    args = parser.parse_args()
    if not args.local_root.is_dir():
        raise SystemExit("build the native SCE title first")
    if args.prune_backups:
        if not args.host:
            raise SystemExit("--host is required with --prune-backups")
        prune_backups(args.host, args.port, args.apply)
        return 0
    if args.inspect_swap:
        if not args.host:
            raise SystemExit("--host is required with --inspect-swap")
        inspect_swap(args.host, args.port, args.local_root)
        return 0
    if args.swap_eboot:
        if not args.host:
            raise SystemExit("--host is required with --swap-eboot")
        swap_eboot(args.host, args.port, args.journal, args.local_root,
                   args.allow_missing_dev_conf)
        return 0
    manifest = plan()
    if not args.apply:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if not args.host:
        raise SystemExit("--host is required with --apply")
    deploy(args.host, args.port, args.journal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
