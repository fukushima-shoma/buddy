from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from typing import Callable


@dataclass(frozen=True)
class RaspberryPiPowerStatus:
    under_voltage: bool
    under_voltage_occurred: bool
    raw: int


class RaspberryPiPowerMonitor:
    """Read Raspberry Pi firmware undervoltage flags using vcgencmd."""

    def __init__(
        self,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._runner = runner

    def read(self) -> RaspberryPiPowerStatus:
        try:
            result = self._runner(
                ["vcgencmd", "get_throttled"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("Could not read Raspberry Pi power status.") from exc
        match = re.fullmatch(r"\s*throttled=0x([0-9a-fA-F]+)\s*", result.stdout)
        if match is None:
            raise RuntimeError("Unexpected vcgencmd get_throttled output.")
        raw = int(match.group(1), 16)
        return RaspberryPiPowerStatus(
            under_voltage=bool(raw & (1 << 0)),
            under_voltage_occurred=bool(raw & (1 << 16)),
            raw=raw,
        )

    def is_power_good(self) -> bool:
        return not self.read().under_voltage
