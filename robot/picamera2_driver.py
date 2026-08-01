from __future__ import annotations

from pathlib import Path


class Picamera2Device:
    """Raspberry Pi Camera backend using Picamera2."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        try:
            from libcamera import controls
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "Picamera2 is required. Install it with: "
                "sudo apt install -y python3-picamera2 --no-install-recommends"
            ) from exc

        self._camera = Picamera2()
        configuration = self._camera.create_still_configuration(
            main={"size": (max(1, width), max(1, height))}
        )
        self._camera.configure(configuration)
        self._camera.set_controls({"AfMode": controls.AfModeEnum.Continuous})

    def start(self) -> None:
        self._camera.start()

    def capture_file(self, output: Path) -> None:
        self._camera.capture_file(str(output))

    def close(self) -> None:
        self._camera.close()
