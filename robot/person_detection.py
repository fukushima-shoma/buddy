from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import importlib.util
from pathlib import Path
from statistics import median
from typing import Any

from robot.color_detection import horizontal_position


@dataclass(frozen=True)
class PersonDetection:
    confidence: float
    center_x: int
    center_y: int
    x: int
    y: int
    width: int
    height: int
    position: str


class PersonDetectionStabilizer:
    """Confirm, retain, and position-smooth detections across video frames."""

    def __init__(
        self,
        image_width: int,
        confirm_frames: int = 2,
        lost_frame_tolerance: int = 1,
        position_window: int = 3,
    ) -> None:
        self._image_width = max(1, image_width)
        self._confirm_frames = max(1, confirm_frames)
        self._lost_frame_tolerance = max(0, lost_frame_tolerance)
        self._centers: deque[int] = deque(maxlen=max(1, position_window))
        self._consecutive_detections = 0
        self._missed_frames = 0
        self._locked = False
        self._last_detection: PersonDetection | None = None

    def update(
        self,
        detection: PersonDetection | None,
    ) -> tuple[PersonDetection | None, bool]:
        """Return the stable detection and whether acquisition is in progress."""
        if detection is None:
            self._consecutive_detections = 0
            if self._locked and self._last_detection is not None:
                self._missed_frames += 1
                if self._missed_frames <= self._lost_frame_tolerance:
                    return self._last_detection, False
            self._reset()
            return None, False

        self._missed_frames = 0
        self._consecutive_detections += 1
        self._centers.append(detection.center_x)
        self._last_detection = detection
        if not self._locked and self._consecutive_detections < self._confirm_frames:
            return None, True

        self._locked = True
        sorted_centers = sorted(self._centers)
        center_x = sorted_centers[len(sorted_centers) // 2]
        stable = PersonDetection(
            confidence=detection.confidence,
            center_x=center_x,
            center_y=detection.center_y,
            x=detection.x,
            y=detection.y,
            width=detection.width,
            height=detection.height,
            position=horizontal_position(center_x, self._image_width),
        )
        self._last_detection = stable
        return stable, False

    def _reset(self) -> None:
        self._locked = False
        self._missed_frames = 0
        self._last_detection = None
        self._centers.clear()


class PersonAreaLatch:
    """Smooth and latch visual proximity without reacting to one bad box."""

    def __init__(
        self,
        stop_area: float = 180000.0,
        resume_area: float = 140000.0,
        window_size: int = 3,
        stop_confirm_frames: int = 2,
        resume_confirm_frames: int = 3,
    ) -> None:
        self.stop_area = max(0.0, stop_area)
        self.resume_area = min(self.stop_area, max(0.0, resume_area))
        self.stop_confirm_frames = max(1, stop_confirm_frames)
        self.resume_confirm_frames = max(1, resume_confirm_frames)
        self._areas: deque[float] = deque(maxlen=max(1, window_size))
        self._stop_frames = 0
        self._resume_frames = 0
        self.latched = False

    def update(
        self,
        detection: PersonDetection | None,
    ) -> tuple[bool, float | None]:
        if detection is None:
            return self.latched, None

        self._areas.append(float(detection.width * detection.height))
        filtered_area = float(median(self._areas))
        if self.stop_area <= 0:
            self.latched = False
            return False, filtered_area
        if not self.latched:
            if filtered_area >= self.stop_area:
                self._stop_frames += 1
                if self._stop_frames >= self.stop_confirm_frames:
                    self.latched = True
                    self._stop_frames = 0
            else:
                self._stop_frames = 0
            return self.latched, filtered_area

        if filtered_area <= self.resume_area:
            self._resume_frames += 1
            if self._resume_frames >= self.resume_confirm_frames:
                self.latched = False
                self._resume_frames = 0
        else:
            self._resume_frames = 0
        return self.latched, filtered_area


def select_person_detection(
    candidates: list[tuple[int, int, int, int, float]],
    image_width: int,
    min_confidence: float,
) -> PersonDetection | None:
    eligible = [candidate for candidate in candidates if candidate[4] >= min_confidence]
    if not eligible:
        return None

    x, y, width, height, confidence = max(
        eligible,
        key=lambda candidate: (candidate[4], candidate[2] * candidate[3]),
    )
    center_x = x + width // 2
    center_y = y + height // 2
    return PersonDetection(
        confidence=float(confidence),
        center_x=center_x,
        center_y=center_y,
        x=x,
        y=y,
        width=width,
        height=height,
        position=horizontal_position(center_x, image_width),
    )


class HogPersonDetector:
    """OpenCV's built-in HOG full-body detector; no model download required."""

    def __init__(self, min_confidence: float = 0.2, scale: float = 1.05) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required. Install it with: "
                "sudo apt install -y python3-opencv opencv-data"
            ) from exc

        self._cv2 = cv2
        self._min_confidence = max(0.0, min_confidence)
        self._scale = max(1.01, scale)
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, image: Any) -> tuple[PersonDetection | None, Any]:
        rectangles, weights = self._hog.detectMultiScale(
            image,
            hitThreshold=0.0,
            winStride=(8, 8),
            padding=(8, 8),
            scale=self._scale,
        )
        candidates = [
            (int(x), int(y), int(width), int(height), float(weight))
            for (x, y, width, height), weight in zip(rectangles, weights)
        ]
        detection = select_person_detection(
            candidates,
            image.shape[1],
            self._min_confidence,
        )

        annotated = image.copy()
        if detection is not None:
            cv2 = self._cv2
            cv2.rectangle(
                annotated,
                (detection.x, detection.y),
                (detection.x + detection.width, detection.y + detection.height),
                (0, 255, 255),
                3,
            )
            cv2.putText(
                annotated,
                f"person {detection.position} confidence={detection.confidence:.2f}",
                (detection.x, max(30, detection.y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
            )
        return detection, annotated


def mediapipe_result_to_detection(
    result: Any,
    image_width: int,
    image_height: int,
) -> PersonDetection:
    """Convert an OpenCV Zoo MP-PersonDet row to Buddy's detection format."""
    hip_x, hip_y = float(result[4]), float(result[5])
    body_x, body_y = float(result[6]), float(result[7])
    radius = max(1.0, ((hip_x - body_x) ** 2 + (hip_y - body_y) ** 2) ** 0.5)
    x1 = max(0, int(hip_x - radius))
    y1 = max(0, int(hip_y - radius))
    x2 = min(image_width, int(hip_x + radius))
    y2 = min(image_height, int(hip_y + radius))
    center_x = max(0, min(image_width - 1, int(hip_x)))
    center_y = max(0, min(image_height - 1, int(hip_y)))
    return PersonDetection(
        confidence=float(result[-1]),
        center_x=center_x,
        center_y=center_y,
        x=x1,
        y=y1,
        width=max(1, x2 - x1),
        height=max(1, y2 - y1),
        position=horizontal_position(center_x, image_width),
    )


class MediaPipePersonDetector:
    """OpenCV Zoo's lightweight MediaPipe person detector."""

    def __init__(
        self,
        model_path: Path,
        helper_path: Path,
        min_confidence: float = 0.5,
    ) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required. Install it with: "
                "sudo apt install -y python3-opencv opencv-data"
            ) from exc

        model_path = model_path.expanduser()
        helper_path = helper_path.expanduser()
        if not model_path.is_file() or not helper_path.is_file():
            raise RuntimeError(
                "MediaPipe person model is not installed. Run: "
                "bash scripts/install_person_model.sh"
            )

        spec = importlib.util.spec_from_file_location(
            "buddy_opencv_zoo_mp_persondet",
            helper_path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load person detector helper: {helper_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self._cv2 = cv2
        self._detector = module.MPPersonDet(
            modelPath=str(model_path),
            scoreThreshold=max(0.0, min_confidence),
        )

    def detect(self, image: Any) -> tuple[PersonDetection | None, Any]:
        results = self._detector.infer(image)
        detections = [
            mediapipe_result_to_detection(row, image.shape[1], image.shape[0])
            for row in results
        ]
        detection = max(detections, key=lambda item: item.confidence, default=None)
        annotated = image.copy()
        if detection is not None:
            cv2 = self._cv2
            cv2.rectangle(
                annotated,
                (detection.x, detection.y),
                (detection.x + detection.width, detection.y + detection.height),
                (0, 255, 0),
                3,
            )
            cv2.circle(
                annotated,
                (detection.center_x, detection.center_y),
                5,
                (0, 0, 255),
                -1,
            )
            cv2.putText(
                annotated,
                f"person {detection.position} confidence={detection.confidence:.2f}",
                (detection.x, max(30, detection.y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
        return detection, annotated


def save_annotated_image(output: Path, image: Any) -> None:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required to save the result image.") from exc

    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), image):
        raise RuntimeError(f"Could not write image: {output}")
