# Phase1 Wiring

This wiring plan is for a TB6612FNG dual motor driver and a 2WD chassis.

Do not power the motors until the real module labels have been checked.

## Power

| Source | Connects to | Notes |
| --- | --- | --- |
| Raspberry Pi USB-C | Raspberry Pi | Pi power only |
| Motor battery box + | TB6612 VM / m◊otor power | Motor power only |
| Motor battery box - | TB6612 GND | Must share ground with Pi |
| Raspberry Pi GND | TB6612 GND | Common signal reference |
| Raspberry Pi 3.3V | TB6612 VCC / logic power | Logic power only |

Never connect the motor battery box to the Raspberry Pi 5V pin.

## GPIO Plan

| TB6612FNG pin | Raspberry Pi GPIO | Purpose |
| --- | --- | --- |
| PWMA | GPIO 12 | Left motor PWM |
| AIN1 | GPIO 5 | Left motor direction |
| AIN2 | GPIO 6 | Left motor direction |
| PWMB | GPIO 13 | Right motor PWM |
| BIN1 | GPIO 20 | Right motor direction |
| BIN2 | GPIO 21 | Right motor direction |
| STBY | GPIO 26 | Driver standby |

## Motor Outputs

| TB6612FNG pin | Connects to |
| --- | --- |
| A01 / AO1 | Left motor wire 1 |
| A02 / AO2 | Left motor wire 2 |
| B01 / BO1 | Right motor wire 1 |
| B02 / BO2 | Right motor wire 2 |

If a motor spins in the opposite direction, swap that motor's two output wires or adjust the code after confirming both wheels.

## Pre-Power Checklist

- [ ] Motor battery box switch is OFF
- [ ] Raspberry Pi is powered separately by USB-C
- [ ] Pi 5V is not connected to motor power
- [ ] Pi GND and TB6612 GND are connected
- [ ] TB6612 VM is connected to motor battery +
- [ ] TB6612 VCC is connected to Pi 3.3V
- [ ] Left motor is on A output
- [ ] Right motor is on B output
- [ ] No loose wire is touching another pin
