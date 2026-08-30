from __future__ import annotations


class Vl53l1xDistanceSensor:
    """VL53L1X distance sensor using Adafruit CircuitPython on Linux."""

    def __init__(self, distance_mode: int = 2, timing_budget_ms: int = 100) -> None:
        try:
            import adafruit_vl53l1x
            import board
        except ImportError as exc:
            raise RuntimeError(
                "VL53L1X dependencies are required. Activate .venv and run: "
                "python -m pip install adafruit-circuitpython-vl53l1x. "
                "For ROS 2, source ~/buddy/scripts/source_ros2.sh first."
            ) from exc

        self._i2c = board.I2C()
        self._sensor = adafruit_vl53l1x.VL53L1X(self._i2c)
        self._sensor.distance_mode = 1 if distance_mode == 1 else 2
        self._sensor.timing_budget = max(20, timing_budget_ms)
        self._started = False

    def start(self) -> None:
        self._sensor.start_ranging()
        self._started = True

    def read_distance_cm(self) -> float | None:
        if not self._sensor.data_ready:
            return None
        distance = self._sensor.distance
        self._sensor.clear_interrupt()
        return None if distance is None else float(distance)

    def close(self) -> None:
        if self._started:
            self._sensor.stop_ranging()
            self._started = False
        deinit = getattr(self._i2c, "deinit", None)
        if callable(deinit):
            deinit()
