from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tb6612Pins:
    left_pwm: int = 18
    left_in1: int = 23
    left_in2: int = 24
    right_pwm: int = 13
    right_in1: int = 5
    right_in2: int = 6
    standby: int = 22


DEFAULT_TB6612_PINS = Tb6612Pins()
