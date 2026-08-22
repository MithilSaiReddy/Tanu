import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from tanu.agent import SkillsLoader
from tanu.runtime import LocalEventBus


class SkillLimitTests(unittest.TestCase):
    def test_skill_count_and_prompt_size_are_bounded(self):
        with tempfile.TemporaryDirectory(prefix="tanu-skills-") as tmp:
            workspace = Path(tmp)
            for name in ("one", "two", "three"):
                skill_dir = workspace / "skills" / name
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(name * 1000, encoding="utf-8")

            bus = LocalEventBus()
            loader = SkillsLoader(
                workspace,
                event_bus=bus,
                max_skills=2,
                max_skill_chars=512,
                max_total_chars=700,
            )
            prompt = loader.get()

        self.assertLessEqual(len(prompt), 700)
        self.assertEqual(bus.recent("skills.changed", 1)[0]["payload"]["count"], "2")


if __name__ == "__main__":
    unittest.main()
