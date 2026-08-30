import ast
from pathlib import Path
import unittest


class RosLaunchTest(unittest.TestCase):
    def test_follow_launch_is_valid_python_and_defaults_to_mock(self) -> None:
        launch_file = (
            Path(__file__).parents[1] / "launch/buddy_follow.launch.py"
        )
        source = launch_file.read_text(encoding="utf-8")

        ast.parse(source)
        self.assertGreaterEqual(source.count('default_value="mock"'), 3)
        self.assertIn('parameters=[{"enabled": False}]', source)
        self.assertIn('executable="motor_node"', source)
        self.assertIn('executable="distance_node"', source)
        self.assertIn('executable="person_node"', source)
        self.assertIn('executable="follow_node"', source)


if __name__ == "__main__":
    unittest.main()
