from __future__ import annotations

import json
from math import isfinite
from typing import Any, Iterable

from buddy_ros.follow_control import FollowCoordinator
from buddy_ros.odometry_control import EncoderOdometry
from buddy_ros.person_control import PersonTarget


def _scenario_target(position: str, detected: bool) -> PersonTarget:
    if position not in {"left", "center", "right", "not-found"}:
        raise ValueError("person position must be left, center, right, or not-found")
    if not detected:
        position = "not-found"
    return PersonTarget(
        status="detected" if detected else "not-found",
        detected=detected,
        position=position,
        confidence=1.0 if detected else 0.0,
        center_x=320 if detected else 0,
        center_y=240 if detected else 0,
        x=220 if detected else 0,
        y=80 if detected else 0,
        width=200 if detected else 0,
        height=320 if detected else 0,
        image_width=640,
        image_height=480,
    )


class ScenarioRunner:
    """Replay numeric sensor events through hardware-free Buddy logic."""

    def __init__(
        self,
        *,
        follow: FollowCoordinator,
        odometry: EncoderOdometry,
    ) -> None:
        self.follow = follow
        self.odometry = odometry
        self._last_timestamp: float | None = None

    def apply(self, event: dict[str, Any]) -> dict[str, Any]:
        try:
            timestamp = float(event["at"])
            event_type = str(event["type"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("scenario event requires numeric at and string type") from exc
        if not isfinite(timestamp):
            raise ValueError("scenario timestamp must be finite")
        if self._last_timestamp is not None and timestamp < self._last_timestamp:
            raise ValueError("scenario timestamps must not go backwards")

        if event_type == "enable":
            self.follow.set_enabled(bool(event.get("enabled", True)))
        elif event_type == "person":
            detected = bool(event.get("detected", True))
            position = str(event.get("position", "not-found"))
            self.follow.update_target(
                _scenario_target(position, detected),
                measured_at=timestamp,
            )
        elif event_type == "distance":
            distance_m = float(event["meters"])
            if not isfinite(distance_m) or distance_m < 0:
                raise ValueError("distance meters must be finite and 0 or greater")
            self.follow.update_distance(distance_m, measured_at=timestamp)
        elif event_type == "power":
            self.follow.update_power(
                bool(event["good"]),
                measured_at=timestamp,
            )
        elif event_type == "encoder":
            self.odometry.update(
                int(event["left"]),
                int(event["right"]),
                timestamp=timestamp,
            )
        elif event_type != "sample":
            raise ValueError(f"unknown scenario event type: {event_type}")

        self._last_timestamp = timestamp
        command = self.follow.command(now=timestamp)
        pose = self.odometry.pose
        return {
            "at": timestamp,
            "event": event_type,
            "follow": {
                "action": command.action,
                "angular_z": command.angular_z,
                "linear_x": command.linear_x,
                "reason": command.reason,
            },
            "pose": {"x": pose.x, "y": pose.y, "yaw": pose.yaw},
        }


def replay_json_lines(
    lines: Iterable[str],
    runner: ScenarioRunner,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("event must be a JSON object")
            results.append(runner.apply(event))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid scenario line {line_number}: {exc}") from exc
    return results
