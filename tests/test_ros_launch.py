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
        self.assertGreaterEqual(source.count('default_value="mock"'), 4)
        self.assertIn('executable="motor_node"', source)
        self.assertIn('executable="distance_node"', source)
        self.assertIn('executable="person_node"', source)
        self.assertIn('executable="power_node"', source)
        self.assertIn('executable="follow_node"', source)
        self.assertIn('executable="reaction_node"', source)
        self.assertIn('executable="reaction_output_node"', source)
        self.assertIn('"require_power_status": True', source)


if __name__ == "__main__":
    unittest.main()
