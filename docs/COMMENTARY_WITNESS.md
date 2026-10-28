# Commentary witness: the broadcast booth as an info-only second witness

**Built Oct 28 2026, in the event window (Meta AI Developer Hackathon, Oct 26 – Nov 4 2026).** Code:
[`qortime_ai/commentary/`](../qortime_ai/commentary/), [`web/commentary-witness-view.js`](../web/commentary-witness-view.js).
Tests: [`tests/test_commentary_witness.py`](../tests/test_commentary_witness.py), [`web/commentary-witness.test.mjs`](../web/commentary-witness.test.mjs)
(both Meta APIs mocked, no key needed). Example: [`examples/170123/commentary_witness.json`](../examples/170123/commentary_witness.json).

Madden NFL's broadcast commentators call scores aloud ("And this kick is good", "Touchdown!", "Extra point").
The commentary witness turns a recorded match's game audio into a timeline of called scoring plays and lines it up
with the referee's locked scores. It is **information only**: the verdict still comes from the pre-existing
deterministic verifier. AI explains; it never decides.

## Pipeline
1. **Audio.** FFmpeg extracts mono 16-bit PCM at 24 kHz to a temp dir (never kept, never committed). A peak level below
   −50 dB (muted commentary) or no audio track gives **unchecked**.
2. **Meta Muse Voice Transcribe** (`muse-voice-transcribe-1.0`, `POST https://api.meta.ai/v1/asr/transcribe`,
   `ENDPOINTING` mode) returns speech segments with start/end times. Recordings longer than 9 minutes are split into
   chunks under the API's 10-minute limit. Control tokens such as `<|speaker_A|>` are stripped.
3. **Meta Muse Spark** (`muse-spark-1.3`, standard mode, never `-contributor`; `/chat/completions`, strict JSON schema)
   lists the scoring plays the commentators call: type (TD / FG / XP / 2PT / SAFETY), the segment number, a verbatim
   quote, the team name if one is said, and high/low confidence.
4. **Code, not the model, checks and matches:**
   - A call is kept only if its quote appears in that segment's transcript.
   - **Timestamps are speech-segment start/end only.** The API has no word timestamps; the model picks a segment, and
     the times come from the segment.
   - A call is high confidence only if the model says so **and** its segment literally names the play ("touchdown",
     "field goal", "extra point"/"PAT", "two-point"/"conversion", "safety"). Low-confidence calls can agree but can
     never cause a disagreement.
   - Repeat calls of the same play type within 20 s are merged into one play (`mentions` counts them).
   - **Team:** resolved to away/home only from team names in match data. Match data for 170123 has no team names, so
     every call there is `unresolved`. Teams are never guessed, and an unresolved team never causes a disagreement.
   - Each referee score lock is matched by **time window (±15 s) + play points** (a 7- or 8-point lock may match
     TD + XP / TD + 2PT).

## Results per lock and for the match
| Lock result | When |
|---|---|
| `agree` | a call in the window has the lock's points |
| `disagree` | commentary is present in the window, nothing matches, and a high-confidence, keyword-backed call there names a different play (or a resolved team names the other side), and that call does not fit a neighbouring lock |
| `unchecked` | muted/absent commentary, no speech in the window, no call, only low-confidence calls, ASR or Muse failure, no key |

Match line: **broadcast agrees** (no disagreeing lock, at least one agreeing), **broadcast disagrees** (any disagreeing
lock → `cap: "PARTIAL"`, VERIFIED shown as PARTIAL), or **broadcast unchecked** (no penalty). `apply_cap` refuses any
cap other than PARTIAL, so nothing here can raise a status or produce FAIL. Calls with no lock nearby are listed as
`unmatched_calls` for information (replays and recaps cause these); they never change anything.

The sidecar `commentary_witness.json` (`qortime.commentary_witness.v0`, `affects_verdict: "lower_only"`,
`max_cap: "PARTIAL"`) is modeled on `score_crosscheck.json`: signed with the AI advisory key (never a referee key),
bound to the receipt's JCS hash, and checked in Python (`check_witness`) and in the browser (`checkWitness`). Wording in
the label and summary is checked with the `wording.py` / `guardrail.py` banned-term lists plus a rule against money-at-risk wording;
a transcript segment or quote that trips them is withheld.

**Runs offline on recorded matches only.** The live referee never calls it, `qortime_ai/ai_ruling/auto.py` does not
import it, and `verify_receipt` / `verify.js` are unchanged.

## Measured on 170123 (3 public clips, 12 s each, 36 s of audio)
Inputs: QorCap's three public highlight clips of match 170123 (`site/matches/170123/clips` in ConWan30/qortime) and
their manifest's locked scores: away FG (0→3, Q3), away TD (3→9, Q4), away XP (9→10, Q4).

| Run (Oct 28 2026) | Result |
|---|---|
| First pipeline run | 2 of 3: FG and TD agree; the XP clip ("Extra point." … "Accuracy perfect there … makes this a 10 point game") was called **FG** by Muse Spark → a false disagreement |
| After one prompt revision (context rule for XP) + the keyword-backed confidence rule | **3 of 3 agree**, 0 disagree, 0 unmatched calls, TD's two "touchdown" mentions merged into one play |

The published example is the second run. **Both runs used the same three clips, so this is a development check, not a
held-out test.** Clips are cut around score changes, so they are biased toward hits: **the false-call and miss rate over
a full game has not been measured yet.** The FG call ("this kick is good") and the XP call are low confidence (no
"field goal"/"extra point" in the cited segment), so on these clips they could agree but could not have disagreed.
Voice Transcribe output also varies slightly between runs (e.g. "KC Concepcion" vs "Casey Concepcion").

Cost and time: 3 Voice Transcribe calls + 3 Muse Spark calls; Muse Spark ≈ $0.008 (tokens); Voice Transcribe price not
recorded. About 21 s wall-clock for 36 s of audio (sequential; ASR alone measured 12.5–17.8 s per audio-minute).

## Full games (Oct 28 2026): 170123 and 220105
Each full match recording's audio track (private, not published) went through the merged module (PR #12). Locks come
from QorCap's score timeline, moved onto the recording clock using the receipt's checkpoint span (about ±1 s; for
170123 this matches the public clips' lock times within 0.6 s). 11 scoring plays in total.

| Game | Audio | Speech found | Locks | Run 1 (PR #12 code) | Run 2 (after the fix below) |
|---|---|---|---|---|---|
| 170123 | 17.4 min | 128 segments, 514 s | FG, TD, XP | FG agree (low), TD agree, **XP: false disagreement** → "broadcast disagrees 1 of 3" | FG agree, TD agree, XP unchecked → **broadcast agrees 2 of 2** |
| 220105 | 29.2 min | 34 segments, 180 s, nearly all in the first 7.5 min | 4 × (TD, XP) | TD agree, XP agree (low); 6 locks unchecked | same |

Per scoring play (run 2): **4 hits, 1 miss, 6 unchecked, 0 false calls.**
- **Miss (170123 XP):** the commentators said "for the extra point. The extra point." and "makes this a 10 point game",
  but Muse Spark, reading the whole 128-segment game transcript in one request, listed no extra point. (On the 12 s
  clip it did.) Not fixed: a change aimed at this one call would be tuning against the test game.
- **False disagreement (run 1, 170123 XP):** the touchdown call 12 s before the extra-point lock fell inside the
  extra-point lock's ±15 s window and counted as a conflicting call. **Fix (this is the one change):** a call that fits a
  *neighbouring* lock (same side, in that lock's window, its points or part of a TD+XP/TD+2PT combo) never counts as a
  conflict at this lock. A call that fits no lock still does. Re-scored from the cached run-1 transcript and Muse output,
  no new model calls. Also: a call counts as `matched` only if it agreed with a lock (before, merely being near one was enough).
- **Unchecked (220105, 6 locks):** Voice Transcribe found no speech after about 7.5 minutes except two fragments. A
  check on 600–720 s returned an empty transcript although the audio level was like the earlier minutes (game sound
  present). Commentary appears to stop; the cause is unknown (nobody listened to confirm). These count as unchecked, never
  as disagreements, as designed.
- **Calls with no matching score:** none. Near-score and recap lines were not called: "field goal range", "those
  field goals are far from a certainty", "makes this a 10 point game", "seven nothing is our score as this kick is
  sent into the air" (a kickoff). No replay produced a call, so no replay suppression was added.
- **Runtime:** 170123 147 s wall (8.5 s per audio-minute; Voice Transcribe 143 s over 2 requests, Muse Spark 3.5 s);
  220105 174 s (6.0 s per audio-minute; 4 requests, Muse Spark 2.8 s). Meta calls: 6 Voice Transcribe + 2 Muse Spark
  (≈ $0.013 Muse tokens), plus 1 Voice Transcribe diagnostic request.

Published sidecars (quotes only, no transcript, `quotes_only=True`):
[`examples/170123/commentary_witness.full_game.json`](../examples/170123/commentary_witness.full_game.json),
[`examples/220105/commentary_witness.full_game.json`](../examples/220105/commentary_witness.full_game.json). They keep
segment counts and four short quoted score calls; no gamertags or player-entered names. Still not measured: games with
replays of scoring plays, and how often a confident wrong call happens. Two games is not a rate.

## Data retention: unconfirmed
Audio is sent to the Meta Model API's Voice Transcribe endpoint with `zdrOverride` left at the API default. Meta's data
retention for this endpoint has **not been confirmed** for this project. The public clips and, on Oct 28 2026, the two
full-game audio tracks (170123, 220105) were sent.

## Not claimed
Not a referee input. It says nothing about who was playing or whether a person was playing at all. A broadcast call is commentary
generated by the game; agreement says only that the game's own commentary track called the same scoring plays.

## Run it
```bash
export META_API_KEY=...   # never commit it
# public clips (QorCap highlight manifest + mp4s)
python -m qortime_ai.commentary examples/170123/receipt.json --clips PATH/TO/qortime/site/matches/170123/clips \
  --match PATH/TO/match.json --sign-key ADVISORY.key --out commentary_witness.json
# a full recording: locks.json = [{"id", "t_ms", "team": "away"|"home", "points"}] on the recording's timeline
python -m qortime_ai.commentary RECEIPT --audio match.mp4 --locks locks.json --sign-key ADVISORY.key
```
Full recordings need the QorCap recording's game-audio track and lock times on that recording's timeline (private;
use `--quotes-only` for any sidecar that will be published).
