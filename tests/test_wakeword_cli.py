from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.wakeword_cli import build_parser, train_wake_word


class WakeWordCliTest(unittest.TestCase):
    def test_defaults_train_japanese_raspberry_pi_phrase(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.phrase, "ねえ バディ")
        self.assertEqual(args.language, "ja")
        self.assertEqual(args.platform, "raspberry-pi")

    def test_training_uses_access_key_without_logging_it(self) -> None:
        calls: list[tuple[object, ...]] = []

        with TemporaryDirectory() as directory:
            output = Path(directory) / "models" / "buddy.ppn"
            result = train_wake_word(
                phrase="ねえ バディ",
                language="ja",
                platform="raspberry-pi",
                output=output,
                access_key="secret",
                trainer=lambda *args: calls.append(args),
            )

            self.assertEqual(result, output.resolve())
            self.assertEqual(
                calls,
                [
                    (
                        "secret",
                        str(output.resolve()),
                        "ja",
                        "ねえ バディ",
                        "raspberry-pi",
                    )
                ],
            )

    def test_empty_phrase_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "phrase"):
            train_wake_word(
                phrase=" ",
                language="ja",
                platform="raspberry-pi",
                output=Path("unused.ppn"),
                access_key="secret",
                trainer=lambda *args: None,
            )


if __name__ == "__main__":
    unittest.main()
