# `qortime_ai/seen/`: "What the referee saw" Evidence Lens (SAM 3.1 + Muse Spark 1.3)

> **Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4 2026.** Everything in this folder is event work.
> Pre-existing vs built this week: [repo README](../../README.md#built-this-week-vs-pre-existing) · [`PROVENANCE.md`](../../PROVENANCE.md).

SAM 3.1 video-tracks the scorebug from the referee's own OCR region (box prompt) and splits the referee's motion energy
into players / HUD / rest (concept prompt, aggregates only). Muse Spark 1.3 writes one cited caption per segment.
Output: a `seen.v0` sidecar bound to the receipt hash and an overlay render. **Visualization only, not a referee input**:
no status field, `receipt.v0` unchanged.

| File | Role |
|---|---|
| `fetch.py` | paid SAM 3.1 calls; outputs cached outside the repo |
| `sam_video.py` | SAM 3.1 video request/response handling |
| `analyze.py` | scorebug in-place counts, anchor drift, motion split |
| `captions.py`, `build.py` | cited Muse Spark captions (with template fallback) and the `seen.v0` sidecar |
| `lens.py`, `render.py` | Evidence Lens overlay (aqua; gold only for a score lock when the verifier returns VERIFIED) |

```bash
python -m qortime_ai.seen.fetch CLIPS_DIR CACHE_DIR LEDGER          # paid, run once; per-frame masks stay out of the repo
python -m qortime_ai.seen --clips DIR --receipt receipt.json --cache CACHE_DIR --out DIR \
  [--render DIR] [--spark --ledger spend.jsonl]                      # --spark refreshes the cached captions (paid)
```
Tests: `tests/test_seen.py`, `web/seen-view.test.mjs`. Full write-up: [`docs/EVIDENCE_LENS.md`](../../docs/EVIDENCE_LENS.md).
