# Provenance: where every file came from

All code here was first written during the Meta AI Developer Hackathon (kickoff Mon Oct 26 2026, 11:00 AM CT / 12:00 PM ET)
in [ConWan30/qortime](https://github.com/ConWan30/qortime), in new paths created after the pre-event boundary commit
[`0e87ec3`](https://github.com/ConWan30/qortime/commit/0e87ec3) (Sun Oct 25 2026). First in-window merge: PR #89, Mon Oct 26 4:05 PM CT.
It was extracted into this standalone repo on Tue Oct 27 2026 after the organizers asked for a repo containing only event work.

Changes made while extracting (also in-window): the package was renamed `qor_receipt.ai_ruling` / `qor_receipt.hands` →
`qortime_ai.ai_ruling` / `qortime_ai.hands`; `verify/` → `web/`; import and fixture paths point at the git-ignored pinned
upstream checkout; the panel CSS added to `verify/viewer.css` in #92/#93/#95 was moved verbatim to `web/advisory-panels.css`;
5 referee-hook integration tests are skipped here; `web/demo.html`, `web/demo-170123.mjs`, `scripts/fetch_upstream.sh`,
`pyproject.toml`, `package.json`, README and this file are new; the caption scripts were parameterised (key from env).

| This repo | Origin in qortime | PRs |
|---|---|---|
| `qortime_ai/ai_ruling/explainer.py`, `guardrail.py`, `__main__.py`, `__init__.py`, `README.md` | `qor_receipt/ai_ruling/` | #90, #92, #93 |
| `qortime_ai/ai_ruling/muse.py` | same | #90, #97, #98, #101 |
| `qortime_ai/ai_ruling/signing.py`, `advisory_keys.json` | same | #92, #93 |
| `qortime_ai/ai_ruling/score_crosscheck.py` | same | #93, #96 |
| `qortime_ai/ai_ruling/sam_scorebug.py` | same | #93, #101 |
| `qortime_ai/ai_ruling/auto.py` | same | #96, #99 |
| `qortime_ai/hands/*` | `qor_receipt/hands/` | #94, #95 |
| `tests/test_ai_ruling*.py`, `test_score_crosscheck.py`, `test_sam_scorebug.py`, `test_hands*.py`, `test_auto_advisory.py` | `tests/` | #90–#99, #101 |
| `web/auto-pin.js`, `auto-pin.test.mjs`, `AUTO_PIN.md` | `verify/` | #89 |
| `web/ai-ruling-view.js`, `ai-ruling.test.mjs`, `ai_advisory_keys.inc.js` | `verify/` | #92, #93 |
| `web/score-crosscheck-view.js`, `score-crosscheck.test.mjs`, `lower-only.js` | `verify/` | #93 |
| `web/hands-view.js`, `hands.test.mjs` | `verify/` | #95 |
| `web/advisory-fetch.js`, `advisory-fetch.test.mjs` | `verify/` | #96 |
| `web/advisory-panels.css` | lines added to `verify/viewer.css` | #92, #93, #95 |
| `examples/170123/ai_ruling.json`, `score_crosscheck.json`, `hands.json` | `site/matches/170123/` | #92, #93, #95 |
| `examples/170123/ai_ruling_170123_*.example.json` | `docs/hackathon/` | #90 |
| `demo_pipeline/captions/*` | submission demo pipeline (never in qortime) | Oct 26–27 |
| `qortime_ai/redteam/*`, `tests/test_redteam.py`, `examples/redteam/*` | new in this repo (never in qortime); built Oct 27 2026, in the event window. The verifier it attacks is pre-existing and unmodified. Insider pass (re-sign with TEST keys) added Oct 27 2026, in-window | Oct 27– |
| `qortime_ai/seen/*`, `tests/test_seen.py`, `web/seen-view.js`, `web/seen-view.test.mjs`, `examples/170123/seen.json`, `examples/170123/seen/*`; seen panel lines in `web/demo.html` and `web/advisory-panels.css` | new in this repo (never in qortime); built Oct 27 2026, in the event window. Inputs: QorCap's public 170123 highlight clips + the pre-existing receipt; SAM 3.1 + Muse Spark 1.3 outputs from Oct 27 2026 | Oct 27– |
| `qortime_ai/echo/*`, `tests/test_echo.py`, `web/echo-view.js`, `web/echo.test.mjs`, `examples/practice-echo/echo.sidecar.json`; echo panel lines in `web/demo.html` and `web/advisory-panels.css` | new in this repo (never in qortime); built Oct 27 2026, in the event window. Inputs: a private practice game (video + inputs kept private, only per-press aggregates published); SAM 3.1 outputs from Oct 27 2026 | Oct 27– |
| `docs/*` (feature write-ups moved out of the README, hero banners + `docs/readme/make_hero.py`), sub-folder READMEs (`qortime_ai/{redteam,seen,echo}/README.md`, `web/README.md`, `examples/README.md`, `demo_pipeline/README.md`), README redesign | new in this repo (never in qortime); written Oct 27 2026, in the event window. The hero banners are newly drawn in QorTime's **pre-existing** brand style (name, clock mark, colors, wordmark typeface from ConWan30/qortime) | Oct 27– |

## Event-built edits to pre-existing qortime files (stay upstream, not copied here)
Small hooks that wire the code above into the existing referee and verifier page:
`verify/index.html`, `verify/viewer-ui.js`, `verify/viewer.css`, `verify/test.mjs` (#89, #92, #93, #95, #96);
`qor_receipt/review/engine.py`, `qor_receipt/referee_service/app.py`, `docs/REFEREE_SERVICE.md` (#96, #98).

## Other in-window work NOT in this repo (non-Meta fixes to pre-existing code)
qortime #91 (handoff note), #100/#102/#103 (site UI), #104 (challenge rule), #105 (recorder version), #106 (motion rule v4),
#107/#108 (HACKATHON.md, removed a public match page, README contact); qorcap #116–#119 (end-menu reader fix, v0.3.38
release, HACKATHON.md, README contact). These are edits to pre-existing code and are listed only for completeness.
