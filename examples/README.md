# `examples/`: published outputs

> **Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4 2026.** Everything in this folder is event work.
> Pre-existing vs built this week: [repo README](../README.md#built-this-week-vs-pre-existing) · [`PROVENANCE.md`](../PROVENANCE.md).

| Path | What | Made by |
|---|---|---|
| `170123/ai_ruling.json`, `score_crosscheck.json`, `hands.json` | signed advisory files for the public VERIFIED match 170123 (AI advisory key, bound to the receipt hash) | Muse Spark 1.3 |
| `170123/commentary_witness.json` | signed commentary witness for 170123 from the 3 public highlight clips (built Oct 28 2026): broadcast agrees with 3 of 3 locked scores; info only, lower-only; see `docs/COMMENTARY_WITNESS.md` | Muse Voice Transcribe 1.0, Muse Spark 1.3 |
| `170123/ai_ruling_170123_{pinned,unpinned}.example.json` | real Muse Spark explanations, pinned (VERIFIED) and unpinned (PARTIAL) | Muse Spark 1.3 |
| `170123/seen.json`, `170123/seen/` | Evidence Lens sidecar, overlay stills and the hl01 overlay video (rendered from QorCap's public 170123 highlight clips) | SAM 3.1, Muse Spark 1.3 |
| `practice-echo/echo.sidecar.json` | Challenge Echo aggregates from a private practice game (video and inputs kept private) | SAM 3.1 |
| `redteam/report.json`, `summary.md` | Red-Team the Referee results | Muse Wonder 1.0, Muse Spark 1.3 |

`170123/receipt.json` is the **pre-existing** public receipt; it is git-ignored and copied here by
`scripts/fetch_upstream.sh`.
