from __future__ import annotations

from pathlib import Path
import time
from typing import Callable, Protocol


class CameraDevice(Protocol):
    def start(self) -> None:
        """Start the configured camera."""

    def capture_file(self, output: Path) -> None:
        """Capture one image to output."""

    def close(self) -> None:
        """Release camera resources."""


def capture_still(
    camera: CameraDevice,
    output: Path,
    warmup: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        camera.start()
        sleep(max(0.0, warmup))
        camera.capture_file(output)
    finally:
        camera.close()

    return output


class MockCamera:
    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.captured: list[Path] = []

    def start(self) -> None:
        self.started = True

    def capture_file(self, output: Path) -> None:
        self.captured.append(output)

    def close(self) -> None:
        self.closed = True
