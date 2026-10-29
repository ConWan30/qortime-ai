# Provenance: where every file came from

**Summary.**
1. **Pre-existing:** everything in [ConWan30/qortime](https://github.com/ConWan30/qortime) at [`0e87ec3`](https://github.com/ConWan30/qortime/commit/0e87ec3) (Sun Oct 25 2026) and earlier, which includes the receipt format, the verifier, the referee and the site, plus the QorCap capture client. This repo only uses it as a pinned dependency.
2. **Built this week (Mon Oct 26 – Wed Nov 4 2026):** every file in this repo. Some were written first in qortime (rows with PR numbers below). The rest were written directly here (rows marked "new in this repo").
3. **Upstream hook PRs** (small edits to pre-existing qortime files, kept in that repo): [#89](https://github.com/ConWan30/qortime/pull/89), [#92](https://github.com/ConWan30/qortime/pull/92), [#93](https://github.com/ConWan30/qortime/pull/93), [#95](https://github.com/ConWan30/qortime/pull/95), [#96](https://github.com/ConWan30/qortime/pull/96), [#98](https://github.com/ConWan30/qortime/pull/98). The live referee that reviewed 220105 also ran two in-window non-Meta fixes, [#104](https://github.com/ConWan30/qortime/pull/104) and [#106](https://github.com/ConWan30/qortime/pull/106) ([below](#other-in-window-work-not-in-this-repo-non-meta-fixes-to-pre-existing-code)).

All code here was written during the Meta AI Developer Hackathon (kickoff Mon Oct 26 2026, 11:00 AM CT / 12:00 PM ET).
Some of it was written first in [ConWan30/qortime](https://github.com/ConWan30/qortime), in new paths created after the pre-event
boundary commit [`0e87ec3`](https://github.com/ConWan30/qortime/commit/0e87ec3) (Sun Oct 25 2026). Those are the rows with PR numbers;
the first in-window merge was PR #89, Mon Oct 26 4:05 PM CT. That code was extracted into this standalone repo on Tue Oct 27 2026,
after the organizers asked for a repo containing only event work. The rest was written directly in this repo (rows marked
"new in this repo").

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
| `docs/SCORE_BENCH.md`, `examples/score_bench/muse_spark_bench.json`, `tests/test_score_bench.py`; README "Who benefits" and test counts | new in this repo (never in qortime); written Wed Oct 28 2026, in the event window. Per-frame outputs are from the Muse Spark bench run of Mon Oct 26 2026 (~3:46–3:57 PM CT, in-window); the frame images and labels are pre-existing private practice material and are not included | Oct 28 |
| `qortime_ai/agent_api/*`, `tests/test_agent_api.py`, `tests/fixtures/agent_api/*`, `deploy/agent-api/Dockerfile`, `docs/AGENT_API.md`; `agent-api` extra in `pyproject.toml`; "proof of human play" and "settle" rules added to `qortime_ai/ai_ruling/guardrail.py` and `qortime_ai/redteam/wording.py` | new in this repo (never in qortime); built Wed Oct 28 2026, in the event window. Calls the pre-existing verifier and transparency-log code (`qor_receipt`, pinned at 0e87ec3) unchanged; reads only public qortime.com match files and the referee's public log. Fixtures: the public 170123 `match.json` and log-inclusion proof, fetched Oct 28 2026 | Oct 28 |
| `qortime_ai/commentary/*`, `tests/test_commentary_witness.py`, `tests/fixtures/commentary/170123_clips_manifest.json`, `web/commentary-witness-view.js`, `web/commentary-witness.test.mjs`, `examples/170123/commentary_witness.json`, `docs/COMMENTARY_WITNESS.md`; commentary-witness lines in `web/demo.html`, `web/demo-170123.mjs`, README | new in this repo (never in qortime); built Wed Oct 28 2026, in the event window. Inputs: QorCap's three **public** 170123 highlight clips and their public manifest (copied as the test fixture) + the pre-existing receipt; Muse Voice Transcribe 1.0 + Muse Spark 1.3 outputs from Oct 28 2026. No audio files are committed | Oct 28 |
| `qortime_ai/stickecho/*`, `tests/test_stickecho.py`, `tests/test_stickecho_checks.py` (free local checks, added Oct 28), `examples/practice-stickecho/*`, `docs/STICK_ECHO.md`, `docs/stick-echo/*`; Stick Echo lines in README, `docs/README.md`, `examples/README.md` | new in this repo (never in qortime); built Wed Oct 28 2026, in the event window, from a private prototype written Oct 27–28 2026. Inputs: three private offline practice games (video and controller logs kept private, only totals published); SAM 3.1 outputs from Oct 28 2026 | Oct 28 |
| `qortime_ai/ai_ruling/guardrail.py`, `qortime_ai/redteam/wording.py` ("human proof" / "proof of human" / "proves a human" rules), `qortime_ai/ai_ruling/explainer.py` (prompt wording for the controller-timing advisory), `tests/test_agent_api.py` | in this repo; edited Wed Oct 28 2026, in the event window ([#24](https://github.com/ConWan30/qortime-ai/pull/24), [#25](https://github.com/ConWan30/qortime-ai/pull/25)). The 220105 Muse Spark explanation on qortime.com was re-generated and re-signed with these rules on Oct 28 | Oct 28 |

## Event-built edits to pre-existing qortime files (stay upstream, not copied here)
Small hooks that wire the code above into the existing referee and verifier page:
`verify/index.html`, `verify/viewer-ui.js`, `verify/viewer.css`, `verify/test.mjs` (#89, #92, #93, #95, #96);
`qor_receipt/review/engine.py`, `qor_receipt/referee_service/app.py`, `docs/REFEREE_SERVICE.md` (#96, #98).

## Other in-window work NOT in this repo (non-Meta fixes to pre-existing code)
**Used by the live referee that reviewed 220105 (Oct 27 2026)** (times CT):
- qorcap [#116](https://github.com/ConWan30/qorcap/pull/116) (Mon Oct 26, 10:08 PM) fixed the QorCap end-menu reader, which had failed to read the home score on online FINISH GAME menus (`home_glyph_count`).
- qortime [#104](https://github.com/ConWan30/qortime/pull/104) (Mon Oct 26, 10:17 PM) bans CIRCLE/CROSS in challenge patterns and pins the referee's copy of that reader to qorcap #116. So the end-menu read that confirmed 220105's final used this in-window reader fix. The fallback logic itself is pre-existing at `0e87ec3`: read the end-of-game menu when the tail has no fourth-quarter scorebug, then check it against the last locked score.
- qortime [#106](https://github.com/ConWan30/qortime/pull/106) (Mon Oct 26, 11:43 PM) adds motion rule v4.
- qortime #105 records QorCap 0.3.38 as the current recorder version.

**Not used by the referee:** qortime #91 (handoff note), #100/#102/#103 (site UI), #107/#108 (HACKATHON.md, removal of the
public page of match 021003, README contact); qorcap #117–#119 (v0.3.38 release, HACKATHON.md, README contact). Match 021003
(Oct 17, before the event) was SELF-SIGNED: the referee rejected it with HTTP 422, so it was never referee-verified and is not
in the referee log. Its public page was removed because the signed receipt carried on-screen player names. The receipt was not
edited.

## Referee log entries without a match page
The referee's public log ([`/v1/log`](https://qortime-referee-production.up.railway.app/v1/log)) has 6 entries, seq 0–5.
Of these entries, only the VERIFIED matches have a public page. (The public FAIL page 125430 is from Oct 16, before the log existed.)

| seq | Match (date, CT) | Submission | Status | Page |
|---|---|---|---|---|
| 0 | 170123 (Oct 23, pre-event) | `875c039ae35b7e97` | PARTIAL (`motion_correlation_low` under the earlier motion rule) | none; superseded by seq 1 after the pre-event motion rule v3 (qortime #62) |
| 1 | 170123 (Oct 23, pre-event) | `64a1a54b77948a49` | VERIFIED | [qortime.com/matches/170123](https://qortime.com/matches/170123/) |
| 2 | 205511 (Oct 26) | `273b29cdf6aae3c4` | PARTIAL (`final_reread` partial) | none (not published) |
| 3 | 205511 (Oct 26, resubmitted after the reader fix) | `7cf6c838410de4c8` | PARTIAL (`motion_correlation_low`) | none (not published); an offline re-score under motion rule v4 was also below the floor |
| 4 | 220105 (Oct 27) | `1d424dc2836f1a8c` | VERIFIED | [qortime.com/matches/220105](https://qortime.com/matches/220105/) |
| 5 | 142909 (Oct 28) | `0141a42daa807fe9` | PARTIAL (final read unconfirmed, motion low) | none (not published) |

The seq, match and submission columns come from the public log. The statuses come from the referee's answers at the time;
they are not on any public page. No PARTIAL or FAIL result was republished or edited, and no footage or player names are
published.
