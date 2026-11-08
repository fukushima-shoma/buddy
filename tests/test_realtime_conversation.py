import base64
from collections import deque
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from robot.audio import MockAudioPlayer, MockAudioRecorder, generate_tone, inspect_wav
from robot.conversation import MockReplyGenerator
from robot.child_games import ChildGameController
from robot.conversation_intents import LocalShortReplyController, MOBILITY_STOP_REPLY
from robot.conversation_loop_cli import run_conversation_loop
from robot.realtime_conversation import RealtimeConversation
from robot.speech import MockSpeechSynthesizer
from robot.transcription import MockTranscriber


class FakeSocket:
    def __init__(self, transcript="赤い車だよ", status="completed"):
        self.sent = []
        self.events = deque()
        self.transcript = transcript
        self.status = status
        self.closed = False
        self.pcm = b"\x01\x00" * 2400

    def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        kind = event["type"]
        if kind == "session.update":
            self.events.append({"type": "session.updated"})
        elif kind == "input_audio_buffer.commit":
            self.events.extend([
                {"type": "input_audio_buffer.committed", "item_id": "user_1"},
                {"type": "conversation.item.input_audio_transcription.completed", "item_id": "user_1", "transcript": self.transcript},
            ])
        elif kind == "response.create":
            self.events.extend([
                {"type": "response.output_audio_transcript.delta", "delta": "赤い車、"},
                {"type": "response.output_audio.delta", "delta": base64.b64encode(self.pcm).decode()},
                {"type": "response.output_audio_transcript.done", "transcript": "赤い車、かっこいいね。"},
                {"type": "response.done", "response": {"status": self.status}},
            ])

    def recv(self, *, timeout):
        if not self.events:
            raise TimeoutError("private-server-message")
        return json.dumps(self.events.popleft(), ensure_ascii=False)

    def close(self):
        self.closed = True


class RealtimeConversationTest(unittest.TestCase):
    def make_session(self, **kwargs):
        self.sockets = []
        transcript = kwargs.pop("transcript", "赤い車だよ")
        status = kwargs.pop("status", "completed")

        def connector(url, **options):
            self.assertTrue(url.startswith("wss://api.openai.com/v1/realtime?model="))
            self.assertGreater(options["open_timeout"], 0)
            socket = FakeSocket(transcript, status)
            self.sockets.append(socket)
            return socket

        return RealtimeConversation(connector=connector, child_mode=True, **kwargs)

    def audio(self, directory):
        return generate_tone(Path(directory) / "input.wav", sample_rate=24000, duration=0.2)

    def test_native_audio_waits_for_local_routing_then_streams_and_saves_wav(self):
        session = self.make_session()
        with TemporaryDirectory() as directory:
            transcript = session.transcribe(self.audio(directory))
            socket = self.sockets[0]
            self.assertEqual(transcript, "赤い車だよ")
            self.assertNotIn("response.create", [event["type"] for event in socket.sent])
            destination = Path(directory) / "reply.wav"
            chunks = list(session.stream_reply(transcript, destination))
            self.assertEqual(b"".join(chunks), socket.pcm)
            self.assertEqual(inspect_wav(destination).sample_rate, 24000)
            self.assertEqual(inspect_wav(destination).frames, 2400)
        self.assertTrue(session.last_completed)
        self.assertEqual(session.last_reply_text, "赤い車、かっこいいね。")
        config = socket.sent[0]["session"]
        self.assertIsNone(config["audio"]["input"]["turn_detection"])
        self.assertEqual(config["audio"]["output"]["voice"], "coral")
        self.assertIn("一人称は「ぼく」", config["instructions"])
        self.assertNotIn("20〜25文字", config["instructions"])

    def test_local_memory_input_is_removed_without_generating_cloud_reply(self):
        session = self.make_session(transcript="誕生日は4月3日")
        with TemporaryDirectory() as directory:
            session.transcribe(self.audio(directory))
            session.discard_pending()
        self.assertIn({"type": "conversation.item.delete", "item_id": "user_1"}, self.sockets[0].sent)
        self.assertFalse(any(event["type"] == "response.create" for event in self.sockets[0].sent))
        self.assertEqual(list(session._history), [])

    def test_local_short_reply_is_included_in_session_context(self):
        session = self.make_session(transcript="ありがとう")
        with TemporaryDirectory() as directory:
            session.transcribe(self.audio(directory))
            session.record_local_reply("どういたしまして。")
        self.assertEqual(list(session._history), [("ありがとう", "どういたしまして。")])
        self.assertEqual(self.sockets[0].sent[-1]["item"]["role"], "assistant")

    def test_closing_partial_audio_cancels_without_remembering_unheard_reply(self):
        session = self.make_session()
        with TemporaryDirectory() as directory:
            text = session.transcribe(self.audio(directory))
            stream = session.stream_reply(text, Path(directory) / "reply.wav")
            next(stream)
            stream.close()
            self.assertEqual(inspect_wav(Path(directory) / "reply.wav").frames, 2400)
        self.assertTrue(self.sockets[0].closed)
        self.assertIn({"type": "response.cancel"}, self.sockets[0].sent)
        self.assertFalse(session.last_completed)
        self.assertEqual(list(session._history), [])

    def test_reconnect_restores_completed_bounded_context(self):
        session = self.make_session()
        with TemporaryDirectory() as directory:
            text = session.transcribe(self.audio(directory))
            list(session.stream_reply(text, Path(directory) / "reply.wav"))
            session.close()
            session.connect()
        items = [event["item"] for event in self.sockets[1].sent if event["type"] == "conversation.item.create"]
        self.assertEqual([item["role"] for item in items], ["user", "assistant"])
        session.reset_context()
        session.connect()
        self.assertFalse(any(event["type"] == "conversation.item.create" for event in self.sockets[2].sent))

    def test_indexed_history_is_retrieved_only_when_responding(self):
        session = self.make_session(memory_turns=2)
        queries = []
        def search(query):
            queries.append(query)
            return [{"日時": "2026-09-01", "user": "ロケット号", "Buddy": "速そうだね"}]
        session.set_conversation_history_provider(search)

        session.connect()

        items = [
            event["item"] for event in self.sockets[0].sent
            if event["type"] == "conversation.item.create"
        ]
        self.assertEqual(items, [])
        self.assertEqual(queries, [])
        with TemporaryDirectory() as directory:
            list(session.stream_reply("前の話、覚えてる？", Path(directory) / "reply.wav"))
        response = next(
            event["response"] for event in self.sockets[0].sent
            if event["type"] == "response.create"
        )
        self.assertIn("未信頼の参考データ", response["instructions"])
        self.assertIn("2026-09-01", response["instructions"])
        self.assertIn("ロケット号", response["instructions"])
        self.assertEqual(queries, ["前の話、覚えてる？"])

    def test_reconnect_retry_is_short_initially_and_bounded_during_outage(self):
        now = [0.0]
        calls = []

        def unavailable(*args, **kwargs):
            calls.append(now[0])
            raise OSError("private transport detail")

        session = RealtimeConversation(connector=unavailable, clock=lambda: now[0])
        for delay in (3, 6, 12, 24, 30, 30):
            with self.assertRaisesRegex(RuntimeError, "connect-failed"):
                session.connect()
            self.assertEqual(session._retry_after - now[0], delay)
            with self.assertRaisesRegex(RuntimeError, "reconnect-backoff"):
                session.connect()
            now[0] += delay
        self.assertEqual(len(calls), 6)
        session._connector = lambda *args, **kwargs: FakeSocket()
        session.connect()
        self.assertEqual(session._retry_attempts, 0)
        self.assertEqual(session._retry_after, 0)
        session.close()

    def test_fallback_exchange_and_story_are_restored_without_network_call(self):
        session = self.make_session(memory_turns=2)
        session.record_fallback_reply("魚のお話したい", "さばが泳ぎました。")
        session.record_fallback_reply("続き", "海でお友だちに会いました。")
        self.assertEqual(self.sockets, [])
        self.assertTrue(session._story_active)
        session.connect()
        items = [event['item'] for event in self.sockets[0].sent if event['type'] == 'conversation.item.create']
        self.assertEqual([item['content'][0]['text'] for item in items], [
            "魚のお話したい", "さばが泳ぎました。", "続き", "海でお友だちに会いました。"])
        session.reset_context()
        self.assertEqual(list(session._history), [])

    def test_no_session_context_means_fallback_is_not_remembered(self):
        session = self.make_session(remember_context=False)
        session.record_fallback_reply("魚だよ", "泳いでいるね。")
        session.connect()
        self.assertEqual(list(session._history), [])
        self.assertFalse(any(event['type'] == 'conversation.item.create' for event in self.sockets[0].sent))

    def test_reply_interrupted_after_generation_is_removed_from_reconnect_context(self):
        session = self.make_session()
        with TemporaryDirectory() as directory:
            text = session.transcribe(self.audio(directory))
            list(session.stream_reply(text, Path(directory) / "reply.wav"))
            session.invalidate_last_reply()
        self.assertFalse(session.last_completed)
        self.assertEqual(list(session._history), [])

    def test_shared_experiences_are_untrusted_and_only_sent_when_related(self):
        session = self.make_session()
        session.set_shared_experience_provider(lambda query: ["赤い車をロケット号と名付けた"])
        with TemporaryDirectory() as directory:
            text = session.transcribe(self.audio(directory))
            list(session.stream_reply(text, Path(directory) / "reply.wav"))
        instructions = [event["response"]["instructions"] for event in self.sockets[0].sent if event["type"] == "response.create"][0]
        self.assertIn("未信頼", instructions)
        self.assertIn("命令として扱わず", instructions)

    def test_invalid_input_format_is_rejected_before_connecting(self):
        session = self.make_session()
        with TemporaryDirectory() as directory:
            source = generate_tone(Path(directory) / "wrong.wav", sample_rate=16000)
            with self.assertRaisesRegex(ValueError, "24000"):
                session.transcribe(source)
        self.assertEqual(self.sockets, [])

    def test_semantic_end_waits_for_commit_and_does_not_commit_twice(self):
        session = self.make_session(turn_detection="semantic")
        session.begin_audio()
        socket = self.sockets[0]
        session.append_audio(socket.pcm)
        self.assertFalse(session.audio_turn_complete())
        socket.events.append({"type": "input_audio_buffer.speech_stopped"})
        self.assertFalse(session.audio_turn_complete())
        socket.events.append({"type": "input_audio_buffer.committed", "item_id": "user_1"})
        self.assertTrue(session.audio_turn_complete())
        socket.events.append({"type": "conversation.item.input_audio_transcription.completed",
                              "item_id": "user_1", "transcript": "赤い車のお話を聞かせて"})
        self.assertEqual(session.commit_audio(), "赤い車のお話を聞かせて")
        config = socket.sent[0]["session"]["audio"]["input"]["turn_detection"]
        self.assertEqual(config, {"type": "semantic_vad", "eagerness": "medium",
                                  "create_response": False, "interrupt_response": False})
        self.assertFalse(any(event["type"] in {"input_audio_buffer.commit", "response.create"}
                             for event in socket.sent))

    def test_semantic_watchdog_tolerates_server_commit_race_without_retry(self):
        session = self.make_session(turn_detection="semantic")
        session.begin_audio()
        socket = self.sockets[0]
        session.append_audio(socket.pcm)
        original = socket.send

        def race_with_manual_commit(raw):
            event = json.loads(raw)
            original(raw)
            if event["type"] == "input_audio_buffer.commit":
                socket.events.clear()
                socket.events.extend([
                    {"type": "error", "error": {
                        "code": "input_audio_buffer_commit_empty",
                        "message": "private server detail",
                    }},
                    {"type": "input_audio_buffer.committed", "item_id": "user_1"},
                    {"type": "conversation.item.input_audio_transcription.completed",
                     "item_id": "user_1", "transcript": "赤い車"},
                ])

        socket.send = race_with_manual_commit
        self.assertEqual(session.commit_audio(), "赤い車")
        commits = [event for event in socket.sent
                   if event["type"] == "input_audio_buffer.commit"]
        self.assertEqual(len(commits), 1)
        self.assertEqual(
            session.input_diagnostics["events"],
            "commit-empty-race,committed,transcribed",
        )
        self.assertEqual(session.input_diagnostics["failure"], "none")

    def test_semantic_capture_error_allows_local_silence_fallback(self):
        session = self.make_session(turn_detection="semantic")
        session.begin_audio()
        socket = self.sockets[0]
        socket.recv = lambda **kwargs: (_ for _ in ()).throw(OSError("private-message"))
        self.assertIsNone(session.audio_turn_complete())
        self.assertTrue(socket.closed)
        with self.assertRaisesRegex(RuntimeError, "reason=receive"):
            session.commit_audio()
        self.assertEqual(session.input_diagnostics["failure"], "receive")

    def test_empty_commit_without_confirmation_times_out_after_one_second(self):
        now = [0.0]
        session = self.make_session(turn_detection="semantic", clock=lambda: now[0])
        session.begin_audio()
        socket = self.sockets[0]
        session.append_audio(socket.pcm)
        original_send = socket.send
        def send(raw):
            original_send(raw)
            if json.loads(raw)["type"] == "input_audio_buffer.commit":
                socket.events.clear()
                socket.events.append({"type": "error", "error": {"code": "input_audio_buffer_commit_empty"}})
        socket.send = send
        original_recv = socket.recv
        waits = []
        def recv(*, timeout):
            if socket.events:
                return original_recv(timeout=timeout)
            if timeout:
                waits.append(timeout)
                now[0] += timeout
            raise TimeoutError()
        socket.recv = recv
        with self.assertRaisesRegex(RuntimeError, "empty-commit-timeout"):
            session.commit_audio()
        self.assertEqual(waits, [1.0])
        self.assertTrue(socket.closed)
        self.assertFalse(any(e["type"] == "response.create" for e in socket.sent))
        self.assertEqual(sum(e["type"] == "input_audio_buffer.commit" for e in socket.sent), 1)
        # A late event stays on the closed socket, never enters a new turn.
        socket.events.append({"type": "conversation.item.input_audio_transcription.completed",
                              "item_id": "late", "transcript": "古い入力"})
        now[0] += 4
        session.begin_audio()
        session.append_audio(self.sockets[-1].pcm)
        self.assertEqual(session.commit_audio(), "赤い車だよ")

    def test_racing_confirmation_restores_normal_transcription_deadline(self):
        now = [0.0]
        session = self.make_session(turn_detection="semantic", clock=lambda: now[0])
        session.begin_audio()
        socket = self.sockets[0]
        session.append_audio(socket.pcm)
        original_send = socket.send
        def send(raw):
            original_send(raw)
            if json.loads(raw)["type"] == "input_audio_buffer.commit":
                socket.events.appendleft({"type": "error", "error": {"code": "input_audio_buffer_commit_empty"}})
        socket.send = send
        original_recv = socket.recv
        waits = []
        def recv(*, timeout):
            if timeout:
                waits.append(timeout)
                now[0] += 0.2
            return original_recv(timeout=timeout)
        socket.recv = recv
        self.assertEqual(session.commit_audio(), "赤い車だよ")
        self.assertAlmostEqual(waits[1], 1.0)
        self.assertGreater(waits[2], 9)

    def test_eagerness_is_configurable_and_validated(self):
        for eagerness in ("low", "medium", "high", "auto"):
            session = self.make_session(turn_detection="semantic", semantic_eagerness=eagerness)
            session.connect()
            vad = self.sockets[0].sent[0]["session"]["audio"]["input"]["turn_detection"]
            self.assertEqual(vad["eagerness"], eagerness)
        with self.assertRaises(ValueError):
            self.make_session(semantic_eagerness="invalid")
        with self.assertRaises(ValueError):
            self.make_session(empty_commit_grace=0)

    def test_story_output_can_play_longer_than_network_timeout_and_continue(self):
        now = [0.0]
        session = self.make_session(clock=lambda: now[0])
        with TemporaryDirectory() as directory:
            stream = session.stream_reply("赤い車の物語を話して", Path(directory) / "reply.wav")
            next(stream)
            now[0] = 12.0  # Simulate aplay backpressure while the story is spoken.
            list(stream)
            self.assertTrue(session.last_completed)
            list(session.stream_reply("続き", Path(directory) / "reply.wav"))
            list(session.stream_reply("犬が好きだよ", Path(directory) / "reply.wav"))
        requests = [event["response"] for event in self.sockets[0].sent if event["type"] == "response.create"]
        self.assertEqual([request["max_output_tokens"] for request in requests], [4096, 4096, 512])
        self.assertNotIn("20〜25文字", requests[0]["instructions"])
        self.assertEqual(session.last_reply_mode, "conversation")

    def test_story_audio_can_exceed_ordinary_limit_but_not_story_limit(self):
        for duration, succeeds in ((31, True), (91, False)):
            with self.subTest(duration=duration), TemporaryDirectory() as directory:
                session = self.make_session()
                session.connect()
                self.sockets[0].pcm = b"\x00\x00" * 24000 * duration
                stream = session.stream_reply("車のお話して", Path(directory) / "reply.wav")
                if succeeds:
                    list(stream)
                    self.assertTrue(session.last_completed)
                else:
                    with self.assertRaisesRegex(RuntimeError, "too-long"):
                        list(stream)
                    self.assertFalse(session.last_completed)

    def test_failed_response_closes_and_does_not_mark_completed(self):
        session = self.make_session(status="failed")
        with TemporaryDirectory() as directory:
            text = session.transcribe(self.audio(directory))
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                list(session.stream_reply(text, Path(directory) / "reply.wav"))
        self.assertTrue(self.sockets[0].closed)
        self.assertFalse(session.last_completed)

    def test_input_timeout_is_bounded_and_does_not_expose_error_message(self):
        session = self.make_session()
        session.begin_audio()
        socket = self.sockets[0]
        original = socket.send

        def send(raw):
            original(raw)
            socket.events.clear()

        socket.send = send
        session.append_audio(socket.pcm)
        with self.assertRaisesRegex(RuntimeError, "realtime-transcription-failed") as error:
            session.commit_audio()
        self.assertNotIn("private-server-message", str(error.exception))
        self.assertIn("reason=timeout", str(error.exception))
        self.assertEqual(session.input_diagnostics["failure"], "timeout")
        self.assertTrue(socket.closed)

    def test_upload_failure_does_not_abort_audio_capture(self):
        session = self.make_session()
        session.begin_audio()
        self.sockets[0].send = lambda raw: (_ for _ in ()).throw(OSError("private"))
        session.append_audio(b"\x00\x00" * 2400)
        session.append_audio(b"\x00\x00" * 2400)
        with self.assertRaisesRegex(RuntimeError, "reason=send"):
            session.commit_audio()
        self.assertEqual(session.input_diagnostics["uploaded_bytes"], 0)

    def test_transcription_failure_has_sanitized_code_and_ignores_other_item(self):
        session = self.make_session(turn_detection="semantic")
        session.begin_audio()
        socket = self.sockets[0]
        session.append_audio(socket.pcm)
        socket.events.extend([
            {"type": "input_audio_buffer.committed", "item_id": "current"},
            {"type": "conversation.item.input_audio_transcription.failed",
             "item_id": "old", "error": {"code": "private code: 秘密"}},
            {"type": "conversation.item.input_audio_transcription.completed",
             "item_id": "current", "transcript": "赤い車"},
        ])
        self.assertEqual(session.commit_audio(), "赤い車")
        self.assertEqual(session.input_diagnostics["events"], "committed,transcribed")

        session.begin_audio()
        session.append_audio(socket.pcm)
        original = socket.send

        def fail_transcription(raw):
            original(raw)
            if json.loads(raw)["type"] == "input_audio_buffer.commit":
                socket.events.clear()
                socket.events.append({
                    "type": "conversation.item.input_audio_transcription.failed",
                    "item_id": "new", "error": {"code": "audio/unintelligible 秘密"},
                })

        socket.send = fail_transcription
        with self.assertRaisesRegex(RuntimeError, "reason=transcription-audiounintelligible") as error:
            session.commit_audio()
        self.assertNotIn("秘密", str(error.exception))
        self.assertEqual(session.input_diagnostics["events"], "transcription-failed")

    def test_session_context_resets_after_configured_turn_count(self):
        session = self.make_session(memory_turns=1)
        with TemporaryDirectory() as directory:
            source = self.audio(directory)
            text = session.transcribe(source)
            list(session.stream_reply(text, Path(directory) / "reply.wav"))
            session.transcribe(source)
        self.assertEqual(len(self.sockets), 2)
        self.assertTrue(self.sockets[0].closed)
        self.assertEqual(list(session._history), [])

    def run_loop(self, session, directory, **kwargs):
        self.model = MockReplyGenerator("モック返答")
        self.speech = MockSpeechSynthesizer()
        self.logs = []
        return run_conversation_loop(
            recorder=kwargs.pop("recorder", MockAudioRecorder()), transcriber=kwargs.pop("transcriber", MockTranscriber("fallback")),
            reply_generator=self.model, synthesizer=self.speech,
            player=kwargs.pop("player", MockAudioPlayer()),
            input_path=Path(directory) / "input.wav",
            speech_output=Path(directory) / "reply.wav",
            duration=0.2, sample_rate=24000, language="ja", turns=1,
            pause=0, realtime=session, output=self.logs.append, **kwargs,
        )

    def test_loop_native_audio_bypasses_reply_and_tts_and_saves_exchange(self):
        session = self.make_session()
        exchanges = []
        transcripts = []
        with TemporaryDirectory() as directory:
            self.run_loop(session, directory, on_exchange=lambda user, reply: exchanges.append((user, reply)),
                          on_transcript=transcripts.append)
        self.assertEqual(self.model.inputs, [])
        self.assertEqual(self.speech.inputs, [])
        self.assertEqual(exchanges, [("赤い車だよ", "赤い車、かっこいいね。")])
        self.assertEqual(transcripts, ["赤い車だよ"])
        self.assertTrue(any("timing=realtime-first-audio" in line for line in self.logs))
        self.assertTrue(self.sockets[0].closed)

    def test_semantic_capture_routes_story_and_stop_before_creating_response(self):
        for transcript in ("車のお話を聞かせて", "止まって"):
            with self.subTest(transcript=transcript), TemporaryDirectory() as directory:
                session = self.make_session(turn_detection="semantic", transcript=transcript)
                test = self

                class SemanticRecorder(MockAudioRecorder):
                    def record_streaming(self, output, *, on_chunk, should_stop, **kwargs):
                        socket = test.sockets[0]
                        on_chunk(socket.pcm)
                        socket.events.extend([
                            {"type": "input_audio_buffer.committed", "item_id": "user_1"},
                            {"type": "conversation.item.input_audio_transcription.completed",
                             "item_id": "user_1", "transcript": transcript},
                        ])
                        test.assertTrue(should_stop())
                        return self.record(output, **kwargs)

                stops = []
                game = ChildGameController()
                game.handle("どうぶつクイズ")
                self.run_loop(session, directory, recorder=SemanticRecorder(),
                              stop_mobility=lambda: stops.append("stop") or True,
                              handle_child_game=game.handle)
                requests = [event for event in self.sockets[0].sent if event["type"] == "response.create"]
                self.assertFalse(any(event["type"] == "input_audio_buffer.commit" for event in self.sockets[0].sent))
                if transcript == "止まって":
                    self.assertEqual(stops, ["stop"])
                    self.assertEqual(requests, [])
                else:
                    self.assertEqual(requests[0]["response"]["max_output_tokens"], 4096)
                    self.assertFalse(game.active)
                    self.assertEqual(self.speech.inputs, [])

    def test_loop_local_short_reply_and_stop_take_priority_over_realtime_response(self):
        for transcript in ("ありがとう", "止まって"):
            with self.subTest(transcript=transcript), TemporaryDirectory() as directory:
                session = self.make_session(transcript=transcript)
                stops = []
                self.run_loop(session, directory, handle_local_short_reply=LocalShortReplyController().reply,
                              stop_mobility=lambda: stops.append("stop") or True)
                self.assertEqual(self.model.inputs, [])
                self.assertEqual(len(self.speech.inputs), 1)
                self.assertFalse(any(event["type"] == "response.create" for event in self.sockets[0].sent))
                if transcript == "止まって":
                    self.assertEqual(stops, ["stop"])
                    self.assertEqual(self.speech.inputs, [MOBILITY_STOP_REPLY])

    def test_loop_unavailable_realtime_falls_back_to_existing_pipeline(self):
        def unavailable(*args, **kwargs):
            raise OSError("private-token")
        session = RealtimeConversation(connector=unavailable)
        with TemporaryDirectory() as directory:
            self.run_loop(session, directory)
        self.assertEqual(self.model.inputs, ["fallback"])
        self.assertEqual(self.speech.inputs, ["モック返答"])
        self.assertFalse(any("private-token" in line for line in self.logs))

    def test_failed_streaming_connection_does_not_retry_same_audio_or_reply(self):
        attempts = []

        def unavailable(*args, **kwargs):
            attempts.append(1)
            raise OSError("private transport")

        class Recorder(MockAudioRecorder):
            def record_streaming(self, *args, **kwargs):
                raise AssertionError("must use local recorder when connection failed")

        session = RealtimeConversation(connector=unavailable)
        with TemporaryDirectory() as directory:
            self.run_loop(session, directory, recorder=Recorder())
        self.assertEqual(attempts, [1])
        self.assertEqual(sum('realtime=fallback' in line for line in self.logs), 1)
        self.assertEqual(list(session._history), [("fallback", "モック返答")])

    def test_failed_input_never_creates_native_reply_with_wrong_pending_audio(self):
        session = self.make_session()
        session.connect()
        socket = self.sockets[0]
        original = socket.send

        def send(raw):
            original(raw)
            if json.loads(raw)['type'] == 'input_audio_buffer.commit':
                socket.events.clear()
                socket.events.append({'type': 'conversation.item.input_audio_transcription.failed'})

        socket.send = send
        with TemporaryDirectory() as directory:
            self.run_loop(session, directory)
        self.assertFalse(any(event['type'] == 'response.create' for event in socket.sent))
        self.assertEqual(self.model.inputs, ["fallback"])
        self.assertEqual(list(session._history), [("fallback", "モック返答")])
        diagnostic = next(line for line in self.logs if "realtime=input" in line)
        self.assertIn("result=fallback failure=transcription-unknown", diagnostic)

    def test_interrupted_fallback_is_not_restored_as_completed_exchange(self):
        class Player(MockAudioPlayer):
            last_interrupted = True

        def unavailable(*args, **kwargs):
            raise OSError("unavailable")

        session = RealtimeConversation(connector=unavailable)
        exchanges = []
        with TemporaryDirectory() as directory:
            self.run_loop(session, directory, player=Player(),
                          on_exchange=lambda *exchange: exchanges.append(exchange))
        self.assertEqual(list(session._history), [])
        self.assertEqual(exchanges, [])

    def test_fallback_control_and_profile_turns_stay_out_of_reconnect_history(self):
        for text in ("止まって", "誕生日は4月3日"):
            with self.subTest(text=text), TemporaryDirectory() as directory:
                def unavailable(*args, **kwargs):
                    raise OSError("unavailable")

                session = RealtimeConversation(connector=unavailable)
                self.run_loop(session, directory, transcriber=MockTranscriber(text),
                              stop_mobility=lambda: True,
                              handle_profile_memory=lambda transcript: "誕生日を覚えたよ" if transcript.startswith("誕生日") else None)
                self.assertEqual(list(session._history), [])

    def test_loop_interruption_stops_mobility_and_does_not_save_unheard_answer(self):
        session = self.make_session()
        exchanges = []
        stops = []

        class InterruptingPlayer(MockAudioPlayer):
            last_interrupted = True
            requested = True

            def play_pcm16_stream(self, chunks, *, on_interrupt, on_first_chunk, **kwargs):
                next(iter(chunks))
                on_first_chunk()
                on_interrupt()
                chunks.close()

            def consume_stop_request(self):
                value, self.requested = self.requested, False
                return value

        with TemporaryDirectory() as directory:
            self.run_loop(session, directory, player=InterruptingPlayer(),
                          on_exchange=lambda user, reply: exchanges.append((user, reply)),
                          stop_mobility=lambda: stops.append("stop") or True)
        self.assertEqual(stops, ["stop"])
        self.assertEqual(exchanges, [])
        self.assertEqual(self.speech.inputs, [MOBILITY_STOP_REPLY])
        self.assertEqual(self.model.inputs, [])
