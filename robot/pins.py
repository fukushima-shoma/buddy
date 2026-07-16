from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tb6612Pins:
    left_pwm: int = 12
    left_in1: int = 5
    left_in2: int = 6
    right_pwm: int = 13
    right_in1: int = 20
    right_in2: int = 21
    standby: int = 26


DEFAULT_TB6612_PINS = Tb6612Pins()
