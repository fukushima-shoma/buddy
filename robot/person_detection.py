from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


def save_annotated_image(output: Path, image: Any) -> None:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required to save the result image.") from exc

    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), image):
        raise RuntimeError(f"Could not write image: {output}")
