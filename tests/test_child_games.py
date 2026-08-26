import unittest

from robot.child_games import ChildGameController, is_game_end_transcript


class ChildGamesTest(unittest.TestCase):
    def test_animal_quiz_handles_answer_repeat_and_end(self) -> None:
        game = ChildGameController()

        start = game.handle("どうぶつクイズ")
        repeat = game.handle("もう一回")
        correct = game.handle("ぞうだと思う")
        end = game.handle("おしまい")

        self.assertTrue(start and "お鼻が長くて" in start)
        self.assertTrue(repeat and "もう一回言うね" in repeat)
        self.assertTrue(correct and "せいかい" in correct)
        self.assertEqual(end, "ゲームはおしまい。また遊ぼうね。")
        self.assertFalse(game.active)

    def test_inactive_game_does_not_consume_normal_conversation(self) -> None:
        game = ChildGameController()

        self.assertIsNone(game.handle("今日は何して遊ぶ？"))
        self.assertTrue(is_game_end_transcript("ゲーム、おしまい。"))
