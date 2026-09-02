---
name: buddy-calibration
description: Guide and record Buddy drivetrain and IMU calibration using encoder ticks, wheel geometry, straight-line and turn trials. Use after the required parts are installed and mock tests pass; do not move hardware without explicit authorization.
---

# Buddy calibration

Calibration is a measured experiment, not a guessed constant change. Read `docs/phase5.md` and inspect the current parameter declarations before proposing edits.

## Workflow

1. Record date, hardware revision, firmware/software commit, battery state, surface, payload, and measurement method.
2. Determine encoder ticks per wheel revolution from multiple slow manual or raised-wheel trials. Preserve raw counts and note whether decoding is single, double, or quadrature-edge counting.
3. Measure effective wheel diameter from traveled distance over multiple revolutions rather than relying only on nominal diameter.
4. Measure left/right wheel center distance and use it as the initial track width.
5. With explicit movement authorization and the hardware-test motor gate satisfied, run repeated low-speed 1 m straight trials. Record commanded and actual distance plus lateral deviation.
6. Run repeated bounded 90-degree turns and record actual angle. Adjust effective track width only from repeatable error.
7. Calibrate the IMU according to its device procedure, preserving raw bias/scale results and temperature where available.
8. Change one parameter group at a time, rerun the relevant test, and keep before/after values with units.
9. Update the appropriate Phase 5 documentation and parameter defaults only after results are repeatable. Run unit and ROS mock tests after code changes.

Do not fabricate missing measurements or infer physical verification from simulations. Report uncertainty, trial count, mean error, spread, final values, changed files, and any values still provisional.
