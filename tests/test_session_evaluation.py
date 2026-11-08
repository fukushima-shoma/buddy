import json
from types import SimpleNamespace

from robot.conversation_memory import ConversationMemoryStore
from robot.session_evaluation import evaluate_session, parse_sessions, render_report
from robot.session_evaluation_cli import main


def event(message, stamp, pid="10"):
    return json.dumps({"MESSAGE": message, "__REALTIME_TIMESTAMP": str(stamp),
                       "_PID": pid, "_BOOT_ID": "boot"})


def entry(session="s", turn=1, user="車のお話を聞かせて", assistant="赤い車のお話。" * 25):
    result = {"session": session, "timestamp": "1970-01-01T00:00:02+00:00",
              "user": user, "assistant": assistant}
    if turn is not None:
        result["turn"] = turn
    return result


def story_logs():
    return [
        "state=conversation session=1", "session-start id=s backend=realtime",
        "turn=1 listening=true", "turn=1 transcript=車のお話を聞かせて",
        "turn=1 input-end=semantic captured-seconds=3.0 silence-seconds=1.2",
        "turn=1 timing=recording-to-playback seconds=1.5 realtime=true",
        "turn=1 realtime=reply reply-chars=210 reply-mode=story interrupted=false",
        "session-end id=s status=completed completed-turns=1",
        "state=waiting session=1 completed-turns=1",
    ]


def test_exact_session_boundaries_and_story_timing():
    sessions = parse_sessions(story_logs())
    assert len(sessions) == 1
    report = evaluate_session(sessions[0], [entry()])
    assert report["session"]["status"] == "completed"
    assert report["coverage"]["paired_turns"] == 1
    assert report["coverage"]["memory_source"] == "session-id"
    assert report["metrics"]["estimated_speech_to_playback_seconds"]["median"] == 2.7
    assert report["metrics"]["story_replies"] == 1
    assert not report["findings"]


def test_semantic_watchdog_keeps_end_reason_and_estimated_latency():
    session = parse_sessions([
        "session-start id=s",
        "turn=1 transcript=こんにちは",
        "turn=1 input-end=semantic-silence-watchdog captured-seconds=3.1 silence-seconds=3.0",
        "turn=1 timing=recording-to-playback seconds=1.2 realtime=true",
        "session-end id=s status=completed completed-turns=1",
    ])[0]
    report = evaluate_session(session, [], include_dialogue=True)
    assert report['review_context']['turns'][0]['input_end'] == 'semantic-silence-watchdog'
    assert report['metrics']['estimated_speech_to_playback_seconds']['median'] == 4.2


def test_realtime_input_failures_are_counted_without_conversation_text():
    session = parse_sessions([
        "session-start id=s",
        "turn=1 realtime=input result=success failure=none uploaded-bytes=100 manual-commit=false server-committed=true events=committed,transcribed",
        "turn=2 realtime=fallback stage=transcription detail=private-server-message",
        "turn=2 realtime=input result=fallback failure=receive uploaded-bytes=200 manual-commit=true server-committed=false events=none",
        "session-end id=s status=completed completed-turns=2",
    ])[0]
    report = evaluate_session(session, [])
    assert report["metrics"]["realtime_input_attempts"] == 2
    assert report["metrics"]["realtime_input_failures"] == 1
    assert report["metrics"]["realtime_input_failure_reasons"] == {"receive": 1}
    assert "private-server-message" not in str(report)


def test_latest_sessions_are_separate_across_restart_and_station_numbers():
    lines = [event("state=conversation session=1", 1), event("turn=1 listening=true", 2),
             event("state=waiting session=1 completed-turns=1", 3),
             event("Started Buddy", 4, pid="1"),
             event("state=conversation session=1", 5, pid="20"),
             event("turn=1 listening=true", 6, pid="20")]
    sessions = parse_sessions(lines)
    assert len(sessions) == 2
    assert sessions[0].status == "completed"
    assert sessions[1].status == "in-progress"
    assert sessions[0].id != sessions[1].id


def test_subprocess_messages_do_not_end_active_session():
    sessions = parse_sessions([event("session-start id=s", 1),
                               event("ROS publisher started", 2, pid="40"),
                               event("turn=1 listening=true", 3),
                               event("session-end id=s status=completed", 4)])
    assert len(sessions) == 1
    assert sessions[0].status == "completed"


def test_legacy_time_window_join_is_exact_per_turn():
    lines = [event("state=conversation session=1", 1_000_000),
             event("turn=1 listening=true", 1_100_000),
             event("turn=1 transcript=車のお話を聞かせて", 1_200_000),
             event("turn=2 listening=true", 3_000_000),
             event("turn=2 transcript=車のお話を聞かせて", 3_100_000),
             event("state=waiting session=1 completed-turns=2", 5_000_000)]
    first, second = entry(session="old", turn=None), entry(session="old", turn=None, assistant="短いよ。")
    second["timestamp"] = "1970-01-01T00:00:04+00:00"
    report = evaluate_session(parse_sessions(lines)[0], [first, second])
    assert report["coverage"]["paired_turns"] == 2
    assert report["coverage"]["memory_source"] == "legacy-time-window"
    assert next(f for f in report["findings"] if f["code"] == "short-story")["turns"] == [2]


def test_ambiguous_legacy_memory_is_not_assigned_by_position():
    lines = [event("state=conversation session=1", 1_000_000),
             event("turn=1 transcript=車のお話を聞かせて", 1_100_000),
             event("state=waiting session=1 completed-turns=1", 5_000_000)]
    report = evaluate_session(parse_sessions(lines)[0], [entry(session="a"), entry(session="b")])
    assert report["coverage"]["memory_source"] == "ambiguous"
    assert report["coverage"]["paired_turns"] == 0


def test_memory_wrong_user_and_truncated_history_do_not_fabricate_pairs():
    session = parse_sessions(story_logs())[0]
    report = evaluate_session(session, [entry(user="別の発話"), entry(session="other")])
    assert report["coverage"]["paired_turns"] == 0
    assert report["metrics"]["story_replies"] == 1


def test_report_flags_evidence_without_claiming_semantic_scores_or_exposing_text():
    lines = ["session-start id=s", "turn=1 transcript=秘密の文章が",
             "turn=1 input-end=duration-limit captured-seconds=20.0 silence-seconds=0.0",
             "turn=1 reply=秘密の返答", "turn=2 transcript=ちがうよ",
             "turn=2 input-end=semantic captured-seconds=9.0 silence-seconds=6.3",
             "turn=2 realtime=reply reply-chars=20 reply-mode=conversation interrupted=true",
             "session-end id=s status=completed"]
    report = evaluate_session(parse_sessions(lines)[0], [])
    assert {f["code"] for f in report["findings"]} == {"recording-limit", "long-end-wait", "possibly-incomplete", "correction"}
    rendered = render_report(report)
    assert "秘密" not in rendered
    assert "秘密" not in json.dumps(report, ensure_ascii=False)
    assert "採点した結果ではない" in rendered
    assert report["metrics"]["interruptions"] == 1


def test_short_story_and_mode_mismatch_are_detected_but_interrupted_story_is_not_short_failure():
    lines = ["session-start id=s", "turn=1 transcript=物語を話して",
             "turn=1 realtime=reply reply-chars=22 reply-mode=conversation interrupted=false",
             "turn=2 transcript=物語を話して",
             "turn=2 realtime=reply reply-chars=10 reply-mode=story interrupted=true",
             "session-end id=s status=completed"]
    report = evaluate_session(parse_sessions(lines)[0], [])
    assert all(f["turns"] == [1] for f in report["findings"])
    assert {f["code"] for f in report["findings"]} == {"short-story", "story-mode-mismatch"}


def test_spoken_log_words_do_not_inflate_timings_or_fallbacks():
    lines = ["session-start id=s",
             "turn=1 transcript=timing=recording-to-playback seconds=999 realtime=fallback",
             "turn=1 timing=recording-to-playback seconds=1.5 realtime=true",
             "turn=1 timing=recording-to-playback seconds=9.5 path=control",
             "session-end id=s status=completed"]
    report = evaluate_session(parse_sessions(lines)[0], [])
    assert report["metrics"]["fallback_events"] == 0
    assert report["metrics"]["recording_to_playback_seconds"]["median"] == 1.5


def test_missing_boundaries_are_marked_partial_and_interruption_is_explicit():
    sessions = parse_sessions(["turn=9 listening=true", "Stopping conversation loop."])
    assert sessions[0].source == "missing-boundary"
    assert sessions[0].status == "interrupted"


def test_cli_reads_local_files_and_selects_completed_session(tmp_path, capsys):
    logs = tmp_path / "logs.txt"
    logs.write_text("\n".join(story_logs() + ["session-start id=active", "turn=1 listening=true"]))
    memory = tmp_path / "memory.json"
    store = ConversationMemoryStore(memory)
    store.append(session="s", turn=1, user="車のお話を聞かせて", assistant="赤い車のお話。" * 25)
    assert main(["--log-file", str(logs), "--memory-file", str(memory), "--completed", "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["session"]["id"] == "s"
    assert report["coverage"]["paired_turns"] == 1


def test_cli_missing_session_has_clear_nonzero_exit(tmp_path, capsys):
    logs = tmp_path / "empty.txt"
    logs.write_text("")
    assert main(["--log-file", str(logs)]) == 1
    assert "no-matching-session" in capsys.readouterr().err


def test_cli_journal_command_is_read_only_and_handles_failure(monkeypatch, capsys):
    def run(command, **kwargs):
        assert command[:3] == ["journalctl", "-u", "buddy-conversation.service"]
        assert kwargs["timeout"] == 15
        return SimpleNamespace(returncode=1, stdout="", stderr="private-error")
    monkeypatch.setattr("robot.session_evaluation_cli.subprocess.run", run)
    assert main([]) == 1
    assert "private-error" not in capsys.readouterr().err


def test_review_context_is_explicit_preserves_unknown_replies_and_redacts_contacts():
    logs = ["session-start id=s", "turn=1 transcript=連絡は child@example.com だよ",
            "session-end id=s status=completed"]
    session = parse_sessions(logs)[0]
    assert "review_context" not in evaluate_session(session, [])
    packet = evaluate_session(session, [], include_dialogue=True)
    assert "child@example.com" not in json.dumps(packet)
    assert packet["review_context"]["turns"][0]["buddy"] is None
    assert "未信頼" in packet["review_context"]["data_trust"]


def test_cli_can_save_private_review_packet(tmp_path):
    logs = tmp_path / "logs.txt"
    logs.write_text("\n".join(story_logs()))
    output = tmp_path / "reports" / "review.json"
    assert main(["--log-file", str(logs), "--memory-file", str(tmp_path / "missing.json"),
                 "--review-context", "--output", str(output)]) == 0
    assert json.loads(output.read_text())["review_context"]["turns"][0]["buddy"] is None
    assert output.stat().st_mode & 0o777 == 0o600


def test_ambiguous_story_and_prompt_echo_are_candidates_not_certainties():
    from robot.transcription import CHILD_TRANSCRIPTION_PROMPT
    logs = ["session-start id=s", "turn=1 transcript=うさぎのお話しです。",
            "turn=1 realtime=reply reply-chars=20 reply-mode=conversation interrupted=false",
            f"turn=2 transcript={CHILD_TRANSCRIPTION_PROMPT}",
            "turn=2 reply=もう一回聞かせてね。 reason=uncertain-transcript",
            "session-end id=s status=completed"]
    report = evaluate_session(parse_sessions(logs)[0], [])
    assert {f["code"] for f in report["findings"]} == {"ambiguous-story-intent", "rejected-transcript", "possible-prompt-echo"}
    assert report["metrics"]["rejected_transcripts"] == 1
