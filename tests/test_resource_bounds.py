import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from tanu.tools.base import ToolContext
from tanu.tools.file_ops import read_file
from tanu.tools.shell import exec as shell_exec


def context(workspace: Path) -> ToolContext:
    return ToolContext(
        cfg={"agents": {"defaults": {"max_tool_output_chars": 6000}}},
        workspace=workspace,
        restrict=True,
    )


class ResourceBoundTests(unittest.TestCase):
    def test_file_reads_are_bounded(self):
        with tempfile.TemporaryDirectory(prefix="tanu-bounds-") as tmp:
            workspace = Path(tmp)
            (workspace / "large.txt").write_text("x" * 20_000, encoding="utf-8")
            output = read_file("large.txt", _ctx=context(workspace))

        self.assertIn("file truncated", output)
        self.assertLess(len(output), 6200)

    def test_shell_capture_is_bounded(self):
        with tempfile.TemporaryDirectory(prefix="tanu-shell-") as tmp:
            command = subprocess.list2cmdline([
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('x' * 20000)",
            ])
            output = shell_exec(
                command,
                timeout=5,
                _ctx=context(Path(tmp)),
            )

        self.assertIn("stdout truncated", output)
        self.assertLess(len(output), 6200)


if __name__ == "__main__":
    unittest.main()
