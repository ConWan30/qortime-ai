# `qortime_ai/redteam/`: Red-Team the Referee (Muse Wonder 1.0 + Muse Spark 1.3)

> **Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4 2026.** Everything in this folder is event work.
> Pre-existing vs built this week: [repo README](../../README.md#built-this-week-vs-pre-existing) · [`PROVENANCE.md`](../../PROVENANCE.md).

Muse Wonder 1.0 writes receipt-tampering attacks as structured JSON mutations; the **pre-existing, unmodified**
verifier (`verify_receipt`, qortime @ `0e87ec3`) judges each one against freshly generated in-memory TEST keys.
Muse Spark 1.3 then explains the results, citing a fact field in every sentence.

**Result:** Outside attacker: 25 attacks · 0 accepted. Insider with signing keys: 25 attacks · 12 accepted (labelled
needs key protection, out of scope for the verifier). Effect on any verdict: **none** — it attacks the verifier and
never edits it.

| File | Role |
|---|---|
| `generate.py` | one live Muse Wonder + Muse Spark run (`--generate`), cached in `fixtures/` |
| `mutations.py` | applies each attack's JSON mutations to a synthetic receipt |
| `harness.py` | plays a synthetic match through the pre-existing referee service with TEST keys, outside + insider passes |
| `explain.py`, `citations.py` | cited Muse Spark explanations; code rejects missing or unknown citations and unsupported numbers |
| `wording.py` | banned-word filter applied to all AI-written text |
| `fixtures/` | cached Muse Wonder attacks and Muse Spark explanations (offline, deterministic) |

```bash
python -m qortime_ai.redteam                              # offline, cached fixtures -> examples/redteam/
META_API_KEY=... python -m qortime_ai.redteam --generate  # live refresh, about $0.10
```
Tests: `tests/test_redteam.py`. Full write-up: [`docs/RED_TEAM.md`](../../docs/RED_TEAM.md).
