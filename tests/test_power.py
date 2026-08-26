from __future__ import annotations

import subprocess
import unittest

from robot.power import RaspberryPiPowerMonitor


class PowerTest(unittest.TestCase):
    def test_reads_current_and_historical_undervoltage_flags(self) -> None:
        outputs = iter(["throttled=0x0\n", "throttled=0x10001\n"])

        def runner(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            self.assertEqual(command, ["vcgencmd", "get_throttled"])
            self.assertEqual(
                kwargs,
                {"check": True, "capture_output": True, "text": True},
            )
            return subprocess.CompletedProcess(command, 0, stdout=next(outputs))

        monitor = RaspberryPiPowerMonitor(runner=runner)

        good = monitor.read()
        low = monitor.read()

        self.assertFalse(good.under_voltage)
        self.assertTrue(low.under_voltage)
        self.assertTrue(low.under_voltage_occurred)

    def test_invalid_firmware_output_is_rejected(self) -> None:
        def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 0, stdout="unknown")

        with self.assertRaisesRegex(RuntimeError, "Unexpected"):
            RaspberryPiPowerMonitor(runner=runner).read()
