from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from robot.person_detection import PersonDetection


@dataclass(frozen=True)
class PersonTarget:
    status: str
    detected: bool
    position: str
    confidence: float
    center_x: int
    center_y: int
    x: int
    y: int
    width: int
    height: int
    image_width: int
    image_height: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "PersonTarget":
        values = json.loads(payload)
        if not isinstance(values, dict):
            raise ValueError("Person target must be a JSON object.")
        try:
            return cls(
                status=str(values["status"]),
                detected=bool(values["detected"]),
                position=str(values["position"]),
                confidence=float(values["confidence"]),
                center_x=int(values["center_x"]),
                center_y=int(values["center_y"]),
                x=int(values["x"]),
                y=int(values["y"]),
                width=int(values["width"]),
                height=int(values["height"]),
                image_width=max(1, int(values["image_width"])),
                image_height=max(1, int(values["image_height"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid person target payload.") from exc


def person_target_from_detection(
    detection: PersonDetection | None,
    *,
    image_width: int,
    image_height: int,
    confirming: bool = False,
) -> PersonTarget:
    if detection is None:
        return PersonTarget(
            status="confirming" if confirming else "not-found",
            detected=False,
            position="not-found",
            confidence=0.0,
            center_x=0,
            center_y=0,
            x=0,
            y=0,
            width=0,
            height=0,
            image_width=max(1, image_width),
            image_height=max(1, image_height),
        )
    return PersonTarget(
        status="detected",
        detected=True,
        position=detection.position,
        confidence=detection.confidence,
        center_x=detection.center_x,
        center_y=detection.center_y,
        x=detection.x,
        y=detection.y,
        width=detection.width,
        height=detection.height,
        image_width=max(1, image_width),
        image_height=max(1, image_height),
    )
