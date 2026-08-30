from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from robot.power import RaspberryPiPowerStatus


@dataclass(frozen=True)
class PowerState:
    power_ok: bool
    under_voltage: bool
    under_voltage_occurred: bool
    raw: int
    error: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)


def power_state_from_status(status: RaspberryPiPowerStatus) -> PowerState:
    return PowerState(
        power_ok=not status.under_voltage,
        under_voltage=status.under_voltage,
        under_voltage_occurred=status.under_voltage_occurred,
        raw=status.raw,
    )
