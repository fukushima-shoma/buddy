import json
import unittest

from buddy_ros.power_control import power_state_from_status
from buddy_ros.power_node import create_monitor
from robot.power import RaspberryPiPowerStatus


class RosPowerControlTest(unittest.TestCase):
    def test_current_undervoltage_marks_power_bad(self) -> None:
        state = power_state_from_status(
            RaspberryPiPowerStatus(
                under_voltage=True,
                under_voltage_occurred=True,
                raw=0x10001,
            )
        )
        payload = json.loads(state.to_json())

        self.assertFalse(state.power_ok)
        self.assertTrue(payload["under_voltage"])
        self.assertEqual(payload["raw"], 0x10001)

    def test_historical_flag_does_not_mark_current_power_bad(self) -> None:
        state = power_state_from_status(
            RaspberryPiPowerStatus(
                under_voltage=False,
                under_voltage_occurred=True,
                raw=0x10000,
            )
        )

        self.assertTrue(state.power_ok)

    def test_mock_monitor_can_simulate_low_power(self) -> None:
        status = create_monitor("mock", mock_power_good=False).read()

        self.assertTrue(status.under_voltage)

    def test_unknown_power_backend_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_monitor("unknown")


if __name__ == "__main__":
    unittest.main()
