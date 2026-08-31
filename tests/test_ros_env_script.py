from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RosEnvironmentScriptTest(unittest.TestCase):
    def test_sourcing_preserves_caller_variables(self) -> None:
        with TemporaryDirectory() as directory:
            setup = Path(directory) / "setup.bash"
            setup.write_text("export BUDDY_FAKE_ROS_SETUP=ok\n", encoding="utf-8")
            command = (
                'buddy_repo_dir="preserved"; '
                f'export BUDDY_ROS2_UNDERLAY="{setup}"; '
                f'export BUDDY_ROS2_OVERLAY="{setup}"; '
                f'source "{ROOT / "scripts/source_ros2.sh"}"; '
                'printf "%s:%s" "$buddy_repo_dir" "$BUDDY_FAKE_ROS_SETUP"'
            )

            result = subprocess.run(
                ["bash", "-c", command],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.stdout, "preserved:ok")
