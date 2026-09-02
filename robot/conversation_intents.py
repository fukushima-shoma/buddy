from __future__ import annotations

import unicodedata


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

DEFAULT_FAREWELL_REPLY = "バイバイ。またお話ししようね。"
DEFAULT_INACTIVITY_REPLY = "お話はおしまいかな。またお話ししようね。"
MOBILITY_START_REPLY = "いまから、ついていくね。動き始めるよ。"
MOBILITY_CONFIRM_REPLY = "ついていってもいい？ いいときは、はい、と言ってね。"
MOBILITY_CONFIRM_AGAIN_REPLY = "ついていってもいい？ はい、か、やめる、で教えてね。"
MOBILITY_CANCEL_REPLY = "わかったよ。動かないね。"
MOBILITY_CLARIFY_REPLY = "どう動いたらいいかわからないから、いまは動かないよ。"
MOBILITY_ALREADY_RUNNING_REPLY = "もう、ついていっているよ。"
MOBILITY_STOP_REPLY = "止まったよ。もう動かないよ。"
MOBILITY_ALREADY_STOPPED_REPLY = "いまは止まっているよ。"
MOBILITY_FAREWELL_REPLY = "止まったよ。バイバイ。またお話ししようね。"
MOBILITY_UNAVAILABLE_REPLY = "ごめんね、今は動けないよ。"
POWER_LOW_REPLY = "電源が弱くなっているから、安全のために止まるね。"
POWER_GOOD_REPLY = "電源は大丈夫だよ。"
POWER_UNAVAILABLE_REPLY = "電源を確認できないから、安全のために動かないね。"


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
