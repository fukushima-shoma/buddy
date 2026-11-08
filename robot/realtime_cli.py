"""Check Realtime output without opening a microphone or speaker."""
from __future__ import annotations

import argparse
from pathlib import Path
import time
import wave

from robot.realtime_conversation import DEFAULT_REALTIME_MODEL, RealtimeConversation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", required=True)
    parser.add_argument("--model", default=DEFAULT_REALTIME_MODEL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    session = RealtimeConversation(model=args.model, child_mode=True)
    try:
        session.connect()
        started = time.monotonic()
        first = None
        for chunk in session.stream_reply(args.text, args.output):
            if first is None and chunk:
                first = time.monotonic() - started
        with wave.open(str(args.output), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
        print(f"realtime=completed first-audio={first:.3f} "
              f"total={time.monotonic() - started:.3f} audio-duration={duration:.3f} "
              f"reply-chars={len(session.last_reply_text)}")
        return 0
    except RuntimeError as exc:
        print(f"realtime=failed detail={exc}")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
