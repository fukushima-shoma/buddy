from __future__ import annotations

from pathlib import Path
import signal
import subprocess
import sys
from typing import Any, Callable


class PersonFollowProcessController:
    """Start and stop the existing person-follow loop as a child process."""

    def __init__(
        self,
        *,
        speed: float = 1.0,
        stop_distance: float = 60.0,
        resume_distance: float = 70.0,
        turn_pulse: float = 0.08,
        process_factory: Callable[..., Any] = subprocess.Popen,
        working_directory: Path | None = None,
    ) -> None:
        self.speed = speed
        self.stop_distance = stop_distance
        self.resume_distance = resume_distance
        self.turn_pulse = turn_pulse
        self._process_factory = process_factory
        self._working_directory = working_directory
        self._process: Any | None = None

    @property
    def active(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> bool:
        if self.active:
            return False
        command = [
            sys.executable,
            "-m",
            "robot.person_follow_cli",
            "--backend",
            "gpiozero",
            "--distance-backend",
            "vl53l1x",
            "--duration",
            "0",
            "--speed",
            str(self.speed),
            "--turn-speed",
            str(self.speed),
            "--max-speed",
            str(self.speed),
            "--stop-distance",
            str(self.stop_distance),
            "--resume-distance",
            str(self.resume_distance),
            "--turn-pulse",
            str(self.turn_pulse),
        ]
        try:
            self._process = self._process_factory(
                command,
                cwd=self._working_directory,
            )
        except OSError as exc:
            raise RuntimeError("Could not start person following.") from exc
        return True

    def stop(self) -> bool:
        process = self._process
        if process is None or process.poll() is not None:
            self._process = None
            return False
        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            self._process = None
            return False
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self._process = None
        return True

    def close(self) -> None:
        self.stop()
