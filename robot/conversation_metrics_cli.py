"""Summarize timing logs without retaining conversation text."""
from __future__ import annotations

import json
import math
import re
import statistics
import sys


def summarize(lines):
    timings = {}
    fallbacks = 0
    interrupted = 0
    local_turn = None
    current_turn = None
    trailing_silence = None
    estimated_wait_samples = {"paired": 0, "missing_silence": 0}
    input_ends = {}
    reply_modes = {}
    realtime_inputs = {"attempts": 0, "successes": 0, "failures": 0,
                       "failure_reasons": {}}
    for line in lines:
        # Turn numbers are reused between sessions. Never pair across boundaries.
        if re.match(r"^(?:session-start |session-end |state=conversation |state=waiting |state=stopped$|Stopping )", line):
            current_turn = local_turn = trailing_silence = None
        turn_match = re.match(r"^turn=(\d+) ", line)
        if turn_match and turn_match[1] != current_turn:
            current_turn = turn_match[1]
            local_turn = trailing_silence = None
        if re.match(r"^turn=\d+ recorded=", line):
            local_turn = trailing_silence = None
        end_match = re.match(r"^turn=\d+ input-end=(semantic-silence-watchdog|semantic|silence|duration-limit)(?:\s|$)", line)
        if end_match:
            reason = end_match[1]
            input_ends[reason] = input_ends.get(reason, 0) + 1
            trailing_silence = None
            silence_match = re.fullmatch(
                r"turn=\d+ input-end=\S+ captured-seconds=([0-9]+(?:\.[0-9]+)?) "
                r"silence-seconds=([0-9]+(?:\.[0-9]+)?)\s*", line
            )
            if silence_match:
                captured, silence = map(float, silence_match.groups())
                if math.isfinite(captured) and math.isfinite(silence) and silence <= captured:
                    trailing_silence = silence
        # Only parse application event lines; spoken text may contain log-like words.
        event = re.match(r"^turn=(\d+) (timing=|realtime=)(.*)", line)
        if not event:
            continue
        if "realtime=fallback" in line:
            fallbacks += 1
        if "realtime=reply" in line and "interrupted=true" in line:
            interrupted += 1
        input_match = re.match(
            r"^turn=\d+ realtime=input result=(success|fallback) "
            r"failure=([a-zA-Z0-9_-]+)(?:\s|$)", line
        )
        if input_match:
            realtime_inputs["attempts"] += 1
            if input_match[1] == "success":
                realtime_inputs["successes"] += 1
            else:
                realtime_inputs["failures"] += 1
                reason = input_match[2]
                reasons = realtime_inputs["failure_reasons"]
                reasons[reason] = reasons.get(reason, 0) + 1
        mode_match = re.match(r"^turn=\d+ realtime=reply reply-chars=\d+ reply-mode=(story|conversation)\b", line)
        if mode_match:
            mode = mode_match[1]
            reply_modes[mode] = reply_modes.get(mode, 0) + 1
        match = re.match(r"^turn=\d+ timing=([a-z-]+) seconds=([0-9]+(?:\.[0-9]+)?)(?:\s|$)", line)
        if not match:
            continue
        value = float(match[2])
        if not math.isfinite(value):
            continue
        name = match[1]
        if name == "reply":
            local_turn = event[1] if "local=true" in line else None
        if name == "recording-to-playback":
            path_match = re.search(r"\bpath=(realtime|pipeline|local|control)\b", line)
            path = path_match[1] if path_match else (
                "realtime" if "realtime=true" in line else
                "local" if "local=true" in line or local_turn == event[1] else "pipeline"
            )
            name += ":" + path
            local_turn = None
            if trailing_silence is None:
                estimated_wait_samples["missing_silence"] += 1
            else:
                estimated = value + trailing_silence
                if math.isfinite(estimated):
                    estimated_wait_samples["paired"] += 1
                    timings.setdefault("estimated-speech-end-to-playback:" + path, []).append(estimated)
                else:
                    estimated_wait_samples["missing_silence"] += 1
            trailing_silence = None
        timings.setdefault(name, []).append(value)
    return {
        "timings": {
            name: {"count": len(values), "mean": round(statistics.mean(values), 3),
                   "median": round(statistics.median(values), 3),
                   "p90": sorted(values)[math.ceil(len(values) * 0.9) - 1],
                   "p95": sorted(values)[math.ceil(len(values) * 0.95) - 1],
                   "min": min(values), "max": max(values)}
            for name, values in sorted(timings.items())
        },
        "realtime_fallback_events": fallbacks,
        "realtime_interrupted_replies": interrupted,
        "input_ends": input_ends,
        "reply_modes": reply_modes,
        "realtime_inputs": realtime_inputs,
        "estimated_wait_samples": estimated_wait_samples,
    }


def main() -> int:
    print(json.dumps(summarize(sys.stdin), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
