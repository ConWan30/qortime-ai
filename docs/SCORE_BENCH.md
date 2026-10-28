[← Docs](README.md)

# Muse Spark score-read bench: what "73 of 73" means

**Written Wed Oct 28 2026, in the event window. The bench run itself was Mon Oct 26 2026, about 3:46–3:57 PM CT,
also in the window.**

The demo video shows "73 of 73" for Muse Spark reading the scorebug. This page says exactly what that number is.

## The short version
- **It is a development bench, not a held-out test.** The frames come from practice sessions and test fixtures that
  were already used in earlier (pre-event) scorebug-reader evaluations. The prompt was written before this run and was
  not changed for it, but these frames are not unseen data in the held-out sense.
- **We never trained or fine-tuned Muse.** Muse Spark 1.3 (`muse-spark-1.3`) is called as-is through the Meta Model
  API. "Frames we never trained on" means only that: there was no training step on our side at all. The final
  demo cut says "on frames it was never trained on", with the plate "73/73 · dev bench, never trained on": Muse was
  never trained or tuned on these frames, and they are a development bench, not a held-out set.
- **It is not a match result.** On the live match 170123 the cross-check is "Muse Spark agrees with 2 of 2 checked
  locked scores" (the third lock was unsure, so unchecked). 73/73 is the bench; 2 of 2 is the match.
- **It does not change what Muse is allowed to do.** The cross-check is lower-only: agreement keeps the status, a
  confident disagreement can lower `VERIFIED` to `PARTIAL`, nothing raises a status or fails a match.

## What was measured
One run, 134 frames, one call each, `temperature 0`, about $0.25 total. Input: the scorebug strip crop (bottom 80 px
of a 1280x720 frame, x 300–980, 2x upscale) with the same prompt and JSON schema as
[`qortime_ai/ai_ruling/score_crosscheck.py`](../qortime_ai/ai_ruling/score_crosscheck.py). A read counts as correct
only if Muse is **confident** and both team scores match the label exactly.

| Set | Score visible | Correct and confident | No score shown | Muse unconfident on those | Confident but wrong |
|---|---|---|---|---|---|
| **Dev bench (the 73/73 figure)**: test fixtures + 2 practice sessions | **73** | **73** | 18 (8 are stats-overlay traps) | **18** | **0** |
| Frames from a game on QorTime's held-out list (left out of the figure above) | 38 | 38 | 5 | 5 | 0 |
| All 134 frames | 111 | 111 | 23 | 23 | 0 |

The 38 frames from the held-out-list game were in the full run, so we quote 73/73 (the frames from that game removed)
rather than 111/111.

Per-frame results (labels, Muse's answer, confident flag; no images): 
[`examples/score_bench/muse_spark_bench.json`](../examples/score_bench/muse_spark_bench.json).
[`tests/test_score_bench.py`](../tests/test_score_bench.py) recomputes every number in the table from that file.

## Module run (also not held out)
After the bench, the cross-check module itself ran on the public 170123 lock frames plus 14 bench frames: 15 of 15
checked locks agree, **0 false drops**, 21 of 26 reads confident, about $0.04. A wrong claimed score is caught by
any confident read (tests simulate it).

## Limits
- Small and narrow: one game (Madden NFL 27, PS5), two broadcast scorebug styles, frames from one player's sessions.
- Not held out, so it is not an accuracy estimate for new matches. Treat it as "the reader did not fail on the frames
  we had", nothing more.
- The frame images and their labels are pre-existing, private practice material and are not in this repo. Only the
  in-window run's per-frame outputs are published here.
- Muse's `confident` flag was never wrong on these frames, but that is measured on this bench only. That is why a
  disagreement can only lower a status and an unsure read is never counted.
