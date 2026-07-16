from __future__ import annotations

from robot.motor import MAX_SPEED, _clamp
from robot.pins import DEFAULT_TB6612_PINS, Tb6612Pins


class Tb6612GpioDriver:
    """TB6612FNG motor backend using gpiozero.

    Do not run this until the real wiring has been checked.
    """

    def __init__(self, pins: Tb6612Pins = DEFAULT_TB6612_PINS) -> None:
        try:
            from gpiozero import DigitalOutputDevice, PWMOutputDevice
        except ImportError as exc:
            raise RuntimeError(
                "gpiozero is required for --backend gpiozero. "
                "Install it on the Raspberry Pi after wiring is confirmed."
            ) from exc

        self.left_pwm = PWMOutputDevice(pins.left_pwm, initial_value=0.0)
        self.left_in1 = DigitalOutputDevice(pins.left_in1, initial_value=False)
        self.left_in2 = DigitalOutputDevice(pins.left_in2, initial_value=False)
        self.right_pwm = PWMOutputDevice(pins.right_pwm, initial_value=0.0)
        self.right_in1 = DigitalOutputDevice(pins.right_in1, initial_value=False)
        self.right_in2 = DigitalOutputDevice(pins.right_in2, initial_value=False)
        self.standby = DigitalOutputDevice(pins.standby, initial_value=True)

    def set_left(self, speed: float) -> None:
        self._set_motor(speed, self.left_pwm, self.left_in1, self.left_in2)

    def set_right(self, speed: float) -> None:
        self._set_motor(speed, self.right_pwm, self.right_in1, self.right_in2)

    def stop(self) -> None:
        self.left_pwm.value = 0.0
        self.right_pwm.value = 0.0
        self.left_in1.off()
        self.left_in2.off()
        self.right_in1.off()
        self.right_in2.off()

    def close(self) -> None:
        self.stop()
        self.standby.off()
        self.left_pwm.close()
        self.left_in1.close()
        self.left_in2.close()
        self.right_pwm.close()
        self.right_in1.close()
        self.right_in2.close()
        self.standby.close()

    def _set_motor(self, speed: float, pwm: object, in1: object, in2: object) -> None:
        value = _clamp(speed, -MAX_SPEED, MAX_SPEED)

        if value > 0:
            in1.on()
            in2.off()
        elif value < 0:
            in1.off()
            in2.on()
        else:
            in1.off()
            in2.off()

        pwm.value = abs(value)
