---
name: buddy-diagnostics
description: Collect and interpret read-only health information for the Buddy robot on macOS or Raspberry Pi, including services, logs, ROS 2, resources, peripherals, and Git. Use for troubleshooting or health checks; do not use it to repair or reconfigure the system.
---

# Buddy diagnostics

Run diagnostics without changing services, files, packages, devices, or Git state.

## Workflow

1. Read `docs/commands.md` and the phase document relevant to the symptom.
2. Run `scripts/collect_buddy_diagnostics.sh`. It continues past missing platform tools so one report works on macOS and Raspberry Pi.
3. For continuous Raspberry Pi resource monitoring, run `scripts/monitor_buddy_resources.sh`. Check total CPU, load average, `free -h`, top CPU processes, temperature, and the raw throttling/undervoltage flags together.
4. For deeper service output, run `scripts/check_buddy_services.sh`. For ROS graph details, run `scripts/check_ros2_topics.sh`.
5. Separate observations from conclusions. Quote the failing command or key output and state whether the check ran on macOS, Raspberry Pi, or an unknown host.
6. Redact tokens, credentials, personal conversation data, and recorded audio paths before sharing a report.
7. Recommend the smallest next diagnostic or repair. Do not apply a repair unless the user asks.

Treat an unavailable command as `not available`, not as a failed component. Do not use `sudo`, restart services, publish ROS messages, activate motors, record audio, capture images, or run network calls in this skill.
