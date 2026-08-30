from __future__ import annotations

from pathlib import Path
import signal
import unittest

from robot.mobility import PersonFollowProcessController, Ros2FollowController


class FakeProcess:
    def __init__(self) -> None:
        self.running = True
        self.signals: list[int] = []

    def poll(self) -> int | None:
        return None if self.running else 0

    def send_signal(self, value: int) -> None:
        self.signals.append(value)
        self.running = False

    def wait(self, timeout: float | None = None) -> int:
        self.running = False
        return 0


class FakeFollowClient:
    def __init__(self) -> None:
        self.requests: list[bool] = []
        self.closed = False

    def set_enabled(self, enabled: bool) -> bool:
        self.requests.append(enabled)
        return True

    def close(self) -> None:
        self.closed = True


class MobilityTest(unittest.TestCase):
    def test_person_follow_process_uses_real_safety_backends(self) -> None:
        calls: list[tuple[list[str], Path | None]] = []
        process = FakeProcess()

        def factory(command: list[str], *, cwd: Path | None) -> FakeProcess:
            calls.append((command, cwd))
            return process

        controller = PersonFollowProcessController(
            process_factory=factory,
            working_directory=Path("/home/shofukus/buddy"),
        )

        self.assertTrue(controller.start())
        self.assertTrue(controller.active)
        self.assertFalse(controller.start())
        command, cwd = calls[0]
        self.assertEqual(cwd, Path("/home/shofukus/buddy"))
        self.assertIn("robot.person_follow_cli", command)
        self.assertIn("gpiozero", command)
        self.assertIn("vl53l1x", command)
        self.assertEqual(command[command.index("--duration") + 1], "0")
        self.assertEqual(command[command.index("--stop-distance") + 1], "60.0")

        self.assertTrue(controller.stop())
        self.assertEqual(process.signals, [signal.SIGINT])
        self.assertFalse(controller.active)
        self.assertFalse(controller.stop())

    def test_ros2_follow_controller_calls_enable_service(self) -> None:
        client = FakeFollowClient()
        controller = Ros2FollowController(client)

        self.assertTrue(controller.start())
        self.assertTrue(controller.active)
        self.assertFalse(controller.start())
        self.assertTrue(controller.stop())
        self.assertFalse(controller.active)
        self.assertFalse(controller.stop())
        self.assertEqual(client.requests, [True, False])

        controller.close()
        self.assertTrue(client.closed)
