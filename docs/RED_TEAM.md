[← README](../README.md) · [Docs index](README.md)

# Red-Team the Referee — Muse Wonder attacks, the pre-existing verifier judges

> Built Oct 27 2026, during the hackathon week. The verifier under attack (`verify_receipt`, QorTime @ `0e87ec3`) is pre-existing and **unmodified**. Per-attack table: [`examples/redteam/summary.md`](../examples/redteam/summary.md).

`python -m qortime_ai.redteam` → **Outside attacker: 25 attacks · 0 accepted** and
**Insider with signing keys: 25 attacks · 12 accepted** (plus 1 pure replay that is byte-identical to an honest
receipt, reported separately). Muse Wonder 1.0 proposed 26 attacks once (forged / re-signed signatures, score and winner
edits, match-id swap, donor splices, dropped and reordered checkpoints and challenges, timestamp shifts, trust-tier and
key-kind upgrades, signal laundering, type confusion, pin tricks); the output is cached in
`qortime_ai/redteam/fixtures/wonder_attacks.json` so the run is offline and deterministic. Each attack is applied to a
synthetic dual match played through the pre-existing referee service with **freshly generated in-memory TEST keys**
(never a real key, never the live referee, no real match data), then judged by the unmodified pre-existing
`verify_receipt`. An attack counts as accepted only if tampered content comes back VERIFIED.
Muse Spark 1.3 then explains the honest and a tampered result; every sentence must cite the fact field(s) it uses
(`[verdict]`, `[result.home_score]` …), and code rejects missing/unknown citations, numbers, statuses or winners the
cited fields do not support, and overclaim words (the banned list in `qortime_ai/redteam/wording.py`, e.g. "certified", "guaranteed",
"proven cheat-free") in any AI-written text. Output: `examples/redteam/report.json`, `summary.md`.
**Insider pass:** every attack is also re-run with the tampered receipt re-signed by the TEST referee and TEST player
keys (an insider who holds signing keys; checkpoint countersignatures and challenge tokens are not re-forged), so the
inner checks run on their own. They still stop 13 of 25: checkpoint hash chain (seq gap, prev/hash mismatch, time
backwards), timing gaps, winner/score consistency, integer type checks, trust-tier recomputation, missing challenges,
challenges not bound to a live checkpoint, missing motion signals. The 12 accepted are labelled **needs key protection
(out of scope for the verifier)**: 6 are plain re-signed score edits (a key holder can sign anything), 1 is a benign
challenge reorder, and 5 are reported inner-check gaps in the pre-existing verifier, left unchanged here:
`result.final_t_ms` outside the match window (2), challenge `hid_sha256` only format-checked, free-text
`referee.key_kind`, and player pubkeys swappable between roles because checkpoint chains are checked only against the
referee countersignature. Per-attack notes are in `examples/redteam/summary.md`.
Refresh the fixtures (live, ≈ $0.10): `META_API_KEY=... python -m qortime_ai.redteam --generate`.
