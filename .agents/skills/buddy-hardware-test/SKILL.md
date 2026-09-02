---
name: buddy-hardware-test
description: Test Buddy camera, distance sensor, microphone, speaker, and motors in a staged safety order on confirmed hardware. Use for physical-device verification; require explicit user authorization immediately before any motor movement.
---

# Buddy hardware test

Confirm the target Raspberry Pi and attached components before accessing devices. Read `docs/commands.md` and the phase document for each component.

## Test order

1. Collect read-only host and peripheral status with `scripts/collect_buddy_diagnostics.sh`.
2. Camera: enumerate first, then perform one still capture only when requested. Do not start continuous capture by default.
3. Distance sensor: confirm I2C visibility, then take bounded stationary readings. Do not move the robot in response.
4. Microphone: enumerate devices, then record a short bounded sample with the user aware that recording is occurring.
5. Speaker: generate or use a non-sensitive test tone, start at low volume, and warn nearby people before playback.
6. Motors: stop and request explicit confirmation that names the target and test. Confirmation for other hardware does not authorize motors.

## Motor gate

Before movement, require all of the following: wheels raised clear of the floor, stable chassis, clear area, known stop command, healthy power status, correct pin mapping, and no competing GPIO process. Begin at the lowest practical speed for a bounded duration, issue stop in cleanup even after errors, and test one direction/action at a time. Never leave a motor command running while waiting for input.

Report what was physically observed separately from command output. Stop on undervoltage, overheating, unexpected direction, sensor inconsistency, device contention, or loss of control.
