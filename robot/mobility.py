from __future__ import annotations

from pathlib import Path
import signal
import subprocess
import sys
from typing import Any, Callable


class FollowEnableClient:
    """Small synchronous client for Buddy's ROS 2 follow enable service."""

    def __init__(self, service_name: str = "/follow/enable") -> None:
        try:
            import rclpy
            from std_srvs.srv import SetBool
        except ImportError as exc:
            raise RuntimeError(
                "ROS 2 Python packages are required. Source "
                "~/buddy/scripts/source_ros2.sh first."
            ) from exc

        self._rclpy = rclpy
        self._set_bool = SetBool
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init(args=[])
        self._node = rclpy.create_node("buddy_conversation_mobility")
        self._client = self._node.create_client(SetBool, service_name)

    def set_enabled(self, enabled: bool) -> bool:
        if not self._client.wait_for_service(timeout_sec=3.0):
            raise RuntimeError("ROS 2 follow service is unavailable.")
        request = self._set_bool.Request()
        request.data = enabled
        future = self._client.call_async(request)
        self._rclpy.spin_until_future_complete(
            self._node,
            future,
            timeout_sec=5.0,
        )
        if not future.done() or future.result() is None:
            raise RuntimeError("ROS 2 follow service did not respond.")
        return bool(future.result().success)

    def close(self) -> None:
        self._node.destroy_node()
        if self._owns_context and self._rclpy.ok():
            self._rclpy.shutdown()


class Ros2FollowController:
    """Start and stop the already-running ROS 2 follow coordinator."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def _service_client(self) -> Any:
        if self._client is None:
            self._client = FollowEnableClient()
        return self._client

    def start(self) -> bool:
        if self._active:
            return False
        if not self._service_client().set_enabled(True):
            raise RuntimeError("Could not enable ROS 2 person following.")
        self._active = True
        return True

    def stop(self) -> bool:
        if not self._active:
            return False
        if not self._service_client().set_enabled(False):
            raise RuntimeError("Could not stop ROS 2 person following.")
        self._active = False
        return True

    def close(self) -> None:
        try:
            self.stop()
        finally:
            close = getattr(self._client, "close", None)
            if callable(close):
                close()


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
