import re

from robot.conversation_loop_cli import main
from robot.conversation_memory import ConversationMemoryStore
from robot.session_evaluation import evaluate_session, parse_sessions


def test_mock_session_logs_uuid_and_saves_exact_turn_for_review(tmp_path, monkeypatch, capsys):
    memory = tmp_path / "memory.json"
    monkeypatch.setattr("sys.argv", [
        "conversation-loop", "--turns", "1", "--duration", "0.1", "--pause", "0",
        "--input", str(tmp_path / "input.wav"), "--speech-output", str(tmp_path / "reply.wav"),
        "--auto-conversation-memory", "--conversation-memory-file", str(memory),
    ])
    assert main() == 0
    logs = capsys.readouterr().out
    session_id = re.search(r"session-start id=([a-f0-9]+)", logs)[1]
    assert f"session-end id={session_id} status=completed completed-turns=1" in logs
    entries = ConversationMemoryStore(memory).load()
    assert entries[0]["session"] == session_id
    assert entries[0]["turn"] == 1
    report = evaluate_session(parse_sessions(logs.splitlines())[0], entries)
    assert report["coverage"]["paired_turns"] == 1


def test_failed_session_has_terminal_marker_without_logging_error_data(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["conversation-loop"])
    def fail(**kwargs):
        raise RuntimeError("private-error-data")
    monkeypatch.setattr("robot.conversation_loop_cli.run_conversation_loop", fail)
    import pytest
    with pytest.raises(RuntimeError):
        main()
    logs = capsys.readouterr().out
    assert "status=failed" in logs
    assert "private-error-data" not in logs
    assert parse_sessions(logs.splitlines())[0].status == "failed"


def test_persistent_recall_survives_restart_and_excludes_current_session(tmp_path, monkeypatch):
    from robot.conversation import MockReplyGenerator
    class SearchingReply(MockReplyGenerator):
        def set_conversation_history_provider(self, provider):
            self.provider = provider
        def reply(self, text):
            self.found = self.provider(text) if hasattr(self, "provider") else []
            return "出発しよう"
    memory = tmp_path / "memory.json"
    store = ConversationMemoryStore(memory)
    store.append(session="old", user="赤い車をロケット号と名付けた", assistant="かっこいいね")
    store.append(session="latest", user="積み木でお城", assistant="大きいね")
    generators = []
    def create(**kwargs):
        generator = SearchingReply()
        generators.append(generator)
        return generator
    monkeypatch.setattr("robot.conversation_loop_cli.create_reply_generator",
                        lambda *args, **kwargs: create(**kwargs))
    for mode in ("persistent", "none", "session"):
        monkeypatch.setattr("sys.argv", [
            "conversation-loop", "--memory", mode, "--mock-text", "ロケット号で遊ぼう",
            "--turns", "2", "--duration", "0.01", "--pause", "0",
            "--input", str(tmp_path / "input.wav"), "--speech-output", str(tmp_path / "reply.wav"),
            "--profile-memory", str(tmp_path / "profile.json"),
            "--conversation-memory-file", str(memory),
        ])
        assert main() == 0
    assert len(generators[0].found) == 1  # excludes this run's first turn
    assert generators[0].found[0]["user"] == "赤い車をロケット号と名付けた"
    assert generators[1].found == generators[2].found == []
    assert len(store.load()) == 4  # persistent saved two ordinary exchanges
