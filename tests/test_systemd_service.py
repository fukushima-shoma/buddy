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
        self.assertIn("--child-mode", service)
        self.assertIn("--audio-device plughw:CARD=Plus,DEV=0", service)
        self.assertNotIn("--orientation-backend gpiozero", service)
        self.assertIn("Restart=on-failure", service)

    def test_installer_checks_private_runtime_files_before_enabling(self) -> None:
        installer = (ROOT / "scripts/install_buddy_service.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('"$buddy_dir/.env"', installer)
        self.assertIn('"$buddy_dir/.venv/bin/python"', installer)
        self.assertIn("OPENAI_API_KEY is missing or empty", installer)
        self.assertIn('chmod 600 "$buddy_dir/.env"', installer)
        self.assertIn("systemctl enable --now", installer)
