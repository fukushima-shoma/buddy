import json
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from robot.conversation_display import ConversationDisplay, ConversationEventSinks
from robot.conversation_loop_cli import build_parser, main, run_conversation_loop
from robot.conversation_state import ConversationEvent, ConversationPhase, ConversationReaction
from robot.audio import MockAudioRecorder, MockAudioPlayer
from robot.conversation import MockReplyGenerator
from robot.speech import MockSpeechSynthesizer
from robot.transcription import MockTranscriber


@pytest.fixture
def display():
    screen = ConversationDisplay(port=0)
    try:
        yield screen
    finally:
        screen.close()


def test_http_exposes_display_data_and_static_page(display):
    url = f"http://127.0.0.1:{display.address[1]}"
    display(ConversationEvent(ConversationPhase.LISTENING, ConversationReaction.WARM,
                              "private transcript must not be published"))
    with urlopen(url + "/api/state", timeout=2) as response:
        assert json.load(response) == {"phase": "listening", "revision": 1, "transcript": None}
        assert response.headers["Cache-Control"] == "no-store"
        assert "Access-Control-Allow-Origin" not in response.headers
    with urlopen(url, timeout=2) as response:
        page = response.read().decode("utf-8")
        assert all(label in page for label in ["話していいよ", "ちょっと待ってね", "ぼくがお話し中"])
        assert "https://" not in page
    for path in ["/.env", "/../.env", "/captures/audio/input.wav"]:
        with pytest.raises(HTTPError) as error:
            urlopen(url + path, timeout=2)
        assert error.value.code == 404


def test_display_cannot_change_state_over_http(display):
    from urllib.request import Request
    url = f"http://127.0.0.1:{display.address[1]}/api/state"
    with pytest.raises(HTTPError) as error:
        urlopen(Request(url, data=b'{"phase":"listening"}'), timeout=2)
    assert error.value.code == 405
    assert display.snapshot()["phase"] == "waiting"


def test_transcription_and_playback_have_correct_display_phase(tmp_path, display):
    class Recorder(MockAudioRecorder):
        def record(self, *args, **kwargs):
            assert display.snapshot()["phase"] == "listening"
            return super().record(*args, **kwargs)

    class Transcriber(MockTranscriber):
        def transcribe(self, *args, **kwargs):
            assert display.snapshot()["phase"] == "thinking"
            return super().transcribe(*args, **kwargs)

    class Player(MockAudioPlayer):
        def play(self, *args, **kwargs):
            assert display.snapshot()["phase"] == "speaking"
            assert display.snapshot()["transcript"] == "こんにちは"
            return super().play(*args, **kwargs)

    run_conversation_loop(
        recorder=Recorder(), transcriber=Transcriber("こんにちは"),
        reply_generator=MockReplyGenerator("やあ"), synthesizer=MockSpeechSynthesizer(),
        player=Player(), input_path=tmp_path / "input.wav",
        speech_output=tmp_path / "reply.wav", duration=0.1, sample_rate=16000,
        language="ja", turns=1, pause=0, on_conversation_event=display,
        on_transcript=display.update_transcript,
        output=lambda _: None,
    )
    assert display.snapshot()["phase"] == "stopped"
    assert display.snapshot()["transcript"] is None


@pytest.mark.parametrize("phase", [ConversationPhase.WAITING, ConversationPhase.LISTENING,
                                  ConversationPhase.STOPPED])
def test_transcript_clears_on_next_recording_or_session_end(display, phase):
    display(ConversationEvent(ConversationPhase.THINKING, ConversationReaction.CURIOUS, "recording-ended"))
    display.update_transcript("赤い車のお話して")
    display(ConversationEvent(ConversationPhase.SPEAKING, ConversationReaction.WARM, "reply"))
    assert display.snapshot()["transcript"] == "赤い車のお話して"
    display(ConversationEvent(phase, ConversationReaction.CALM, "next-state"))
    assert display.snapshot()["transcript"] is None
    if phase != ConversationPhase.LISTENING:
        display.update_transcript("late transcript")
        assert display.snapshot()["transcript"] is None


def test_http_transcript_is_current_utterance_without_event_details(display):
    text = '<script>alert("車")</script>'
    display(ConversationEvent(ConversationPhase.THINKING, ConversationReaction.CURIOUS, "private reason"))
    display.update_transcript(text)
    url = f"http://127.0.0.1:{display.address[1]}/api/state"
    with urlopen(url, timeout=2) as response:
        assert json.load(response) == {"phase": "thinking", "revision": 2, "transcript": text}
    display.update_transcript(None)
    assert display.snapshot()["transcript"] is None


def test_stop_command_stops_before_transcript_display_update(tmp_path):
    ordered = []
    run_conversation_loop(
        recorder=MockAudioRecorder(), transcriber=MockTranscriber("止まって"),
        reply_generator=MockReplyGenerator(), synthesizer=MockSpeechSynthesizer(),
        player=MockAudioPlayer(), input_path=tmp_path / "input.wav",
        speech_output=tmp_path / "reply.wav", duration=0.1, sample_rate=16000,
        language="ja", turns=1, pause=0,
        stop_mobility=lambda: ordered.append("stop") or True,
        on_transcript=lambda text: ordered.append(text), output=lambda _: None,
    )
    assert ordered == ["stop", "止まって"]


def test_failure_does_not_leave_listening_display(tmp_path, display):
    class Recorder(MockAudioRecorder):
        def record(self, *args, **kwargs):
            raise RuntimeError("capture failed")

    with pytest.raises(RuntimeError, match="capture failed"):
        run_conversation_loop(
            recorder=Recorder(), transcriber=MockTranscriber("hello"),
            reply_generator=MockReplyGenerator(), synthesizer=MockSpeechSynthesizer(),
            player=MockAudioPlayer(), input_path=tmp_path / "input.wav",
            speech_output=tmp_path / "reply.wav", duration=0.1, sample_rate=16000,
            language="ja", turns=1, pause=0, on_conversation_event=display,
        )
    assert display.snapshot()["phase"] == "stopped"


def test_fanout_preserves_ros_events_and_closes_display_even_if_ros_close_fails():
    received = []

    class Sink:
        def __call__(self, event):
            received.append(event)

        def close(self):
            raise RuntimeError("ros close failed")

    class Screen:
        closed = False

        def __call__(self, event):
            received.append(event)

        def close(self):
            self.closed = True

    screen = Screen()
    sinks = ConversationEventSinks(Sink(), screen)
    event = ConversationEvent(ConversationPhase.SPEAKING, ConversationReaction.WARM, "reply")
    sinks(event)
    assert received == [event, event]
    with pytest.raises(RuntimeError):
        sinks.close()
    assert screen.closed


def test_display_bind_failure_does_not_stop_mock_conversation(tmp_path, monkeypatch, capsys):
    def unavailable(*args, **kwargs):
        raise OSError("port in use")

    monkeypatch.setattr("robot.conversation_display.ConversationDisplay", unavailable)
    monkeypatch.setattr("sys.argv", ["conversation-loop", "--conversation-display",
        "--turns", "1", "--duration", "0.1", "--pause", "0",
        "--input", str(tmp_path / "input.wav"), "--speech-output", str(tmp_path / "reply.wav")])
    assert main() == 0
    assert "conversation-display=unavailable" in capsys.readouterr().out


def test_display_is_opt_in_and_defaults_to_localhost():
    args = build_parser().parse_args([])
    assert not args.conversation_display
    assert args.conversation_display_host == "127.0.0.1"
    assert args.conversation_display_port == 8765
