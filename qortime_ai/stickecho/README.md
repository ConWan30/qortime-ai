# `qortime_ai/stickecho/`: Stick Echo (SAM 3.1)

> **Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4 2026 (built Oct 28 2026).** Everything in this folder is event work.
> Pre-existing vs built this week: [repo README](../../README.md#built-this-week-vs-pre-existing) · [`PROVENANCE.md`](../../PROVENANCE.md).

Does the player being controlled move the way the left stick says, one fixed lag later? SAM 3.1 tracks that player
(seeded on the game's controlled-player marker); deterministic code removes camera motion, picks the frames and scores
the angle agreement against swapped-log nulls. The lag is fixed beforehand from the same game's pause challenges
([Challenge Echo](../echo/README.md)). **Info only, lower-only:** `agree` / `inconclusive` / `unscorable` add a note;
`disagree` can at most suggest VERIFIED → PARTIAL. It never raises a status and never makes the call.

| File | Role |
|---|---|
| `log.py` | left stick from `inputs.jsonl` (screen axes, ±50 ms mean) |
| `video.py` | controlled-player marker, SAM 3.1 seed boxes and call (cached), camera-compensated motion |
| `select.py` | which motion counts per frame: `sam` (pre-registered), `hybrid` and `marker` (exploratory); never reads the stick |
| `score.py` | angle cosine, swapped-log nulls, z, lag sweep (diagnostic only) |
| `sidecar.py` | `stickecho.sidecar.json` (`qortime.stickecho.v0`, integers only, totals only), lower-only cap |

```bash
# 1) private per-frame tracks (each window = one short video-only clip to SAM 3.1; keep tracks.json local)
META_API_KEY=... python -m qortime_ai.stickecho track VIDEO --video-start-us T0 \
  --window 625.1 3.7 defender --window 813.2 3.2 returner --out /private/tracks.json \
  --yes-send-to-meta --cache /private/cache --ledger spend.jsonl        # --no-sam = marker track only
# 2) totals-only sidecar next to the receipt (lag from this game's Challenge Echo sidecars, fixed before scoring)
python -m qortime_ai.stickecho score /private/tracks.json inputs.jsonl --null-log other_game/inputs.jsonl \
  --echo-sidecar echo.sidecar.json --receipt receipt.v0.json
python -m qortime_ai.stickecho check stickecho.sidecar.json
```
Practice aggregates: [`examples/practice-stickecho/`](../../examples/practice-stickecho/). Tests: `tests/test_stickecho.py`.
Full write-up: [`docs/STICK_ECHO.md`](../../docs/STICK_ECHO.md).
