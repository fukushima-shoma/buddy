from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from buddy_ros.person_control import person_target_from_detection
from robot.person_detection import (
    HOG_DEFAULT_CONFIDENCE,
    MEDIAPIPE_DEFAULT_CONFIDENCE,
    HogPersonDetector,
    MediaPipePersonDetector,
    PersonDetection,
    PersonDetectionStabilizer,
)
from robot.picamera2_driver import Picamera2FrameSource


class PersonDetector(Protocol):
    def detect(self, image: Any) -> tuple[PersonDetection | None, Any]: ...


def create_detector(
    backend: str,
    *,
    min_confidence: float | None = None,
    hog_scale: float = 1.05,
    model_path: Path | None = None,
    helper_path: Path | None = None,
) -> PersonDetector:
    if backend == "hog":
        return HogPersonDetector(
            min_confidence=(
                HOG_DEFAULT_CONFIDENCE
                if min_confidence is None
                else min_confidence
            ),
            scale=hog_scale,
        )
    if backend == "mediapipe":
        if model_path is None or helper_path is None:
            raise ValueError("MediaPipe model and helper paths are required.")
        return MediaPipePersonDetector(
            model_path=model_path,
            helper_path=helper_path,
            min_confidence=(
                MEDIAPIPE_DEFAULT_CONFIDENCE
                if min_confidence is None
                else min_confidence
            ),
        )
    raise ValueError(f"Unsupported person backend: {backend}")


def create_person_node_class() -> type[Any]:
    """Create the node lazily so core tests do not require ROS 2."""
    try:
        from rclpy.node import Node
        from std_msgs.msg import String
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the Buddy ROS 2 "
            "environment before starting person_node."
        ) from exc

    class BuddyPersonNode(Node):
        def __init__(self) -> None:
            super().__init__("buddy_person")
            default_model_dir = Path.home() / "buddy/models/person_detection"
            self.declare_parameter("backend", "mock")
            self.declare_parameter("width", 640)
            self.declare_parameter("height", 480)
            self.declare_parameter("fps", 5.0)
            self.declare_parameter("min_confidence", -1.0)
            self.declare_parameter("hog_scale", 1.05)
            self.declare_parameter(
                "model_path",
                str(default_model_dir / "person_detection_mediapipe_2023mar.onnx"),
            )
            self.declare_parameter(
                "helper_path",
                str(default_model_dir / "mp_persondet.py"),
            )
            self.declare_parameter("confirm_window", 3)
            self.declare_parameter("confirm_hits", 2)
            self.declare_parameter("confirm_max_shift", 160)
            self.declare_parameter("lost_frame_tolerance", 1)
            self.declare_parameter("position_window", 3)
            self.declare_parameter("mock_position", "center")
            self.declare_parameter("mock_confidence", 0.9)

            self.backend = str(self.get_parameter("backend").value)
            self.width = max(1, int(self.get_parameter("width").value))
            self.height = max(1, int(self.get_parameter("height").value))
            fps = max(0.1, float(self.get_parameter("fps").value))
            self.publisher = self.create_publisher(String, "/person/target", 10)
            self.source: Picamera2FrameSource | None = None
            self.detector: PersonDetector | None = None
            self.stabilizer: PersonDetectionStabilizer | None = None

            if self.backend != "mock":
                configured_confidence = float(
                    self.get_parameter("min_confidence").value
                )
                self.detector = create_detector(
                    self.backend,
                    min_confidence=(
                        None if configured_confidence < 0 else configured_confidence
                    ),
                    hog_scale=float(self.get_parameter("hog_scale").value),
                    model_path=Path(str(self.get_parameter("model_path").value)),
                    helper_path=Path(str(self.get_parameter("helper_path").value)),
                )
                self.source = Picamera2FrameSource(
                    width=self.width,
                    height=self.height,
                )
                self.stabilizer = PersonDetectionStabilizer(
                    image_width=self.width,
                    confirm_window=int(self.get_parameter("confirm_window").value),
                    confirm_hits=int(self.get_parameter("confirm_hits").value),
                    confirm_max_shift=int(
                        self.get_parameter("confirm_max_shift").value
                    ),
                    lost_frame_tolerance=int(
                        self.get_parameter("lost_frame_tolerance").value
                    ),
                    position_window=int(
                        self.get_parameter("position_window").value
                    ),
                )
                self.source.start()

            self.timer = self.create_timer(1.0 / fps, self._publish)
            self.get_logger().info(
                f"person ready backend={self.backend} topic=/person/target "
                f"rate={fps:.1f}Hz"
            )

        def _publish(self) -> None:
            if self.backend == "mock":
                detection = self._mock_detection()
                confirming = False
            else:
                assert self.source is not None
                assert self.detector is not None
                assert self.stabilizer is not None
                frame = self.source.capture_array()
                measured, _ = self.detector.detect(frame)
                detection, confirming = self.stabilizer.update(measured)

            target = person_target_from_detection(
                detection,
                image_width=self.width,
                image_height=self.height,
                confirming=confirming,
            )
            message = String()
            message.data = target.to_json()
            self.publisher.publish(message)

        def _mock_detection(self) -> PersonDetection:
            position = str(self.get_parameter("mock_position").value)
            center_by_position = {
                "left": self.width // 6,
                "center": self.width // 2,
                "right": self.width * 5 // 6,
            }
            if position not in center_by_position:
                raise ValueError("mock_position must be left, center, or right.")
            center_x = center_by_position[position]
            width = max(1, self.width // 4)
            height = max(1, self.height // 2)
            return PersonDetection(
                confidence=float(self.get_parameter("mock_confidence").value),
                center_x=center_x,
                center_y=self.height // 2,
                x=max(0, center_x - width // 2),
                y=self.height // 4,
                width=width,
                height=height,
                position=position,
            )

        def destroy_node(self) -> None:
            if self.source is not None:
                self.source.close()
            super().destroy_node()

    return BuddyPersonNode


def main(args: list[str] | None = None) -> None:
    try:
        import rclpy
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python packages are required. Source the Buddy ROS 2 environment."
        ) from exc

    node_class = create_person_node_class()
    rclpy.init(args=args)
    node = node_class()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
