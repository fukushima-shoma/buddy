from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from robot.shared_experience_cli import main


class SharedExperienceCliTest(unittest.TestCase):
    def test_parent_can_add_list_delete_and_clear_memories(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "experiences.json"

            added = self._run(path, "add", "赤い車をロケット号と名付けた")
            experience_id = added.split("remembered=", 1)[1].split(" ", 1)[0]
            listed = self._run(path, "list")
            deleted = self._run(path, "delete", experience_id)
            self._run(path, "add", "段ボールの車を作った")
            cleared = self._run(path, "clear", "--yes")

            self.assertIn("ロケット号", listed)
            self.assertIn("deleted=true", deleted)
            self.assertIn("shared-experiences=cleared", cleared)
            self.assertIn("shared-experiences=empty", self._run(path, "list"))

    def test_clear_requires_explicit_yes(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "experiences.json"
            with self.assertRaisesRegex(RuntimeError, "--yes"):
                self._run(path, "clear")

    def _run(self, path: Path, *arguments: str) -> str:
        output = StringIO()
        argv = [
            "robot.shared_experience_cli",
            "--file",
            str(path),
            *arguments,
        ]
        with patch("sys.argv", argv), redirect_stdout(output):
            result = main()
        self.assertEqual(result, 0)
        return output.getvalue()


if __name__ == "__main__":
    unittest.main()
