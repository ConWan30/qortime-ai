# `qortime_ai/echo/`: Challenge Echo (SAM 3.1)

> **Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4 2026.** Everything in this folder is event work.
> Pre-existing vs built this week: [repo README](../../README.md#built-this-week-vs-pre-existing) · [`PROVENANCE.md`](../../PROVENANCE.md).

During a pause challenge, every logged D-pad press must be followed by the matching move of the pause-menu highlight.
SAM 3.1 tracks the highlight box; deterministic code finds press edges, detects the menu and does the matching. A
deterministic tracker is the fallback (`--no-sam`) and a cross-check. **Info only**: `consistent` / `partial` /
`unscorable` add a note; `mismatch` can at most suggest VERIFIED → PARTIAL. The live referee is not changed.

| File | Role |
|---|---|
| `presses.py` | press edges from `inputs.jsonl` |
| `video.py` | SAM 3.1 highlight track (menu-list column only) + deterministic fallback tracker; menu row pitch for the wrap test |
| `match.py` | per-press latency, directions matched, jitter, menu after OPTIONS |
| `sidecar.py` | `echo.sidecar.json` (`qortime.echo.v0`, integers only), lower-only cap |

```bash
META_API_KEY=... python -m qortime_ai.echo VIDEO inputs.jsonl --video-start-us T0 --pattern LEFT,DOWN,RIGHT,UP \
  --receipt receipt.v0.json --cache /private/cache --ledger spend.jsonl      # --no-sam = deterministic tracker only
```
Practice aggregates: [`examples/practice-echo/echo.sidecar.json`](../../examples/practice-echo/echo.sidecar.json).
Tests: `tests/test_echo.py`, `web/echo.test.mjs`. Full write-up: [`docs/CHALLENGE_ECHO.md`](../../docs/CHALLENGE_ECHO.md).
