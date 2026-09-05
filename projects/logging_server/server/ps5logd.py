#!/usr/bin/env python3
"""ps5logd: development-PC log server for PS5 homebrew line streams.

Homebrew payloads and native titles connect over TCP (or send UDP datagrams),
optionally announce themselves with one HELLO line, then stream one record per
line. The server stores every received line verbatim in a per-run file, prints
a decoded view to the terminal, detects sequence gaps, and writes an atomic
JSON manifest when the run ends. It depends only on the Python standard
library.

Wire format: see PROTOCOL.md next to this file's project root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROTOCOL = "ps5log/1"
DEFAULT_PORT = 9300
DEFAULT_KEEP = 200
MAX_LINE_BYTES = 65536
RECV_BYTES = 65536

_HELLO_RE = re.compile(r"^HELLO (\S+)(.*)$")
_KV_RE = re.compile(r"(\w+)=(\S*)")
_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


# ----------------------------------------------------------------------------
# Protocol parsing (pure functions, unit-tested)
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Hello:
    protocol: str
    fields: dict[str, str]


@dataclass(frozen=True)
class Record:
    seq: Optional[int]
    mono_ns: Optional[int]
    level: str
    text: str
    raw: str

    @property
    def structured(self) -> bool:
        return self.seq is not None


def parse_hello(line: str) -> Optional[Hello]:
    """Parse ``HELLO ps5log/1 key=value ...``; return None for other lines."""
    match = _HELLO_RE.match(line)
    if match is None:
        return None
    return Hello(match.group(1), dict(_KV_RE.findall(match.group(2))))


def parse_bye(line: str) -> Optional[dict[str, str]]:
    """Parse ``BYE key=value ...``; return None for other lines."""
    if line != "BYE" and not line.startswith("BYE "):
        return None
    return dict(_KV_RE.findall(line[3:]))


def parse_record(line: str) -> Record:
    """Parse ``<seq>\\t<mono_ns>\\t<level>\\t<text>``.

    Anything that does not match is kept as a RAW record so that plain
    ``printf | nc`` style clients still produce usable evidence.
    """
    parts = line.split("\t", 3)
    if len(parts) == 4:
        try:
            seq = int(parts[0], 10)
            mono_ns = int(parts[1], 10)
        except ValueError:
            pass
        else:
            level = parts[2].strip() or "INFO"
            return Record(seq, mono_ns, level, parts[3], line)
    return Record(None, None, "RAW", line, line)


def safe_name(value: str, fallback: str) -> str:
    cleaned = _UNSAFE_NAME_RE.sub("-", value).strip("-.")
    return cleaned[:48] or fallback


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S") + f"{moment.microsecond // 1000:03d}Z"


# ----------------------------------------------------------------------------
# Run storage
# ----------------------------------------------------------------------------

@dataclass
class Run:
    """One connection's evidence: verbatim log file plus manifest."""

    store: "RunStore"
    run_id: str
    path: Path
    manifest_path: Path
    identity: dict[str, str]
    peer: str
    transport: str
    started: datetime
    handle: object = field(repr=False)
    sha256: "hashlib._Hash" = field(default_factory=hashlib.sha256, repr=False)
    bytes_written: int = 0
    records: int = 0
    raw_lines: int = 0
    oversized_lines: int = 0
    first_seq: Optional[int] = None
    last_seq: Optional[int] = None
    first_mono_ns: Optional[int] = None
    last_mono_ns: Optional[int] = None
    gaps: list[dict[str, int]] = field(default_factory=list)
    hello: Optional[Hello] = None
    bye: Optional[dict[str, str]] = None
    finalized: bool = False

    @property
    def title(self) -> str:
        return self.identity.get("title", "unknown")

    @property
    def app(self) -> str:
        return self.identity.get("app", "unknown")

    def write_raw(self, line: bytes) -> None:
        payload = line + b"\n"
        self.handle.write(payload)
        self.handle.flush()
        self.sha256.update(payload)
        self.bytes_written += len(payload)

    def observe(self, record: Record) -> None:
        if not record.structured:
            self.raw_lines += 1
            return
        self.records += 1
        assert record.seq is not None and record.mono_ns is not None
        if self.first_seq is None:
            self.first_seq = record.seq
        elif self.last_seq is not None and record.seq != self.last_seq + 1:
            self.gaps.append({"expected": self.last_seq + 1, "got": record.seq})
        self.last_seq = record.seq
        if self.first_mono_ns is None:
            self.first_mono_ns = record.mono_ns
        self.last_mono_ns = record.mono_ns

    def relative_seconds(self, record: Record) -> Optional[float]:
        if record.mono_ns is None or self.first_mono_ns is None:
            return None
        return (record.mono_ns - self.first_mono_ns) / 1e9

    def finalize(self, close_reason: str) -> dict[str, object]:
        if self.finalized:
            return self.manifest(close_reason)
        self.finalized = True
        self.handle.flush()
        try:
            os.fsync(self.handle.fileno())
        except OSError:
            pass
        self.handle.close()
        manifest = self.manifest(close_reason)
        _write_json_atomic(self.manifest_path, manifest)
        self.store.update_latest(self)
        self.store.prune()
        return manifest

    def manifest(self, close_reason: str) -> dict[str, object]:
        ended = utc_now()
        return {
            "schema": 1,
            "protocol": self.hello.protocol if self.hello else None,
            "run_id": self.run_id,
            "title": self.title,
            "app": self.app,
            "identity": dict(self.identity),
            "peer": self.peer,
            "transport": self.transport,
            "started_utc": self.started.isoformat(),
            "ended_utc": ended.isoformat(),
            "duration_s": round((ended - self.started).total_seconds(), 6),
            "log_path": self.path.name,
            "bytes": self.bytes_written,
            "sha256": self.sha256.hexdigest(),
            "records": self.records,
            "raw_lines": self.raw_lines,
            "oversized_lines": self.oversized_lines,
            "first_seq": self.first_seq,
            "last_seq": self.last_seq,
            "gaps": list(self.gaps),
            "device_span_s": (
                None if self.first_mono_ns is None or self.last_mono_ns is None
                else round((self.last_mono_ns - self.first_mono_ns) / 1e9, 6)),
            "hello": self.hello is not None,
            "bye": self.bye is not None,
            "bye_fields": dict(self.bye) if self.bye else None,
            "clean": self.bye is not None,
            "close_reason": close_reason,
        }


class RunStore:
    """Creates run files under one directory and bounds their number."""

    def __init__(self, root: Path, keep: int = DEFAULT_KEEP) -> None:
        self.root = Path(root)
        self.keep = keep
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def open_run(self, identity: dict[str, str], peer: str, transport: str) -> Run:
        started = utc_now()
        title = safe_name(identity.get("title", ""), "unknown")
        app = safe_name(identity.get("app", ""), "unknown")
        token = safe_name(identity.get("boot", ""), safe_name(peer, "peer"))
        base = f"{stamp(started)}_{title}_{app}_{token}"
        with self._lock:
            path = self.root / f"{base}.log"
            suffix = 1
            while path.exists():
                path = self.root / f"{base}-{suffix}.log"
                suffix += 1
            handle = open(path, "xb")
        return Run(
            store=self, run_id=path.stem, path=path,
            manifest_path=path.with_suffix(".json"), identity=dict(identity),
            peer=peer, transport=transport, started=started, handle=handle,
        )

    def update_latest(self, run: Run) -> None:
        link = self.root / f"latest_{safe_name(run.title, 'unknown')}.log"
        temporary = self.root / f".{link.name}.tmp"
        try:
            if temporary.is_symlink() or temporary.exists():
                temporary.unlink()
            os.symlink(run.path.name, temporary)
            os.replace(temporary, link)
        except OSError:
            pass

    def prune(self) -> list[Path]:
        """Delete the oldest runs beyond ``keep``; return the removed logs."""
        logs = sorted(
            (p for p in self.root.glob("*.log") if not p.is_symlink()),
            key=lambda p: (p.stat().st_mtime, p.name))
        removed: list[Path] = []
        for path in logs[:max(0, len(logs) - self.keep)]:
            for victim in (path, path.with_suffix(".json")):
                try:
                    victim.unlink()
                except FileNotFoundError:
                    pass
            removed.append(path)
        return removed


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


# ----------------------------------------------------------------------------
# Terminal output
# ----------------------------------------------------------------------------

class Printer:
    LEVEL_COLORS = {
        "ERR": "\x1b[31m", "ERROR": "\x1b[31m", "WARN": "\x1b[33m",
        "MARK": "\x1b[36m", "RAW": "\x1b[35m",
    }
    RESET = "\x1b[0m"

    def __init__(self, stream=None, quiet: bool = False,
                 color: Optional[bool] = None,
                 record_filter: Optional[re.Pattern[str]] = None) -> None:
        self.stream = stream or sys.stdout
        self.quiet = quiet
        self.color = self.stream.isatty() if color is None else color
        self.record_filter = record_filter
        self._lock = threading.Lock()

    def _emit(self, text: str) -> None:
        with self._lock:
            self.stream.write(text + "\n")
            self.stream.flush()

    def _paint(self, level: str, text: str) -> str:
        if not self.color:
            return text
        color = self.LEVEL_COLORS.get(level.upper())
        return f"{color}{text}{self.RESET}" if color else text

    @staticmethod
    def _clock() -> str:
        return utc_now().strftime("%H:%M:%S.%f")[:-3]

    def event(self, run: Optional[Run], message: str) -> None:
        who = f"{run.title}/{run.app}" if run else "-"
        self._emit(f"{self._clock()} {who:<28} ## {message}")

    def record(self, run: Run, record: Record) -> None:
        if self.quiet:
            return
        if self.record_filter and not self.record_filter.search(record.text):
            return
        rel = run.relative_seconds(record)
        rel_text = f"+{rel:11.6f}s" if rel is not None else " " * 13
        seq_text = f"#{record.seq}" if record.seq is not None else "#-"
        who = f"{run.title}/{run.app}"
        line = (f"{self._clock()} {who:<28} {rel_text} {seq_text:>7} "
                f"{record.level:<5} {record.text}")
        self._emit(self._paint(record.level, line))


# ----------------------------------------------------------------------------
# Sessions and server
# ----------------------------------------------------------------------------

class Session:
    """Line framing and per-connection state for one TCP peer or UDP source."""

    def __init__(self, store: RunStore, printer: Printer, peer: str,
                 transport: str) -> None:
        self.store = store
        self.printer = printer
        self.peer = peer
        self.transport = transport
        self.buffer = b""
        self.run: Optional[Run] = None
        self.last_activity = time.monotonic()
        self.closed = False

    def feed(self, data: bytes) -> None:
        self.last_activity = time.monotonic()
        self.buffer += data
        while True:
            newline = self.buffer.find(b"\n")
            if newline < 0:
                if len(self.buffer) >= MAX_LINE_BYTES:
                    oversized, self.buffer = self.buffer[:MAX_LINE_BYTES], self.buffer[MAX_LINE_BYTES:]
                    self._ensure_run(oversized)
                    assert self.run is not None
                    self.run.oversized_lines += 1
                    self._handle_line(oversized)
                    continue
                return
            line, self.buffer = self.buffer[:newline], self.buffer[newline + 1:]
            if line.endswith(b"\r"):
                line = line[:-1]
            self._handle_line(line)

    def _ensure_run(self, first_line: bytes) -> Hello | None:
        if self.run is not None:
            return None
        hello = parse_hello(first_line.decode("utf-8", "replace"))
        identity = dict(hello.fields) if hello else {}
        self.run = self.store.open_run(identity, self.peer, self.transport)
        return hello

    def _handle_line(self, raw: bytes) -> None:
        hello = self._ensure_run(raw)
        assert self.run is not None
        self.run.write_raw(raw)
        text = raw.decode("utf-8", "replace")
        if hello is not None:
            self.run.hello = hello
            note = "" if hello.protocol == PROTOCOL else f" (unexpected protocol {hello.protocol})"
            self.printer.event(self.run, f"HELLO from {self.peer} via {self.transport}"
                                         f" -> {self.run.path.name}{note}")
            return
        if self.run.hello is None and self.run.records == 0 and self.run.raw_lines == 0 \
                and self.run.bye is None:
            self.printer.event(self.run, f"stream from {self.peer} via {self.transport}"
                                         f" without HELLO -> {self.run.path.name}")
        bye = parse_bye(text)
        if bye is not None:
            self.run.bye = bye
            self.printer.event(self.run, f"BYE {bye}")
            return
        record = parse_record(text)
        self.run.observe(record)
        if self.run.gaps and self.run.gaps[-1]["got"] == record.seq:
            gap = self.run.gaps[-1]
            self.printer.event(self.run, f"sequence gap: expected {gap['expected']}, got {gap['got']}")
        self.printer.record(self.run, record)

    def close(self, reason: str) -> Optional[dict[str, object]]:
        if self.closed:
            return None
        self.closed = True
        if self.buffer:
            trailing, self.buffer = self.buffer, b""
            self._handle_line(trailing)
        if self.run is None:
            self.printer.event(None, f"{self.transport} peer {self.peer} closed without data ({reason})")
            return None
        manifest = self.run.finalize(reason)
        state = "clean" if manifest["clean"] else "no BYE"
        self.printer.event(
            self.run,
            f"closed ({reason}, {state}): {manifest['records']} records, "
            f"{len(manifest['gaps'])} gaps, {manifest['bytes']} bytes -> {self.run.manifest_path.name}")
        return manifest


class Server:
    """Single-threaded selector loop serving TCP streams and UDP datagrams."""

    def __init__(self, store: RunStore, printer: Printer, bind: str = "0.0.0.0",
                 port: int = DEFAULT_PORT, udp: bool = True,
                 udp_idle_seconds: float = 30.0, poll_interval: float = 0.5) -> None:
        self.store = store
        self.printer = printer
        self.udp_idle_seconds = udp_idle_seconds
        self.poll_interval = poll_interval
        self.selector = selectors.DefaultSelector()
        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp.bind((bind, port))
        self.tcp.listen(64)
        self.tcp.setblocking(False)
        self.port = self.tcp.getsockname()[1]
        self.bind = bind
        self.selector.register(self.tcp, selectors.EVENT_READ, self._accept)
        self.udp: Optional[socket.socket] = None
        if udp:
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp.bind((bind, self.port))
            self.udp.setblocking(False)
            self.selector.register(self.udp, selectors.EVENT_READ, self._read_udp)
        self.tcp_sessions: dict[socket.socket, Session] = {}
        self.udp_sessions: dict[tuple[str, int], Session] = {}
        self._stop = threading.Event()
        self._stopped = threading.Event()

    # -- lifecycle ---------------------------------------------------------

    def serve_forever(self) -> None:
        try:
            while not self._stop.is_set():
                for key, _mask in self.selector.select(timeout=self.poll_interval):
                    key.data(key.fileobj)
                self._expire_udp()
        finally:
            self.close_all("server_shutdown")
            self._stopped.set()

    def shutdown(self, wait: bool = True, timeout: float = 5.0) -> None:
        self._stop.set()
        if wait:
            self._stopped.wait(timeout)

    def close_all(self, reason: str) -> None:
        for conn in list(self.tcp_sessions):
            self._close_tcp(conn, reason)
        for addr in list(self.udp_sessions):
            self.udp_sessions.pop(addr).close(reason)
        for sock in (self.tcp, self.udp):
            if sock is None:
                continue
            try:
                self.selector.unregister(sock)
            except (KeyError, ValueError):
                pass
            sock.close()
        self.selector.close()

    # -- TCP ----------------------------------------------------------------

    def _accept(self, _sock: socket.socket) -> None:
        try:
            conn, addr = self.tcp.accept()
        except OSError:
            return
        conn.setblocking(False)
        peer = f"{addr[0]}:{addr[1]}"
        self.tcp_sessions[conn] = Session(self.store, self.printer, peer, "tcp")
        self.selector.register(conn, selectors.EVENT_READ, self._read_tcp)
        self.printer.event(None, f"tcp connection from {peer}")

    def _read_tcp(self, conn: socket.socket) -> None:
        session = self.tcp_sessions.get(conn)
        if session is None:
            return
        try:
            data = conn.recv(RECV_BYTES)
        except (BlockingIOError, InterruptedError):
            return
        except OSError as exc:
            self._close_tcp(conn, f"error:{exc.errno}")
            return
        if not data:
            self._close_tcp(conn, "eof")
            return
        session.feed(data)

    def _close_tcp(self, conn: socket.socket, reason: str) -> None:
        session = self.tcp_sessions.pop(conn, None)
        try:
            self.selector.unregister(conn)
        except (KeyError, ValueError):
            pass
        conn.close()
        if session is not None:
            session.close(reason)

    # -- UDP ----------------------------------------------------------------

    def _read_udp(self, sock: socket.socket) -> None:
        try:
            data, addr = sock.recvfrom(RECV_BYTES)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            return
        session = self.udp_sessions.get(addr)
        if session is None:
            session = Session(self.store, self.printer, f"{addr[0]}:{addr[1]}", "udp")
            self.udp_sessions[addr] = session
        if not data.endswith(b"\n"):
            data += b"\n"
        session.feed(data)
        if session.run is not None and session.run.bye is not None:
            self.udp_sessions.pop(addr, None)
            session.close("bye")

    def _expire_udp(self) -> None:
        now = time.monotonic()
        for addr, session in list(self.udp_sessions.items()):
            if now - session.last_activity > self.udp_idle_seconds:
                self.udp_sessions.pop(addr)
                session.close("udp_idle")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def guess_lan_ip(probe_host: str = "192.0.2.1") -> Optional[str]:
    """Best-effort local address for the dev.conf hint; sends no packets."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((probe_host, 9))
            return sock.getsockname()[0]
    except OSError:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bind", default="0.0.0.0", help="address to listen on")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"TCP and UDP port (default {DEFAULT_PORT})")
    parser.add_argument("--runs-dir", default="runs", help="directory for run logs and manifests")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                        help="maximum number of run logs to retain")
    parser.add_argument("--no-udp", action="store_true", help="disable the UDP listener")
    parser.add_argument("--udp-idle", type=float, default=30.0,
                        help="seconds of silence that finalize a UDP run")
    parser.add_argument("--quiet", action="store_true", help="print session events only")
    parser.add_argument("--filter", metavar="REGEX", help="only print records whose text matches")
    parser.add_argument("--no-color", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    record_filter = re.compile(args.filter) if args.filter else None
    printer = Printer(quiet=args.quiet, color=False if args.no_color else None,
                      record_filter=record_filter)
    store = RunStore(Path(args.runs_dir), keep=args.keep)
    server = Server(store, printer, bind=args.bind, port=args.port,
                    udp=not args.no_udp, udp_idle_seconds=args.udp_idle)
    hint_ip = guess_lan_ip() or "<this-pc-ip>"
    printer.event(None, f"ps5logd listening on {args.bind}:{server.port} "
                        f"(tcp{'' if args.no_udp else '+udp'}), runs -> {store.root.resolve()}")
    printer.event(None, f"dev.conf hint: DEV_SERVER={hint_ip}  DEV_PORT={server.port}")

    def _stop(_signum, _frame) -> None:
        server.shutdown(wait=False)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    server.serve_forever()
    printer.event(None, "ps5logd stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
