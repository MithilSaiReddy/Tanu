import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from tanu.session import SessionManager


class FakeAgent:
    def __init__(self, *args, callbacks=None, **kwargs):
        self.callbacks = callbacks or {}
        self.tools = type("Tools", (), {"callbacks": {}})()


class SessionLimitTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "runtime": {
                "max_sessions": 2,
                "max_history_messages": 4,
                "session_idle_seconds": 1800,
                "memory": {"soft_limit_mb": 600, "hard_limit_mb": 800},
            }
        }

    def test_evicts_oldest_session_and_history(self):
        with patch("tanu.session.AgentLoop", FakeAgent):
            manager = SessionManager(self.cfg)
            manager.memory_budget.current_mb = lambda include_children=True: 10
            manager.get("one")
            manager.append("one", "user", "private history")
            manager.get("two")
            manager.get("three")

        self.assertNotIn("one", manager.sessions())
        self.assertEqual(manager.history("one"), [])
        self.assertEqual(set(manager.sessions()), {"two", "three"})

    def test_history_is_bounded(self):
        with patch("tanu.session.AgentLoop", FakeAgent):
            manager = SessionManager(self.cfg)
            manager.memory_budget.current_mb = lambda include_children=True: 10
            manager.get("one")
            for index in range(8):
                manager.append("one", "user", str(index))

        self.assertEqual([item["content"] for item in manager.history("one")], ["4", "5", "6", "7"])


if __name__ == "__main__":
    unittest.main()
