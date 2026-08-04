import unittest

from robot.color_detection import HSV_RANGES, horizontal_position
from robot.color_cli import build_parser


class ColorDetectionTest(unittest.TestCase):
    def test_supported_colors_have_hsv_ranges(self) -> None:
        self.assertEqual(set(HSV_RANGES), {"red", "green", "blue"})
        self.assertEqual(len(HSV_RANGES["red"]), 2)

    def test_horizontal_position_uses_center_deadzone(self) -> None:
        self.assertEqual(horizontal_position(100, 1000), "left")
        self.assertEqual(horizontal_position(500, 1000), "center")
        self.assertEqual(horizontal_position(900, 1000), "right")

    def test_cli_defaults_to_latest_image_and_red(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(str(args.input), "captures/latest.jpg")
        self.assertEqual(str(args.output), "captures/color-detected.jpg")
        self.assertEqual(args.color, "red")
        self.assertEqual(args.min_area, 1000.0)


if __name__ == "__main__":
    unittest.main()
