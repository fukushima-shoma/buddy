from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from robot.buddy_identity import BUDDY_FAREWELL_REPLY, BUDDY_INACTIVITY_REPLY


FAREWELL_PHRASES = frozenset(
    {
        "バイバイ",
        "ばいばい",
        "じゃあバイバイ",
        "バイバイまたね",
        "またね",
        "さようなら",
        "さよなら",
        "おしまい",
        "お話おしまい",
    }
)
MOBILITY_START_PHRASES = frozenset({"ついてきて", "ついて来て"})
MOBILITY_STOP_PHRASES = frozenset({"止まって", "とまって", "ストップ"})
MOBILITY_CONFIRM_PHRASES = frozenset({"はい", "いいよ", "お願い", "おねがい"})
MOBILITY_CANCEL_PHRASES = frozenset(
    {"いいえ", "やめて", "やめる", "キャンセル", "取り消し", "とりけし"}
)
AMBIGUOUS_MOBILITY_PHRASES = frozenset(
    {"動いて", "うごいて", "進んで", "すすんで", "こっちに来て", "こっちきて"}
)
POWER_STATUS_PHRASES = frozenset(
    {"電池大丈夫", "電池は大丈夫", "バッテリー大丈夫", "バッテリーは大丈夫"}
)
REPEAT_REPLY_PHRASES = frozenset(
    {"もう一回言って", "もう一度言って", "もう一回", "もう一度", "なんて言った"}
)

CHILD_RETRY_REPLIES = (
    "ごめんね、よく聞こえなかったよ。もう一度、ゆっくり話してくれる？",
    "うまく聞き取れないみたい。近くの大人と一緒に、もう一度試してね。",
)
DEFAULT_RETRY_REPLIES = (
    "ごめんね、うまく聞き取れなかったよ。もう一度言ってくれる？",
    "あれ、聞き逃しちゃった。もう一回お願いしてもいい？",
    "ゆっくりで大丈夫だよ。もう一度聞かせてね。",
)
DEFAULT_FAREWELL_REPLY = BUDDY_FAREWELL_REPLY
DEFAULT_INACTIVITY_REPLY = BUDDY_INACTIVITY_REPLY
MOBILITY_START_REPLY = "いまから、ついていくね。動き始めるよ。"
MOBILITY_CONFIRM_REPLY = "ついていってもいい？ いいときは、はい、と言ってね。"
MOBILITY_CONFIRM_AGAIN_REPLY = "ついていってもいい？ はい、か、やめる、で教えてね。"
MOBILITY_CANCEL_REPLY = "わかったよ。動かないね。"
MOBILITY_CLARIFY_REPLY = "どう動いたらいいかわからないから、いまは動かないよ。"
MOBILITY_ALREADY_RUNNING_REPLY = "もう、ついていっているよ。"
MOBILITY_STOP_REPLY = "止まったよ。もう動かないよ。"
MOBILITY_ALREADY_STOPPED_REPLY = "いまは止まっているよ。"
MOBILITY_FAREWELL_REPLY = (
    "止まったよ。バイバイ、ぼくのタイヤもひと休みするね。"
)
MOBILITY_UNAVAILABLE_REPLY = "ごめんね、今は動けないよ。"
POWER_LOW_REPLY = "電源が弱くなっているから、安全のために止まるね。"
POWER_GOOD_REPLY = "電源は大丈夫だよ。"
POWER_UNAVAILABLE_REPLY = "電源を確認できないから、安全のために動かないね。"
NOTHING_TO_REPEAT_REPLY = "まだ繰り返せるお話がないよ。"

LOCAL_SHORT_REPLY_PHRASES = {
    "greeting": frozenset({"こんにちは", "おはよう", "こんばんは", "やあ"}),
    "thanks": frozenset({"ありがとう", "ありがと", "どうも"}),
    "correction": frozenset({"ちがう", "違う", "ちがうよ", "そうじゃない"}),
    "uncertain": frozenset(
        {"わからない", "わかんない", "わかんないよ", "知らない", "しらない"}
    ),
    "change-play": frozenset(
        {"別の遊び", "べつの遊び", "ほかの遊び", "他の遊び", "違う遊び"}
    ),
    "success": frozenset({"できた", "できたよ", "やった", "やったよ"}),
    "fun": frozenset(
        {"楽しい", "たのしい", "楽しいね", "おもしろい", "面白い"}
    ),
}

LOCAL_SHORT_REPLIES = {
    "greeting": (
        "こんにちは。ぼくはBuddyだよ。",
        "やあ。ぼくのタイヤも起きたよ。",
        "こんにちは。今日も話せてうれしいな。",
    ),
    "thanks": (
        "どういたしまして。ぼくもうれしいよ。",
        "えへへ、ありがとう。",
        "ありがとう。タイヤが弾む気分だよ。",
    ),
    "correction": (
        "そっか、ちがったね。教えてくれてありがとう。",
        "わかったよ。ちゃんと直すね。",
        "了解。ぼくのタイヤも向きを変えるね。",
    ),
    "uncertain": (
        "だいじょうぶ。いっしょに考えよう。",
        "わからなくても平気だよ。",
        "ぼくも考えるよ。ゆっくりでいいよ。",
    ),
    "change-play": (
        "いいよ。こんどは何して遊ぶ？",
        "切り替えよう。どの遊びにする？",
        "オーケー。ぼくのタイヤも気分転換。",
    ),
    "success": (
        "できたんだね。やったあ。",
        "すごい。ぼくもくるんと喜んだよ。",
        "やったね。ぼくもうれしいよ。",
    ),
    "fun": (
        "楽しいね。ぼくのタイヤも弾みそう。",
        "おもしろいね。もっと聞きたいな。",
        "ぼくも楽しくなってきたよ。",
    ),
}


@dataclass(frozen=True)
class LocalShortReply:
    intent: str
    text: str


class LocalShortReplyController:
    """Handle safe exact short phrases without waiting for a reply model."""

    def __init__(self) -> None:
        self._next_by_intent: dict[str, int] = {}

    def reply(self, transcript: str) -> LocalShortReply | None:
        normalized = normalize_exact_phrase(transcript)
        for intent, phrases in LOCAL_SHORT_REPLY_PHRASES.items():
            if normalized not in phrases:
                continue
            choices = LOCAL_SHORT_REPLIES[intent]
            index = self._next_by_intent.get(intent, 0)
            self._next_by_intent[intent] = (index + 1) % len(choices)
            return LocalShortReply(intent, choices[index])
        return None


def normalize_exact_phrase(transcript: str) -> str:
    """Normalize punctuation and width without allowing partial commands."""
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", transcript).casefold()
        if character.isalnum()
    )


def _matches(transcript: str, phrases: frozenset[str]) -> bool:
    return normalize_exact_phrase(transcript) in phrases


def is_farewell_transcript(transcript: str) -> bool:
    return _matches(transcript, FAREWELL_PHRASES)


def is_mobility_start_transcript(transcript: str) -> bool:
    return _matches(transcript, MOBILITY_START_PHRASES)


def is_mobility_stop_transcript(transcript: str) -> bool:
    return _matches(transcript, MOBILITY_STOP_PHRASES)


def is_mobility_confirm_transcript(transcript: str) -> bool:
    return _matches(transcript, MOBILITY_CONFIRM_PHRASES)


def is_mobility_cancel_transcript(transcript: str) -> bool:
    return _matches(transcript, MOBILITY_CANCEL_PHRASES)


def is_ambiguous_mobility_transcript(transcript: str) -> bool:
    return _matches(transcript, AMBIGUOUS_MOBILITY_PHRASES)


def is_power_status_transcript(transcript: str) -> bool:
    return _matches(transcript, POWER_STATUS_PHRASES)


def is_repeat_reply_transcript(transcript: str) -> bool:
    return _matches(transcript, REPEAT_REPLY_PHRASES)
