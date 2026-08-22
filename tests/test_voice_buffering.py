import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "src" / "tanu" / "plugins" / "voice" / "deskbot.py"
SPEC = importlib.util.spec_from_file_location("tanu_deskbot", MODULE_PATH)
deskbot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deskbot)


class VoiceBufferTests(unittest.TestCase):
    def test_pops_one_sentence_and_preserves_remainder(self):
        sentence, remainder = deskbot.DeskbotConnection._pop_complete_sentence(
            "The first answer is ready. The second is partial"
        )
        self.assertEqual(sentence, "The first answer is ready.")
        self.assertEqual(remainder, "The second is partial")

    def test_waits_for_sentence_boundary(self):
        sentence, remainder = deskbot.DeskbotConnection._pop_complete_sentence(
            "Still generating this response"
        )
        self.assertEqual(sentence, "")
        self.assertEqual(remainder, "Still generating this response")


if __name__ == "__main__":
    unittest.main()
