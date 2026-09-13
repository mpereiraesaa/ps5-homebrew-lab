#!/usr/bin/env python3
"""Append-only coordination mailbox for agents that cannot message each other.

The mailbox intentionally lives outside Git.  Every write takes an advisory
file lock and is followed by fsync, so independent Codex processes can share it
without rewriting one another's state.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import sys
from typing import Any
from datetime import datetime, timezone
from uuid import uuid4


DEFAULT_LOG = Path(os.environ.get(
    "PS5_AGENT_COORDINATION_LOG",
    str(Path.home() / ".codex/agent-coordination/ps5-vulkan.jsonl"),
))
KINDS = {"claim", "progress", "blocker", "message", "ack", "complete", "release"}
TERMINAL_KINDS = {"complete", "release"}


class CoordinationError(RuntimeError):
    pass


def _open_mailbox(path: Path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stream = path.open("a+", encoding="utf-8")
    os.chmod(path, 0o600)
    return stream


def _read_locked(stream) -> list[dict[str, Any]]:
    stream.seek(0)
    events: list[dict[str, Any]] = []
    for number, line in enumerate(stream, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CoordinationError(f"malformed mailbox line {number}: {exc}") from exc
        if event.get("schema") != "ps5-agent-coordination/1":
            raise CoordinationError(f"unsupported mailbox schema on line {number}")
        events.append(event)
    return events


def _path_scope(value: str) -> str:
    path = str(PurePosixPath(value.removeprefix("path:")))
    if path in {"", ".", "/"}:
        raise CoordinationError("path scopes must be narrower than the workspace root")
    return path.rstrip("/")


def scopes_conflict(left: str, right: str) -> bool:
    if left.startswith("path:") and right.startswith("path:"):
        a, b = _path_scope(left), _path_scope(right)
        return a == b or a.startswith(b + "/") or b.startswith(a + "/")
    return left == right


def active_claims(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        key = (event["agent"], event["task"])
        if event["kind"] == "claim":
            claims[key] = event
        elif event["kind"] in TERMINAL_KINDS:
            claims.pop(key, None)
    return list(claims.values())


def append_event(path: Path, *, agent: str, kind: str, task: str, target: str,
                 message: str, scopes: list[str], artifacts: list[str],
                 commit: str | None, pr: str | None) -> dict[str, Any]:
    if kind not in KINDS:
        raise CoordinationError(f"kind must be one of {sorted(KINDS)}")
    if not agent.strip() or not task.strip() or not message.strip():
        raise CoordinationError("agent, task and message are required")
    if kind == "claim" and not scopes:
        raise CoordinationError("a claim requires at least one --scope")
    if kind != "claim" and scopes:
        raise CoordinationError("only claim events may introduce scopes")
    event = {
        "schema": "ps5-agent-coordination/1",
        "event_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "agent": agent.strip(),
        "kind": kind,
        "task": task.strip(),
        "target": target.strip() or "all",
        "message": message.strip(),
        "scopes": sorted(set(scopes)),
        "artifacts": artifacts,
        "commit": commit,
        "pr": pr,
    }
    with _open_mailbox(path) as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        events = _read_locked(stream)
        if kind == "claim":
            for claim in active_claims(events):
                if claim["agent"] == event["agent"] and claim["task"] == event["task"]:
                    continue
                conflicts = [scope for scope in scopes for held in claim["scopes"]
                             if scopes_conflict(scope, held)]
                if conflicts:
                    raise CoordinationError(
                        f"scope conflict with {claim['agent']} task={claim['task']}: "
                        + ", ".join(sorted(set(conflicts)))
                    )
        stream.seek(0, os.SEEK_END)
        stream.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return event


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
        events = _read_locked(stream)
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return events


def command_post(args: argparse.Namespace) -> int:
    event = append_event(
        args.log, agent=args.agent, kind=args.kind, task=args.task,
        target=args.target, message=args.message, scopes=args.scope,
        artifacts=args.artifact, commit=args.commit, pr=args.pr,
    )
    print(json.dumps(event, indent=2, sort_keys=True))
    return 0


def command_tail(args: argparse.Namespace) -> int:
    events = read_events(args.log)
    if args.task:
        events = [event for event in events if event["task"] == args.task]
    if args.agent:
        events = [event for event in events if event["agent"] == args.agent]
    for event in events[-args.lines:]:
        if args.json:
            print(json.dumps(event, sort_keys=True))
        else:
            target = "" if event["target"] == "all" else f" -> {event['target']}"
            print(f"{event['timestamp']} {event['agent']}{target} "
                  f"[{event['kind']}/{event['task']}] {event['message']}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    events = read_events(args.log)
    claims = active_claims(events)
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        latest[event["task"]] = event
    result = {"mailbox": str(args.log), "event_count": len(events),
              "active_claims": claims, "latest_by_task": latest}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--log", type=Path, default=DEFAULT_LOG)
    sub = result.add_subparsers(dest="command", required=True)
    post = sub.add_parser("post", help="append one structured event")
    post.add_argument("--agent", required=True)
    post.add_argument("--kind", required=True, choices=sorted(KINDS))
    post.add_argument("--task", required=True)
    post.add_argument("--target", default="all")
    post.add_argument("--message", required=True)
    post.add_argument("--scope", action="append", default=[])
    post.add_argument("--artifact", action="append", default=[])
    post.add_argument("--commit")
    post.add_argument("--pr")
    post.set_defaults(run=command_post)
    tail = sub.add_parser("tail", help="read recent events")
    tail.add_argument("--lines", type=int, default=20)
    tail.add_argument("--task")
    tail.add_argument("--agent")
    tail.add_argument("--json", action="store_true")
    tail.set_defaults(run=command_tail)
    status = sub.add_parser("status", help="show current claims and latest events")
    status.set_defaults(run=command_status)
    return result


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "lines", 1) < 1:
        raise CoordinationError("--lines must be positive")
    try:
        return args.run(args)
    except CoordinationError as exc:
        print(f"coordination error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
