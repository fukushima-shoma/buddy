from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from urllib.parse import urlsplit

from robot.conversation_state import ConversationEvent, ConversationPhase


class ConversationDisplay:
    """Serve the phase and current recognized utterance without storing history."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self._lock = Lock()
        self._phase = ConversationPhase.WAITING
        self._transcript: str | None = None
        self._revision = 0
        page = Path(__file__).with_suffix(".html").read_bytes()
        display = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(2)

            def do_GET(self) -> None:
                path = urlsplit(self.path).path
                if path == "/":
                    self.respond(200, "text/html; charset=utf-8", page)
                elif path == "/api/state":
                    body = json.dumps(display.snapshot()).encode("utf-8")
                    self.respond(200, "application/json; charset=utf-8", body)
                else:
                    self.respond(404, "text/plain; charset=utf-8", b"Not found")

            def do_POST(self) -> None:
                self.respond(405, "text/plain; charset=utf-8", b"Read only")

            def respond(self, status: int, mime: str, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format: str, *args: Any) -> None:
                # Do not keep phone addresses or request paths in conversation logs.
                pass

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._server.daemon_threads = True
        self._thread = Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.1),
            name="buddy-conversation-display", daemon=True,
        )
        self._thread.start()

    @property
    def address(self) -> tuple[str, int]:
        return self._server.server_address[:2]

    def __call__(self, event: ConversationEvent) -> None:
        with self._lock:
            transcript = self._transcript
            if event.phase in (
                ConversationPhase.WAITING, ConversationPhase.LISTENING,
                ConversationPhase.STOPPED,
            ):
                transcript = None
            if (event.phase, transcript) != (self._phase, self._transcript):
                self._revision += 1
            self._phase = event.phase
            self._transcript = transcript

    def update_transcript(self, transcript: str | None) -> None:
        with self._lock:
            if self._phase in (ConversationPhase.WAITING, ConversationPhase.STOPPED):
                return
            text = (transcript or "").strip() or None
            if text != self._transcript:
                self._transcript = text
                self._revision += 1

    def snapshot(self) -> dict[str, str | int | None]:
        with self._lock:
            return {"phase": self._phase.value, "revision": self._revision,
                    "transcript": self._transcript}

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


class ConversationEventSinks:
    """Keep existing ROS reactions alongside the optional browser display."""

    def __init__(self, *sinks: Any) -> None:
        self._sinks = sinks

    def __call__(self, event: ConversationEvent) -> None:
        for sink in self._sinks:
            sink(event)

    def close(self) -> None:
        try:
            for sink in self._sinks[:-1]:
                sink.close()
        finally:
            self._sinks[-1].close()
