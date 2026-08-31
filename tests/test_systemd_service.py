from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SystemdServiceTest(unittest.TestCase):
    def test_service_starts_safe_wake_word_conversation(self) -> None:
        service = (ROOT / "infra/buddy-conversation.service").read_text(
            encoding="utf-8"
        )

        self.assertIn("User=shofukus", service)
        self.assertIn("EnvironmentFile=/home/shofukus/buddy/.env", service)
        self.assertIn("--start-trigger wakeword", service)
        self.assertIn("--auto-conversation-memory", service)
        self.assertIn("--mobility-backend ros2-follow", service)
        self.assertIn("--mobility-stop-distance 60", service)
        self.assertIn("--power-monitor raspberry-pi", service)
        self.assertIn("--child-games", service)
        self.assertIn("--child-mode", service)
        self.assertIn("--audio-device plughw:CARD=Plus,DEV=0", service)
        self.assertNotIn("--orientation-backend gpiozero", service)
        self.assertNotIn("-m robot.person_follow_cli", service)
        self.assertIn("Restart=on-failure", service)
        self.assertIn("buddy-ros-follow.service", service)
        self.assertIn("stop_buddy_ros_follow.sh", service)

    def test_ros_follow_service_starts_real_backends_disabled(self) -> None:
        service = (ROOT / "infra/buddy-ros-follow.service").read_text(
            encoding="utf-8"
        )
        runner = (ROOT / "scripts/run_buddy_ros_follow.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("run_buddy_ros_follow.sh", service)
        self.assertIn("motor_backend:=gpiozero", runner)
        self.assertIn("distance_backend:=vl53l1x", runner)
        self.assertIn("person_backend:=mediapipe", runner)
        self.assertIn("power_backend:=raspberry_pi", runner)
        self.assertNotIn("/follow/enable", runner)

    def test_ros_wrappers_do_not_enable_nounset_before_ros_setup(self) -> None:
        for name in (
            "run_buddy_conversation_ros2.sh",
            "run_buddy_ros_follow.sh",
            "stop_buddy_ros_follow.sh",
        ):
            script = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertNotIn("set -u", script)
            self.assertNotIn("set -euo", script)

    def test_installer_checks_private_runtime_files_before_enabling(self) -> None:
        installer = (ROOT / "scripts/install_buddy_service.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('"$buddy_dir/.env"', installer)
        self.assertIn('"$buddy_dir/.venv/bin/python"', installer)
        self.assertIn("person_detection_mediapipe_2023mar.onnx", installer)
        self.assertIn("OPENAI_API_KEY is missing or empty", installer)
        self.assertIn('chmod 600 "$buddy_dir/.env"', installer)
        self.assertIn('systemctl enable "$follow_service"', installer)
        self.assertIn('systemctl restart "$follow_service"', installer)
        self.assertIn('systemctl restart "$conversation_service"', installer)
