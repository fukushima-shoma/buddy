from robot.conversation_metrics_cli import summarize
import pytest


def test_metrics_separate_paths_and_do_not_include_private_text():
    result = summarize([
        "turn=1 timing=recording-to-playback seconds=1.0 realtime=true",
        "turn=2 timing=recording-to-playback seconds=3.0 realtime=true",
        "turn=3 timing=recording-to-playback seconds=4.0",
        "turn=4 timing=recording-to-playback seconds=0.2 local=true",
        "turn=4 transcript=private-child-text",
        "turn=5 realtime=fallback stage=connect",
        "turn=5 realtime=reply reply-chars=20 interrupted=true",
    ])
    assert result["timings"]["recording-to-playback:realtime"]["median"] == 2.0
    assert result["timings"]["recording-to-playback:realtime"]["p90"] == 3.0
    assert result["timings"]["recording-to-playback:pipeline"]["count"] == 1
    assert result["timings"]["recording-to-playback:local"]["count"] == 1
    assert result["realtime_fallback_events"] == 1
    assert result["realtime_interrupted_replies"] == 1
    assert "private-child-text" not in str(result)


def test_metrics_ignore_spoken_log_words_and_support_legacy_local_turns():
    result = summarize([
        "turn=1 transcript=timing=recording-to-playback seconds=999 realtime=fallback",
        "turn=1 timing=reply seconds=0.000 local=true",
        "turn=1 timing=recording-to-playback seconds=0.5 streaming=true",
        "turn=2 timing=recording-to-playback seconds=0.3 path=control",
        "turn=3 timing=reply seconds=1.2",
        "turn=3 timing=recording-to-playback seconds=2.0 path=pipeline",
    ])
    assert result["timings"]["recording-to-playback:local"]["count"] == 1
    assert result["timings"]["recording-to-playback:control"]["count"] == 1
    assert result["timings"]["recording-to-playback:pipeline"]["mean"] == 2.0
    assert result["realtime_fallback_events"] == 0


def test_metrics_count_input_cutoffs_and_story_modes_without_spoken_text():
    result = summarize([
        "turn=1 input-end=semantic captured-seconds=6.1 silence-seconds=0.7",
        "turn=1 realtime=reply reply-chars=210 reply-mode=story interrupted=false",
        "turn=2 input-end=duration-limit captured-seconds=20.0 silence-seconds=0.1",
        "turn=2 realtime=reply reply-chars=22 reply-mode=conversation interrupted=true",
        "turn=3 input-end=silence captured-seconds=3.0 silence-seconds=1.4",
        "turn=3 transcript=input-end=duration-limit",
        "turn=4 input-end=semantic-silence-watchdog captured-seconds=3.1 silence-seconds=3.0",
    ])
    assert result["input_ends"] == {"semantic": 1, "duration-limit": 1, "silence": 1,
                                    "semantic-silence-watchdog": 1}
    assert result["reply_modes"] == {"story": 1, "conversation": 1}


def test_metrics_count_realtime_input_attempts_and_safe_failure_reasons():
    result = summarize([
        "turn=1 realtime=input result=success failure=none uploaded-bytes=12000 manual-commit=false server-committed=true events=committed,transcribed",
        "turn=2 realtime=input result=fallback failure=timeout uploaded-bytes=14000 manual-commit=true server-committed=false events=none",
        "turn=3 realtime=input result=fallback failure=transcription-audio_unintelligible uploaded-bytes=16000 manual-commit=false server-committed=true events=committed,transcription-failed",
        "turn=4 transcript=realtime=input result=fallback failure=private",
    ])
    assert result["realtime_inputs"] == {
        "attempts": 3, "successes": 1, "failures": 2,
        "failure_reasons": {"timeout": 1, "transcription-audio_unintelligible": 1},
    }
    assert "private" not in str(result)


def test_estimated_wait_pairs_each_turn_before_calculating_statistics():
    lines = []
    for turn, (silence, playback) in enumerate([(0, 10), (10, 0), (0, 0)], 1):
        lines.extend([
            f"turn={turn} input-end=semantic captured-seconds=12 silence-seconds={silence}",
            f"turn={turn} timing=recording-to-playback seconds={playback} realtime=true",
        ])
    result = summarize(iter(lines))
    # The sum of the separate medians is zero; the paired median is ten.
    stats = result["timings"]["estimated-speech-end-to-playback:realtime"]
    assert stats["count"] == 3
    assert stats["median"] == stats["p95"] == stats["max"] == 10
    assert result["estimated_wait_samples"] == {"paired": 3, "missing_silence": 0}


def test_p95_uses_nearest_rank_and_keeps_rare_long_waits_visible():
    result = summarize(
        f"turn={turn} timing=recording-to-playback seconds={turn} realtime=true"
        for turn in range(1, 21)
    )
    stats = result["timings"]["recording-to-playback:realtime"]
    assert (stats["median"], stats["p90"], stats["p95"], stats["max"]) == (10.5, 18, 19, 20)
    assert result["estimated_wait_samples"] == {"paired": 0, "missing_silence": 20}
    assert not any(key.startswith("estimated-") for key in result["timings"])


@pytest.mark.parametrize("path", ["realtime", "pipeline", "local", "control"])
def test_estimated_wait_separates_routes(path):
    result = summarize([
        "turn=1 input-end=silence captured-seconds=3.0 silence-seconds=1.4",
        f"turn=1 timing=recording-to-playback seconds=0.6 path={path}",
    ])
    assert result["timings"][f"estimated-speech-end-to-playback:{path}"]["median"] == 2.0


@pytest.mark.parametrize("boundary", [
    "session-start id=new", "session-end id=old status=completed",
    "state=conversation session=2", "state=waiting session=1 completed-turns=1",
    "state=stopped", "Stopping conversation", "turn=2 recorded=unused",
    "turn=1 recorded=unused",
])
def test_incomplete_turn_does_not_leak_silence_or_local_route(boundary):
    result = summarize([
        "turn=1 input-end=semantic captured-seconds=4 silence-seconds=3",
        "turn=1 timing=reply seconds=0 local=true",
        boundary,
        "turn=1 timing=recording-to-playback seconds=1",
    ])
    assert result["timings"]["recording-to-playback:pipeline"]["count"] == 1
    assert result["estimated_wait_samples"] == {"paired": 0, "missing_silence": 1}


@pytest.mark.parametrize("silence", ["nan", "inf", "-1", "4", "9" * 400])
def test_invalid_silence_is_excluded_without_losing_playback_metrics(silence):
    result = summarize([
        f"turn=1 input-end=semantic captured-seconds=3 silence-seconds={silence}",
        "turn=1 timing=recording-to-playback seconds=1 realtime=true",
    ])
    assert result["estimated_wait_samples"] == {"paired": 0, "missing_silence": 1}
    assert result["timings"]["recording-to-playback:realtime"]["count"] == 1


def test_spoken_timing_or_boundary_text_cannot_change_pairing():
    result = summarize([
        "turn=1 input-end=semantic captured-seconds=2 silence-seconds=0.5",
        "turn=1 transcript=session-start id=private input-end=semantic silence-seconds=999",
        "turn=1 reply=private timing=recording-to-playback seconds=999",
        "turn=1 timing=recording-to-playback seconds=1 local=true",
    ])
    assert result["timings"]["estimated-speech-end-to-playback:local"]["median"] == 1.5
    assert "private" not in str(result)
