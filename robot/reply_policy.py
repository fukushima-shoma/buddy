"""Use a complete story when requested, keeping ordinary turns short."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class ReplyPolicy:
    mode: str
    realtime_tokens: int
    pipeline_tokens: int
    audio_seconds: int


CONVERSATION_POLICY = ReplyPolicy("conversation", 512, 64, 30)
STORY_POLICY = ReplyPolicy("story", 4096, 1024, 90)
_STORY_NOUN = r"(?:物語|お話|おはなし|ストーリー|童話|昔話|むかし話|むかしばなし|おとぎ話)"
_STORY_ACTION = r"(?:して|したい|聞かせて|きかせて|話して|はなして|語って|かたって|読んで|よんで|作って|つくって|聞きたい|ききたい|お願い|おねがい)"
_STORY_DECLINE = r"(?:したくない|聞きたくない|ききたくない|してほしくない|いらない|したい気分じゃない)"
_CONTINUE = re.compile(
    r"^(?:続き(?:を(?:聞かせて|話して))?|つづき(?:をきかせて)?|続けて|つづけて|"
    r"もっと(?:長く|ながく|聞かせて|きかせて|話して)?|もう少し(?:長く|聞かせて)?|"
    r"長くして|ながくして|そのあと(?:は)?|それから(?:は)?)[。.!！?？]*$"
)
STORY_INSTRUCTIONS = """\
今回の返答は、子どもが頼んだ物語です。
180〜260文字、6〜10文を目安に、始まり、小さな出来事、安心できる結末のある物語を
そのまま語ってください。題材や登場人物は子どもの希望を拾ってください。
「お話しするね」だけで終えず、題材を選ぶ質問を挟まず、最初の文から物語を始めてください。
短い文を自然な間でつなぎ、声色や抑揚に小さな変化をつけてください。
怖すぎる展開や長い説教は避け、末尾で毎回質問しないでください。
続きを頼まれた場合は直前の物語を引き継ぎ、その部分にも小さな結末をつけてください。
元の物語が文脈にない場合は覚えているふりをせず、新しいお話として始めてください。
"""


def choose_reply_policy(text: str, *, story_active: bool = False) -> ReplyPolicy:
    compact = "".join(unicodedata.normalize("NFKC", text).split())
    noun = re.search(_STORY_NOUN, compact)
    if noun and re.search(_STORY_DECLINE, compact[noun.end():]):
        return CONVERSATION_POLICY
    if noun and (re.search(_STORY_ACTION, compact[noun.end():])
                 or re.search(_STORY_NOUN + r"[。.!！?？]*$", compact)):
        return STORY_POLICY
    if story_active and noun and re.fullmatch(r"の?(?:続き|つづき)[。.!！?？]*$", compact[noun.end():]):
        return STORY_POLICY
    if story_active and _CONTINUE.fullmatch(compact):
        return STORY_POLICY
    return CONVERSATION_POLICY


def apply_reply_policy(instructions: str, policy: ReplyPolicy) -> str:
    if policy.mode != "story":
        return instructions
    return instructions + "\n" + STORY_INSTRUCTIONS
