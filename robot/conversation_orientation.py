from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol
import time

from robot.motor import BuddyDrive
from robot.person_detection import PersonDetection


class FrameSource(Protocol):
    def start(self) -> None: ...
    def capture_array(self) -> Any: ...
    def close(self) -> None: ...


class PersonDetector(Protocol):
    def detect(self, frame: Any) -> tuple[PersonDetection | None, Any]: ...


def orient_to_person(
    *,
    source: FrameSource,
    detector: PersonDetector,
    drive: BuddyDrive,
    attempts: int = 4,
    speed: float = 1.0,
    pulse: float = 0.12,
    output: Callable[[str], None] = print,
    sleeper: Callable[[float], None] = time.sleep,
) -> str:
    """Make a few bounded in-place corrections before conversation starts."""
    attempts = max(1, attempts)
    source.start()
    try:
        for _ in range(attempts):
            detection, _ = detector.detect(source.capture_array())
            if detection is None:
                output("orientation=stop reason=person-not-found")
                return "not-found"
            if detection.position == "center":
                output("orientation=stop reason=person-centered")
                return "center"
            action = detection.position
            if action == "left":
                drive.left(speed)
            elif action == "right":
                drive.right(speed)
            else:
                output("orientation=stop reason=unknown-position")
                return "not-found"
            output(f"orientation={action} reason=aligning")
            sleeper(max(0.0, pulse))
            drive.stop()
            sleeper(0.15)
        output("orientation=stop reason=attempt-limit")
        return "attempt-limit"
    finally:
        drive.stop()
        drive.close()
        source.close()
