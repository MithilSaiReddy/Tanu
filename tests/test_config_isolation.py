import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tanu.config import DEFAULT_CONFIG, workspace_path


class ConfigIsolationTests(unittest.TestCase):
    def test_workspace_environment_override_wins(self):
        with tempfile.TemporaryDirectory(prefix="tanu-config-test-") as tmp:
            expected = Path(tmp) / "isolated-workspace"
            with patch.dict(os.environ, {"TANU_WORKSPACE_DIR": str(expected)}):
                self.assertEqual(workspace_path(DEFAULT_CONFIG), expected)


if __name__ == "__main__":
    unittest.main()
