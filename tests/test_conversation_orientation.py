from __future__ import annotations

from dataclasses import replace
import unittest

from robot.conversation_orientation import orient_to_person
from robot.motor import BuddyDrive, MockMotorDriver
from robot.person_detection import PersonDetection


class FakeSource:
    def __init__(self) -> None:
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def capture_array(self) -> object:
        return object()

    def close(self) -> None:
        self.closed = True


class FakeDetector:
    def __init__(self, detections: list[PersonDetection | None]) -> None:
        self.detections = iter(detections)

    def detect(self, frame: object) -> tuple[PersonDetection | None, object]:
        return next(self.detections), frame


def detection(position: str) -> PersonDetection:
    base = PersonDetection(0.9, 100, 200, 50, 50, 100, 200, "left")
    return replace(base, position=position)


class ConversationOrientationTest(unittest.TestCase):
    def test_turns_in_short_pulse_then_stops_when_centered(self) -> None:
        source = FakeSource()
        driver = MockMotorDriver()
        pauses: list[float] = []
        logs: list[str] = []

        result = orient_to_person(
            source=source,
            detector=FakeDetector([detection("left"), detection("center")]),
            drive=BuddyDrive(driver, max_speed=1.0),
            pulse=0.1,
            output=logs.append,
            sleeper=pauses.append,
        )

        self.assertEqual(result, "center")
        self.assertIn("left=1.00", driver.events)
        self.assertIn("right=-1.00", driver.events)
        self.assertEqual(driver.left_speed, 0)
        self.assertTrue(source.started)
        self.assertTrue(source.closed)
        self.assertEqual(pauses, [0.1, 0.15])

    def test_missing_person_never_turns(self) -> None:
        source = FakeSource()
        driver = MockMotorDriver()

        result = orient_to_person(
            source=source,
            detector=FakeDetector([None]),
            drive=BuddyDrive(driver),
            output=lambda _: None,
        )

        self.assertEqual(result, "not-found")
        self.assertFalse(any(event.startswith("left=") for event in driver.events))
        self.assertEqual(driver.left_speed, 0)
        self.assertTrue(source.closed)
