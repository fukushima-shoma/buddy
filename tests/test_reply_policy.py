import pytest

from robot.conversation import get_reply_instructions
from robot.reply_policy import apply_reply_policy, choose_reply_policy


@pytest.mark.parametrize("text", [
    "車の物語を話して", "お話して", "お話ししてほしい", "おはなしきかせて",
    "赤い車のお話", "昔話を読んで", "ストーリーを作って", "童話が聞きたい", "物語を語って",
    "魚のお話したい。", "お話ししたい", "動物のお話がしたい", "楽しくお話をして。",
])
def test_explicit_story_requests_get_complete_story_policy(text):
    policy = choose_reply_policy(text)
    assert policy.mode == "story"
    instructions = apply_reply_policy(get_reply_instructions(True), policy)
    assert "20〜25文字" not in instructions
    assert "180〜260文字" in instructions
    assert "安心できる結末" in instructions
    assert "個人情報" in instructions
    assert policy.realtime_tokens > 512


@pytest.mark.parametrize("text", ["こんにちは", "赤い車だよ", "お話ししよう", "物語って何", "物語はいらない",
                                 "お話したくない", "物語を聞きたくない", "お話してほしくない",
                                 "お話したい気分じゃない"])
def test_normal_conversation_remains_short(text):
    policy = choose_reply_policy(text)
    assert policy.mode == "conversation"
    assert apply_reply_policy(get_reply_instructions(True), policy) == get_reply_instructions(True)


@pytest.mark.parametrize("text", ["続き", "続きを聞かせて", "つづけて", "もっと", "もっと長く", "それから？", "お話の続き"])
def test_story_continuations_require_previous_story(text):
    assert choose_reply_policy(text).mode == "conversation"
    assert choose_reply_policy(text, story_active=True).mode == "story"
