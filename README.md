# QorTime AI — Meta Muse explains the referee's result, it never decides it

**Meta Global AI Developer Hackathon (Cerebral Valley), Indie Developer track. Solo build by Contravious Battle.**
This repository contains **only work built during the event (Mon Oct 26 – Wed Nov 4, 2026)**. QorTime's pre-existing
code is kept out; it is fetched at a pinned pre-event commit when you run or test this repo (see below).

**Demo video (2:58):** `[DEMO VIDEO LINK — PLACEHOLDER: YouTube not uploaded yet]`. It opens with one line on what was pre-existing and
what was built this week. **Judges: verify it in 2 minutes** → [For judges](#for-judges-verify-in-2-minutes).

QorTime is anti-cheat and verified skill for console head-to-head matches (not a coach; no play advice). A
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
| Receipt explainer: verifier results → plain-English explanation, fail-closed, deterministic guardrail (exact status, no device-proof overclaims, no coaching, no identity claims) | `qortime_ai/ai_ruling/explainer.py`, `guardrail.py`, `muse.py`, `__main__.py` | Muse Spark 1.3 | none |
| Separate AI **advisory** signing key (never a referee key) + signed sidecar bound to the receipt hash | `qortime_ai/ai_ruling/signing.py`, `advisory_keys.json`, `web/ai_advisory_keys.inc.js` | — | none |
| Score cross-check: Muse Spark is a second reader of every locked score | `qortime_ai/ai_ruling/score_crosscheck.py`, `web/score-crosscheck-view.js`, `web/lower-only.js` | Muse Spark 1.3 | lower only (VERIFIED → PARTIAL) |
| Scorebug locator for viewers | `qortime_ai/ai_ruling/sam_scorebug.py` | SAM 3.1 | none (info only) |
| Show Your Hands: verified-input overlay + press-to-pixel check; Muse play-start filter can only remove candidates | `qortime_ai/hands/`, `web/hands-view.js` | Muse Spark 1.3 | lower only, capped at PARTIAL |
| Automatic advisory job run by the referee after the verdict is final (caps, kill switch, retries) | `qortime_ai/ai_ruling/auto.py` | Muse Spark 1.3 | none (never delays or changes it) |
| Advisory fetch from the referee + verifier auto-pin of trusted referee keys | `web/advisory-fetch.js`, `web/auto-pin.js`, `web/AUTO_PIN.md` | — | none |
| Browser panels for the three signed advisory files | `web/*-view.js`, `web/advisory-panels.css`, `web/demo.html`, `web/demo-170123.mjs` | — | display only |
| Demo-video captions timed by ASR | `demo_pipeline/captions/` | Muse Voice Transcribe 1.0 | n/a (video only) |
| Red-Team the Referee: Muse Wonder writes 26 receipt-tampering attacks (cached), the pre-existing verifier judges them against fresh TEST keys, as an outside attacker and as an insider holding the TEST signing keys; Muse Spark explanations must cite a field in every sentence, checked by code + banned-word filter | `qortime_ai/redteam/`, `examples/redteam/` | Muse Wonder 1.0, Muse Spark 1.3 | none (attacks the verifier; never edits it) |
| Signed advisory files for match 170123 | `examples/170123/{ai_ruling,score_crosscheck,hands}.json` | Muse Spark 1.3 | — |
| "What the referee saw" Evidence Lens: SAM 3.1 video-tracks the scorebug from the referee's own OCR region, motion split players / HUD / rest, `seen.v0` sidecar, cited Muse Spark captions, overlay render + web panel (details below) | `qortime_ai/seen/`, `web/seen-view.js`, `examples/170123/seen.json`, `examples/170123/seen/` | SAM 3.1, Muse Spark 1.3 | none (visualization, not a referee input) |
| Challenge Echo: SAM 3.1 tracks the pause-menu highlight; each logged D-pad press must be echoed on screen (latency, directions matched, menu after OPTIONS), `echo.sidecar.json` | `qortime_ai/echo/`, `web/echo-view.js`, `examples/practice-echo/` | SAM 3.1 | info only; a mismatch can at most lower VERIFIED → PARTIAL |

File-by-file origin (qortime PR numbers): [`PROVENANCE.md`](PROVENANCE.md).

## How Meta models are used
- **Muse Spark 1.3** — (1) writes the plain-English explanation of the referee's result; a deterministic guardrail
  rejects any text that misstates the status or makes banned claims, and the result is signed with an advisory key;
  (2) independently re-reads the scorebug at every locked score: agree = no change, disagree = VERIFIED → PARTIAL,
  unsure/unavailable = "Muse unchecked", no penalty; (3) filters Show Your Hands play-start candidates (remove-only).
  On match 170123: 2 of 2 checked locked scores agree (third: unsure → unchecked), ~$0.009 for 6 reads.
- **SAM 3.1** — boxes the scorebug for viewers, and video-tracks the scorebug + players for the "What the referee saw"
  Evidence Lens (below), and the pause-menu highlight for Challenge Echo. Info only; never a status signal.
- **Muse Voice Transcribe 1.0** — event-stream ASR of the demo narration; each partial's `audioProcessedMs` times the
  burned-in captions (`demo_pipeline/captions/make_srt.py`, reproduces `data/vo-v6-captions.srt` byte-for-byte).
- **Muse Wonder 1.0** — red-team attacker: proposes receipt tampering attacks as structured JSON mutations (see below).
- Keys come only from the environment (`META_API_KEY`); nothing in this repo contains a key.

## For judges: verify in 2 minutes
1. **No install, real match:** open the public verifier on the pre-existing VERIFIED match 170123 (signed Oct 23 2026):
   https://qortime.com/verify/?receipt=https%3A%2F%2Fqortime.com%2Fmatches%2F170123%2Freceipt.json&referee=b283cffb9279f2f90859268c64ef21861ef7e5d9fc773bdb8061af0e80624889
   → gold **VERIFIED** (away 10 – home 0), then the event-built panels: signed Muse Spark explanation, "Muse Spark agrees
   with 2 of 2 checked locked scores", Show Your Hands. The verifier and match page are pre-existing; the panels are this repo.
2. **Offline, from this repo** (no API key, ~2 min): run the first block in [Run it](#run-it), then `node web/demo-170123.mjs`.
   Expected: `verdict (verify.js, deterministic): VERIFIED`, `after lower-only advisory signals: VERIFIED (unchanged)`,
   `Muse Spark score cross-check: "Muse Spark agrees with 2 of 2 checked locked scores"`, then the signed explanation text.
3. **Red team:** `python -m qortime_ai.redteam` → `Outside attacker: 25 attacks · 0 accepted` (offline, cached Muse Wonder output).
4. **Evidence Lens:** open `examples/170123/seen/hl01-q4-a9-h0.seen.mp4`, or `web/demo.html` (bottom panel) via the local server.
5. **AI can't decide:** `pytest -q tests/test_ai_ruling_signing.py tests/test_score_crosscheck.py` — deleting or tampering
   with the AI sidecars never changes the verdict; disagreement only lowers VERIFIED → PARTIAL.

## What the referee saw (SAM 3.1 Evidence Lens) — visualization only
Built Oct 27 2026, in the event window. `qortime_ai/seen/` chains the deterministic referee into Meta SAM 3.1 video
tracking on QorCap's three **public** match-170123 highlight clips (12 s each):
1. **Box prompt = the referee's own scorebug OCR region** (`madden27_standard`, 640×360: 8,340–485,359), forward
   propagation, one object id. Reports, per chain segment, how many frames the scorebug stayed *in place* (≥ 50 % of the
   OCR region inside SAM's mask), how far its anchor edges moved, and any dropouts / swaps. hl00 and hl01: 359/359 and
   360/360 frames in place, anchor moves ≤ 2 px. hl02: in place on 249/360 frames, until 8.3 s (the lock is at 8.0 s); the game then swaps
   in a "scoring drive" graphic and SAM's object leaves the OCR region — shown, not judged.
2. **Concept prompt "football player"** used ONLY to split the referee's own frame-difference energy (as in
   `motion_series`) into players / HUD / rest of screen. Aggregate percentages only — never per-player data, routes,
   speeds or play quality. On these clips most motion energy is camera and field movement (players 0–21 % per segment).
3. **`examples/170123/seen.json` (schema `seen.v0`)**: receipt JCS sha256, segment seqs + segment sha256s from the
   highlight manifest, SAM model and prompt types, summary numbers, Muse Spark captions, and the sha256 of each rendered
   overlay. No per-frame masks or boxes, no status field; receipt.v0 is unchanged. The receipt does not publish which
   segments the motion rule's random draw sampled, so seen.json says these are the chain segments the clips cover.
4. **Muse Spark 1.3** writes one caption per segment citing seen.json / receipt fields in `[brackets]`; the red-team
   citation checker + banned-word filter + a "not a coach" lint run after the model, with a template fallback.
5. **Evidence Lens render** (`python -m qortime_ai.seen … --render DIR`): a holographic box that materializes
   (corner brackets, glow, one scanline sweep, ~300 ms), follows SAM's track, and dissolves (~400 ms) **only inside
   receipt event windows** — the score-lock checkpoint (tag `SCORE READ AWAY 9–HOME 0 · [checkpoints.away[459]]`), the
   lock's segment (`MOTION SEGMENT 448 · players 9% · [signals.motion_permille.away]`) and any challenge window. Aqua by
   default; **gold only for a score lock when the pre-existing verifier returns VERIFIED**. Corner label:
   "SAM 3.1 · visualization, not a referee input". Web: `web/seen-view.js` (canvas lens, reduced-motion = static frame),
   shown at the bottom of `web/demo.html`; tests in `web/seen-view.test.mjs` and `tests/test_seen.py`.
Sample: `examples/170123/seen/` (stills + the 3.2 MB hl01 overlay). Cost: SAM 3.1 6 × 360 frames ≈ $0.43; Spark captions
≈ $0.05. Paid steps: `python -m qortime_ai.seen.fetch` (SAM, outputs cached outside the repo) and `--spark`.

## Challenge Echo (SAM 3.1) — info only, lower-only
**Built Oct 27 2026, during the hackathon week.** During a pause challenge the player presses OPTIONS, enters the
D-pad pattern on the pause menu, then selects Resume. `qortime_ai/echo/` checks that the **video follows the input
log**: every logged D-pad press must be followed by the matching move of the pause-menu highlight.
- **What SAM 3.1 does:** tracks the pause-menu highlight box. Only the menu window is sent, only the menu-list column
  (left 30 % × top 47 % of the frame, nothing player-identifying), at 30 fps; a **box prompt** on the first menu frame
  seeds one object and SAM propagates it forward. The track is the box's centre row.
- **What is deterministic code (not SAM):** press edges from `inputs.jsonl`; finding the highlight box that seeds the
  prompt; "menu appeared" (whole-frame luma goes dark after OPTIONS); the matching. A deterministic tracker (bright
  rows of the highlight box) is the fallback when SAM is off or fails, and a cross-check: on the practice set SAM and
  the fallback agree on 98–100 % of frames in 9 of 10 windows (72 % in the sloppy one, where a sub-menu opens).
- **Matching:** DOWN/UP must move the highlight one row (wrap included) within ±100 ms of the window's common lag;
  LEFT/RIGHT do nothing on this vertical menu, so Echo only checks the highlight held still (counted, marked
  `visible: false`). Per press: press-to-pixel latency in ms. Per window: directions matched N of M, jitter, and
  whether the menu appeared after the OPTIONS press. Latencies are reported against the known 0.5–2.4 s capture/relay gap.
- **Effect:** `echo.sidecar.json` (schema `qortime.echo.v0`, integers only, next to the receipt; `receipt.v0.json` is
  untouched). `consistent` / `partial` / `unscorable` add a note only; `mismatch` can suggest VERIFIED → PARTIAL and
  nothing else (`qortime_ai/echo/sidecar.py`, tests). The browser panel (`web/echo-view.js`) is info-only and never
  changes the status. The live referee and its challenge check are not changed.

Practice run (10 pause challenges from one practice game, video and inputs kept private; aggregates in
`examples/practice-echo/echo.sidecar.json`): **8 consistent, 2 partial, 0 mismatch.** Median press-to-pixel per window
0.94–1.70 s, jitter inside a window ≤ 44 ms. The sloppy window (D-pad DOWN pressed six times, no LEFT/RIGHT/UP) comes out
`partial`, 1/4 directions; its six DOWN presses all line up with six highlight moves. One other window is `partial`
because the private extract has no release reports, so two quick DOWN presses read as one. The offset between the
video and input clocks was calibrated from the OPTIONS → pause-menu latency (see the sidecar's `clock`); absolute
latencies move with that offset, the jitter inside a window does not. The video also showed that the logged bit
8192 is DOWN (not LEFT), as in `hands/track.py`. Cost: SAM 3.1, 1,571 frames ≈ $0.31 including one probe.
```bash
META_API_KEY=... python -m qortime_ai.echo VIDEO inputs.jsonl --video-start-us T0 --pattern LEFT,DOWN,RIGHT,UP \
  --receipt receipt.v0.json --cache /private/cache --ledger spend.jsonl      # --no-sam = deterministic tracker only
```
Tests: `tests/test_echo.py` (synthetic presses, tracks and a drawn synthetic video), `web/echo.test.mjs`.

## Red-Team the Referee
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

## Run it
Requires Python ≥ 3.10, Node ≥ 20, git. No API key needed for tests or the demo.
```bash
./scripts/fetch_upstream.sh            # pre-existing qortime @ 0e87ec3 -> upstream/ (git-ignored) + 170123 receipt
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'                # installs the pinned pre-existing qor-receipt library as a dependency
pytest -q                              # 216 passed, 5 skipped (referee-hook integration tests live upstream)
npm test                               # 7 browser-module test files, 153 checks
node web/demo-170123.mjs               # offline: verdict from verify.js, then the signed Muse files, lower-only
python -m http.server 8000             # from the repo root; then open http://localhost:8000/web/demo.html
```
(Counts re-checked with Challenge Echo added, Tue Oct 27 2026.) Optional overlay render needs `pip install -e '.[seen]'`
and ffmpeg on PATH. `demo_pipeline/captions/transcribe_stream.py` needs `requests` (`pip install -e '.[captions]'`; also in `[dev]`).
Live Muse Spark explanation (needs a Meta Model API key):
```bash
META_API_KEY=... python -m qortime_ai.ai_ruling examples/170123/receipt.json --no-write \
  --pub b283cffb9279f2f90859268c64ef21861ef7e5d9fc773bdb8061af0e80624889
```
The production integration (the referee's background hook and the verifier page at https://qortime.com/verify/) is a
small set of edits to pre-existing qortime files and stays in that repo (see `PROVENANCE.md`).

## Models, services and open-source used
**Meta models** (all called through the Meta Model API, `https://api.meta.ai/v1`, key from `META_API_KEY`):
| Model | Called from | Endpoint |
|---|---|---|
| Muse Spark 1.3 (`muse-spark-1.3`) | `qortime_ai/ai_ruling/muse.py`, `score_crosscheck.py`, `hands/muse_context.py`, `redteam/generate.py`, `seen/build.py` | `/chat/completions` |
| SAM 3.1 (`sam-3.1`) | `qortime_ai/ai_ruling/sam_scorebug.py`, `qortime_ai/seen/sam_video.py`, `qortime_ai/echo/video.py` | `/responses` |
| Muse Wonder 1.0 (`muse-wonder-1.0`) | `qortime_ai/redteam/generate.py` (one live run; output cached in `fixtures/wonder_attacks.json`) | `/chat/completions` |
| Muse Voice Transcribe 1.0 (`muse-voice-transcribe-1.0`) | `demo_pipeline/captions/transcribe_stream.py` | `/asr/transcribe` |
No other Meta model (e.g. Muse Image) is used.

**Open-source used by this code:** `cryptography`, `numpy`, `opencv-python-headless`, `pillow`, `meta-sam-parser`
(SAM output parsing), `requests` (caption script), and for tests `pytest`, `fastapi`, `httpx`; FFmpeg (frame extraction,
overlay encode, caption silence detection); Node.js ≥ 20 (browser-module tests); DejaVu fonts (overlay text). Pre-existing,
not in this repo: `qor-receipt` from [ConWan30/qortime@0e87ec3](https://github.com/ConWan30/qortime/commit/0e87ec3).

**Used only to make the demo video (not in this repo, never part of the referee):**
- xAI text-to-speech, voice "Rex": narration (AI voice)
- Grok Imagine: AI-generated cold open and phone callback, labelled DRAMATIZATION on screen (the phone screen shows the
  real qortime.com verifier output for match 170123, composited)
- Remotion: animated Meta-models / roadmap / "what this doesn't prove" section; headless Chrome: card stills; FFmpeg + x264: edit and encode
- Sound effects and music: original, synthesized with NumPy for this video. (ElevenLabs sound effects were used only in
  early cuts and were all replaced; none are in the final video.)
- Captions: timed with Muse Voice Transcribe (`demo_pipeline/captions/`; the committed data reproduces the v6 narration
  captions — the final cut's extra beats were timed the same way)

## Rules this code keeps
- The verdict comes only from the deterministic verifier. AI output lives in separate signed sidecars; deleting or
  tampering with them never changes the verdict (tests check this).
- The receipt format is frozen; new data goes in sidecars.
- No device-proof overclaims (banned list in `qortime_ai/redteam/wording.py`); device status is at most "TPM claimed (unverified)".
- QorTime does not prove who held the controller and does not catch collusion.
- No secrets, raw match footage, raw controller logs, gamertags, OCR weights or held-out game data in this repo.

## Creator & contact

Built by **Contravious Battle**, solo founder, QorTime.

- Email: [qoresence@mail.grokbot.com](mailto:qoresence@mail.grokbot.com) (project inbox)
- LinkedIn: [linkedin.com/in/contravious-battle-b8a25a445](https://www.linkedin.com/in/contravious-battle-b8a25a445)
- X: [@ConWanZo](https://x.com/ConWanZo) (personal) · [@QorTimeHQ](https://x.com/QorTimeHQ) (project)
- GitHub: [ConWan30](https://github.com/ConWan30)

## License
MIT (see `LICENSE`). Not affiliated with Meta, EA, the NFL or Sony. Madden NFL is a trademark of its owner.
