# Buddy project instructions

## Working style

- Start by reading the relevant code, tests, and phase documentation.
- For review or diagnosis requests, report findings before editing. For implementation requests, make the change and verify it without waiting for routine confirmations.
- Keep changes focused. Preserve unrelated user changes and inspect the final diff before finishing.
- Explain assumptions when hardware, operating system, or deployment details cannot be verified locally.

## Safety and privacy

- Never commit `.env`, credentials, tokens, recordings, or conversation-memory data. Use `.env.example` for configuration examples.
- Do not use `sudo`, install system packages, alter services, access external systems, push branches, or create/merge pull requests unless the user explicitly asks.
- Do not bypass the Codex sandbox or approval checks. Request approval only when an in-scope task genuinely requires access outside the workspace or network access.
- Treat motor, GPIO, power, camera, microphone, and Raspberry Pi commands as real-world operations. Do not run them on attached hardware unless the user explicitly requests it and the target is confirmed.
- For motor-control changes, preserve fail-safe stop behavior, validate input ranges, and avoid tests that can energize hardware unexpectedly.

## Verification

- Run the smallest relevant test set first; use `python -m pytest` for Python tests.
- When shared behavior changes, run the full test suite if practical.
- Do not claim hardware behavior was verified when only mocks or unit tests were run.
- Report the files changed, checks run, and any remaining unverified hardware assumptions.
