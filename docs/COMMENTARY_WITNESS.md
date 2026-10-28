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
| `disagree` | commentary is present in the window, nothing matches, and a high-confidence, keyword-backed call there names a different play (or a resolved team names the other side) |
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

## Data retention: unconfirmed
Audio is sent to the Meta Model API's Voice Transcribe endpoint with `zdrOverride` left at the API default. Meta's data
retention for this endpoint has **not been confirmed** for this project. Only already-public clips were sent.

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
Full recordings (e.g. 170123 or 220105) need the original QorCap recording with its game-audio track and lock times on
that recording's timeline. These live on the capture laptop, not in any public repo.
