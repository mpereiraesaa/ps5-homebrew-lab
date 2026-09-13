import json
from pathlib import Path
import tempfile
import unittest

from tools.agent_coordination import CoordinationError, active_claims, append_event, read_events


def post(path, agent, kind, task, scopes=()):
    return append_event(path, agent=agent, kind=kind, task=task, target="all",
                        message=f"{kind} {task}", scopes=list(scopes), artifacts=[],
                        commit=None, pr=None)


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.log = Path(self.temp.name) / "mailbox.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def test_append_is_valid_jsonl_and_private(self):
        event = post(self.log, "orchestrator", "message", "roadmap")
        self.assertEqual(read_events(self.log), [event])
        self.assertEqual(self.log.stat().st_mode & 0o777, 0o600)
        json.loads(self.log.read_text())

    def test_parent_and_child_path_claims_conflict(self):
        post(self.log, "worker-a", "claim", "compiler", ["path:projects/ps5vk/src"])
        with self.assertRaises(CoordinationError):
            post(self.log, "worker-b", "claim", "dispatch",
                 ["path:projects/ps5vk/src/dispatch_encode.c"])

    def test_console_claim_is_exclusive_until_release(self):
        post(self.log, "worker-a", "claim", "run-a", ["console:PPSA99994"])
        with self.assertRaises(CoordinationError):
            post(self.log, "worker-b", "claim", "run-b", ["console:PPSA99994"])
        post(self.log, "worker-a", "release", "run-a")
        post(self.log, "worker-b", "claim", "run-b", ["console:PPSA99994"])
        self.assertEqual(active_claims(read_events(self.log))[0]["agent"], "worker-b")

    def test_completion_releases_only_matching_task(self):
        post(self.log, "worker", "claim", "one", ["path:a"])
        post(self.log, "worker", "claim", "two", ["path:b"])
        post(self.log, "worker", "complete", "one")
        claims = active_claims(read_events(self.log))
        self.assertEqual([(c["agent"], c["task"]) for c in claims], [("worker", "two")])


if __name__ == "__main__":
    unittest.main()
