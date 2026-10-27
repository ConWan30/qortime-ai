# QorTime AI — Meta Muse explains the referee's result, it never decides it

**Meta Global AI Developer Hackathon (Cerebral Valley), Indie Developer track. Solo build by Contravious Battle.**
This repository contains **only work built during the event (Mon Oct 26 – Wed Nov 4, 2026)**. QorTime's pre-existing
code is kept out; it is fetched at a pinned pre-event commit when you run or test this repo (see below).

QorTime is anti-cheat and verified skill for console head-to-head matches (not a coach, not a sports analyzer). A
deterministic referee checks a signed, hash-chained match receipt and returns VERIFIED, PARTIAL, SELF-SIGNED or FAIL.
This repo is the AI layer added on top during the hackathon: Meta models **explain** that result and **double-check**
it, under hard rules — the AI never decides a verdict, and its one status-affecting signal can only lower VERIFIED to
PARTIAL, never raise a status or fail a match.

## Pre-existing (not in this repo)
Built before kickoff (everything at [`ConWan30/qortime@0e87ec3`](https://github.com/ConWan30/qortime/commit/0e87ec3),
Sun Oct 25 2026, and earlier), plus the whole capture client:
- [ConWan30/qortime](https://github.com/ConWan30/qortime): receipt format `schema/receipt.v0.json` (frozen), Ed25519
  signing over RFC 8785 canonical JSON, the deterministic verifier (`qor_receipt/receipt.py`, `verify/verify.js`),
  the referee service and official post-hoc review, trusted-referee list and revocations, transparency log, the website
  and match pages (including the public VERIFIED match 170123, signed Oct 23 2026).
- [ConWan30/qorcap](https://github.com/ConWan30/qorcap): the Windows capture client (capture-card video hash chain,
  DualSense USB log, pause challenges). No Meta model calls.

This repo uses that code only as a **pinned dependency** (`pyproject.toml` → `qor-receipt @ git+…@0e87ec3`) and a
**git-ignored checkout** (`scripts/fetch_upstream.sh` → `upstream/qortime/`, same commit). Nothing from it is committed here.
The only pre-existing data used is the public receipt of match 170123, fetched from that checkout into `examples/170123/` (git-ignored).

## Built Oct 26 – Nov 4, 2026 (in this repo)
| What | Path | Meta model | Effect on the verdict |
|---|---|---|---|
| Receipt explainer: verifier results → plain-English explanation, fail-closed, deterministic guardrail (exact status, no "attested"/hardware claims, no coaching, no identity claims) | `qortime_ai/ai_ruling/explainer.py`, `guardrail.py`, `muse.py`, `__main__.py` | Muse Spark 1.3 | none |
| Separate AI **advisory** signing key (never a referee key) + signed sidecar bound to the receipt hash | `qortime_ai/ai_ruling/signing.py`, `advisory_keys.json`, `web/ai_advisory_keys.inc.js` | — | none |
| Score cross-check: Muse Spark is a second reader of every locked score | `qortime_ai/ai_ruling/score_crosscheck.py`, `web/score-crosscheck-view.js`, `web/lower-only.js` | Muse Spark 1.3 | lower only (VERIFIED → PARTIAL) |
| Scorebug locator for viewers | `qortime_ai/ai_ruling/sam_scorebug.py` | SAM 3.1 | none (info only) |
| Show Your Hands: verified-input overlay + press-to-pixel check; Muse play-start filter can only remove candidates | `qortime_ai/hands/`, `web/hands-view.js` | Muse Spark 1.3 | lower only, capped at PARTIAL |
| Automatic advisory job run by the referee after the verdict is final (caps, kill switch, retries) | `qortime_ai/ai_ruling/auto.py` | Muse Spark 1.3 | none (never delays or changes it) |
| Advisory fetch from the referee + verifier auto-pin of trusted referee keys | `web/advisory-fetch.js`, `web/auto-pin.js`, `web/AUTO_PIN.md` | — | none |
| Browser panels for the three signed advisory files | `web/*-view.js`, `web/advisory-panels.css`, `web/demo.html`, `web/demo-170123.mjs` | — | display only |
| Demo-video captions timed by ASR | `demo_pipeline/captions/` | Muse Voice Transcribe 1.0 | n/a (video only) |
| Signed advisory files for match 170123 | `examples/170123/{ai_ruling,score_crosscheck,hands}.json` | Muse Spark 1.3 | — |

File-by-file origin (qortime PR numbers): [`PROVENANCE.md`](PROVENANCE.md).

## How Meta models are used
- **Muse Spark 1.3** — (1) writes the plain-English explanation of the referee's result; a deterministic guardrail
  rejects any text that misstates the status or makes banned claims, and the result is signed with an advisory key;
  (2) independently re-reads the scorebug at every locked score: agree = no change, disagree = VERIFIED → PARTIAL,
  unsure/unavailable = "Muse unchecked", no penalty; (3) filters Show Your Hands play-start candidates (remove-only).
  On match 170123: 2 of 2 checked locked scores agree (third: unsure → unchecked), ~$0.009 for 6 reads.
- **SAM 3.1** — boxes the scorebug for viewers. Info only; never a status signal.
- **Muse Voice Transcribe 1.0** — event-stream ASR of the demo narration; each partial's `audioProcessedMs` times the
  burned-in captions (`demo_pipeline/captions/make_srt.py`, reproduces `data/vo-v6-captions.srt` byte-for-byte).
- Keys come only from the environment (`META_API_KEY`); nothing in this repo contains a key.

## Run it
Requires Python ≥ 3.10, Node ≥ 20, git. No API key needed for tests or the demo.
```bash
./scripts/fetch_upstream.sh            # pre-existing qortime @ 0e87ec3 -> upstream/ (git-ignored) + 170123 receipt
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'                # installs the pinned pre-existing qor-receipt library as a dependency
pytest -q                              # 138 passed, 5 skipped (referee-hook integration tests live upstream)
npm test                               # 5 browser-module test files, 125 checks
node web/demo-170123.mjs               # offline: verdict from verify.js, then the signed Muse files, lower-only
python -m http.server 8000             # then open http://localhost:8000/web/demo.html
```
Live Muse Spark explanation (needs a Meta Model API key):
```bash
META_API_KEY=... python -m qortime_ai.ai_ruling examples/170123/receipt.json --no-write \
  --pub b283cffb9279f2f90859268c64ef21861ef7e5d9fc773bdb8061af0e80624889
```
The production integration (the referee's background hook and the verifier page at https://qortime.com/verify/) is a
small set of edits to pre-existing qortime files and stays in that repo (see `PROVENANCE.md`).

## Rules this code keeps
- The verdict comes only from the deterministic verifier. AI output lives in separate signed sidecars; deleting or
  tampering with them never changes the verdict (tests check this).
- The receipt format is frozen; new data goes in sidecars.
- Never "attested" or "hardware-verified"; device status is at most "TPM claimed (unverified)".
- QorTime does not prove who held the controller and does not catch collusion.
- No secrets, raw match footage, raw controller logs, gamertags, OCR weights or held-out game data in this repo.

## Creator & contact

Built by **Contravious Battle**, solo founder, QorTime.

- Email: [kamazi.shotta@icloud.com](mailto:kamazi.shotta@icloud.com) (personal) · [qoresence@mail.grokbot.com](mailto:qoresence@mail.grokbot.com) (project inbox)
- LinkedIn: [linkedin.com/in/contravious-battle-b8a25a445](https://www.linkedin.com/in/contravious-battle-b8a25a445)
- X: [@ConWanZo](https://x.com/ConWanZo) (personal) · [@QorTimeHQ](https://x.com/QorTimeHQ) (project)
- GitHub: [ConWan30](https://github.com/ConWan30)

## License
MIT (see `LICENSE`). Not affiliated with Meta, EA, the NFL or Sony.
