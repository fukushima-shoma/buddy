import tempfile
import unittest
from pathlib import Path

from robot.camera import MockCamera, capture_still
from robot.camera_cli import build_parser, create_camera


class CameraTest(unittest.TestCase):
    def test_capture_still_starts_captures_and_closes(self) -> None:
        camera = MockCamera()

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "image.jpg"
            result = capture_still(camera, output, warmup=0, sleep=lambda _: None)

        self.assertEqual(result, output)
        self.assertTrue(camera.started)
        self.assertTrue(camera.closed)
        self.assertEqual(camera.captured, [output])

    def test_camera_closes_when_capture_fails(self) -> None:
        class FailingCamera(MockCamera):
            def capture_file(self, output: Path) -> None:
                raise RuntimeError("capture failed")

        camera = FailingCamera()

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "capture failed"):
                capture_still(
                    camera,
                    Path(directory) / "image.jpg",
                    warmup=0,
                    sleep=lambda _: None,
                )

        self.assertTrue(camera.closed)

    def test_cli_defaults_are_safe_for_initial_capture(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.output, Path("captures/latest.jpg"))
        self.assertEqual((args.width, args.height), (1920, 1080))
        self.assertEqual(args.backend, "mock")

    def test_mock_backend_is_available_without_camera_hardware(self) -> None:
        self.assertIsInstance(create_camera("mock", 1920, 1080), MockCamera)


if __name__ == "__main__":
    unittest.main()
