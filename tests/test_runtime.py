import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "src" / "tanu" / "runtime.py"
SPEC = importlib.util.spec_from_file_location("tanu_runtime", MODULE_PATH)
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)


class EventBusTests(unittest.TestCase):
    def test_publish_subscribe_filter_and_unsubscribe(self):
        bus = runtime.LocalEventBus(max_events=16)
        received = []
        unsubscribe = bus.subscribe("task.completed", received.append)

        event = bus.publish("task.completed", {"id": 7}, source="test")
        bus.publish("task.started", {"id": 8}, source="test")
        unsubscribe()
        bus.publish("task.completed", {"id": 9}, source="test")

        self.assertEqual(event.sequence, 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(bus.recent("task.completed", 10)[-1]["payload"]["id"], "9")

    def test_history_and_payload_are_bounded(self):
        bus = runtime.LocalEventBus(max_events=16, max_payload_chars=256)
        for index in range(20):
            bus.publish("test", {"value": "x" * 500, "index": index})

        events = bus.recent(limit=50)
        self.assertEqual(len(events), 16)
        self.assertLessEqual(len(events[-1]["payload"]["value"]), 256)


class MemoryBudgetTests(unittest.TestCase):
    def test_pressure_thresholds(self):
        budget = runtime.MemoryBudget(soft_limit_mb=600, hard_limit_mb=800)
        budget.current_mb = lambda include_children=True: 599
        self.assertEqual(budget.pressure(), "normal")
        budget.current_mb = lambda include_children=True: 600
        self.assertEqual(budget.pressure(), "soft")
        budget.current_mb = lambda include_children=True: 800
        self.assertEqual(budget.pressure(), "hard")


if __name__ == "__main__":
    unittest.main()
