from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HsvRange:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]


@dataclass(frozen=True)
class ColorDetection:
    color: str
    area: float
    center_x: int
    center_y: int
    x: int
    y: int
    width: int
    height: int
    position: str


HSV_RANGES = {
    "red": (
        # Keep the hue range narrow and require vivid pixels so brown wood in
        # Buddy's operating environment is not mistaken for a red target.
        HsvRange((0, 160, 100), (7, 255, 255)),
        HsvRange((173, 160, 100), (179, 255, 255)),
    ),
    "green": (HsvRange((35, 80, 60), (85, 255, 255)),),
    "blue": (HsvRange((90, 80, 60), (135, 255, 255)),),
}


def horizontal_position(center_x: int, image_width: int, deadzone: float = 0.15) -> str:
    midpoint = image_width / 2
    margin = max(0.0, min(deadzone, 0.5)) * image_width
    if center_x < midpoint - margin:
        return "left"
    if center_x > midpoint + margin:
        return "right"
    return "center"


def detect_largest_color(
    input_path: Path,
    output_path: Path,
    color: str,
    min_area: float = 1000.0,
) -> ColorDetection | None:
    cv2, _ = _opencv()

    image = cv2.imread(str(input_path))
    if image is None:
        raise RuntimeError(f"Could not read image: {input_path}")

    detection, annotated = detect_color_frame(image, color, min_area=min_area)

    output_path = output_path.expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), annotated):
        raise RuntimeError(f"Could not write image: {output_path}")

    return detection


def detect_color_frame(
    image: Any,
    color: str,
    min_area: float = 1000.0,
) -> tuple[ColorDetection | None, Any]:
    cv2, np = _opencv()
    ranges = HSV_RANGES.get(color)
    if ranges is None:
        raise ValueError(f"Unsupported color: {color}")

    annotated = image.copy()
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask: Any = None
    for hsv_range in ranges:
        partial = cv2.inRange(
            hsv,
            np.array(hsv_range.lower, dtype=np.uint8),
            np.array(hsv_range.upper, dtype=np.uint8),
        )
        mask = partial if mask is None else cv2.bitwise_or(mask, partial)

    kernel = np.ones((5, 5), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detection = None
    if contours:
        contour = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(contour))
        if area >= max(0.0, min_area):
            x, y, width, height = cv2.boundingRect(contour)
            center_x = x + width // 2
            center_y = y + height // 2
            detection = ColorDetection(
                color=color,
                area=area,
                center_x=center_x,
                center_y=center_y,
                x=x,
                y=y,
                width=width,
                height=height,
                position=horizontal_position(center_x, image.shape[1]),
            )
            cv2.rectangle(
                annotated, (x, y), (x + width, y + height), (0, 255, 255), 3
            )
            cv2.circle(annotated, (center_x, center_y), 6, (255, 255, 255), -1)
            cv2.putText(
                annotated,
                f"{color} {detection.position} area={area:.0f}",
                (x, max(30, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
            )

    return detection, annotated


def _opencv() -> tuple[Any, Any]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required. Install it with: "
            "sudo apt install -y python3-opencv opencv-data"
        ) from exc
    return cv2, np
