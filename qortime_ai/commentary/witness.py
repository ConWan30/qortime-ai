"""Commentary witness (``commentary_witness.json``, ``qortime.commentary_witness.v0``). INFO ONLY, LOWER-ONLY.
Built Oct 28 2026 during the Meta AI Developer Hackathon (Oct 26 - Nov 4 2026). Runs offline on recorded matches; the
live referee never calls it and ``verify_receipt`` is unchanged.

Pipeline: game audio -> Meta Muse Voice Transcribe (speech segments) -> Meta Muse Spark lists the scoring plays the
commentators call (TD / FG / XP / 2PT / SAFETY), citing a segment and a verbatim quote -> code checks the quote,
merges repeat calls of one play, and matches each referee score lock by time window + play points.

Rules (tests: tests/test_commentary_witness.py):
* Timestamps are speech-segment start/end only (the API has no word timestamps). The model picks a segment id; the
  times come from the segment, never from the model.
* A call is kept only if its quote appears in that segment's transcript (no invented calls).
* A call counts as high confidence only if the model says so AND its segment literally names the play ("touchdown",
  "field goal", "extra point"/"PAT", "two-point"/"conversion", "safety"). Low-confidence calls can agree but can never
  cause a disagreement.
* Repeat calls of the same play type within ``MERGE_GAP_MS`` are one play.
* Team: resolved only from team names present in match data. With no names (170123) the team is "unresolved"; it is
  never guessed, and an unresolved team never causes a disagreement.
* Per lock: ``agree`` = a call in the window whose points match the lock's score change (TD+XP / TD+2PT may combine).
  ``disagree`` = commentary is present in the window, nothing matches, and a HIGH-confidence call there says a
  different play (or a resolved team says the other side). Anything else is ``unchecked``.
* Muted or absent commentary, no speech in the window, ASR or Muse failure, no key: ``unchecked``, never ``disagree``.
* Any disagreeing lock => ``cap: "PARTIAL"`` (VERIFIED -> PARTIAL on display). Nothing here raises a status or FAILs.
* A call that fits a NEIGHBOURING lock (the touchdown call 10-15 s before the extra-point lock) never counts as a
  conflict at this lock. Added Oct 28 2026 after the first full-game run (doc: "Full games").
* Calls that agree with no lock are listed as ``unmatched`` (information only; replays and recaps cause these).
* ``quotes_only``: for private recordings the sidecar keeps only segment counts and short quoted score calls.
* AI explains, never decides: the verdict is the pre-existing verifier's. Wording is checked by ``wording.py`` and
  ``guardrail.py`` banned-term lists plus a no-gambling-words rule; a quote that trips them is withheld.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

from qortime_ai.ai_ruling import guardrail
from qortime_ai.ai_ruling.muse import BASE_URL, DEFAULT_MODEL, MuseError, api_key_from_env
from qortime_ai.ai_ruling.signing import receipt_jcs_sha256
from qortime_ai.commentary.asr import ASR_MODEL, _DIRECT, AsrError, Segment, VoiceTranscriber
from qortime_ai.redteam.wording import banned_hits

SCHEMA = "qortime.commentary_witness.v0"
FILENAME = "commentary_witness.json"
VERIFIED, PARTIAL = "VERIFIED", "PARTIAL"
CAP_CODE = "commentary_witness_disagrees"
BUILT = "Meta AI Developer Hackathon, Oct 26 - Nov 4 2026 (built Oct 28 2026)"
LABEL = ("INFO ONLY, LOWER-ONLY. Meta Muse Voice Transcribe turns the game's broadcast commentary into text and Meta "
         "Muse Spark lists the scoring plays the commentators call. Each call is compared with the referee's locked "
         "scores: 'broadcast agrees', 'broadcast disagrees' or 'broadcast unchecked'. A disagreement can only lower "
         "VERIFIED to PARTIAL; it never raises a status and never fails a match. The referee decides; AI only explains.")
DATA_RETENTION = ("Unconfirmed. Audio is sent to the Meta Model API (muse-voice-transcribe-1.0) with zdrOverride left "
                  "at the API default; Meta's retention for this endpoint has not been confirmed for this project.")
POINTS = {"TD": 6, "FG": 3, "XP": 1, "2PT": 2, "SAFETY": 2}
COMBOS = {7: ("TD", "XP"), 8: ("TD", "2PT")}   # a scorebug lock can land after the try
PRE_MS, POST_MS = 15_000, 15_000                # lock window: commentary usually calls the play before the scorebug moves
MERGE_GAP_MS = 20_000
MAX_QUOTE_CHARS = 80
MUTED_MAX_DB = -50.0
USD_IN, USD_OUT = 1.25e-6, 4.25e-6
# A call can drive a DISAGREEMENT only if its own segment literally names the play (deterministic, not the model).
KEYWORDS = {"TD": r"touch\s*down", "FG": r"field\s*goal", "XP": r"extra\s*points?|\bpat\b|point\s*after",
            "2PT": r"two[\s-]*point|\b2[\s-]*point|conversion", "SAFETY": r"\bsafety\b"}
_GAMBLING = re.compile(r"\b(bet|bets|betting|wager\w*|odds|parlay\w*|sportsbook\w*|payouts?|stakes?|gambl\w*|bookie\w*|spread)\b", re.I)

SYSTEM = """You read speech segments transcribed from a Madden NFL broadcast commentary track. List ONLY scoring plays the commentators say HAVE HAPPENED in this audio.
Types: TD (touchdown), FG (field goal), XP (extra point / PAT), 2PT (two-point conversion), SAFETY.
- Ignore set-ups ("lining up for the kick"), predictions, replays described as earlier plays, and stat recaps unless the result of the current play is called.
- One entry per segment that calls a score. segment = the segment number. quote = the exact words from that segment that call it (copy them verbatim).
- team_said = the team or player name the commentators use for the scoring side, or null if none is said. Never guess a team.
- confidence = "high" only if the words clearly say the score happened; otherwise "low".
- Use neighbouring segments for context: a kick called right after "extra point" / "PAT" is XP, not FG. "Makes this a N point game" describes the new margin, not the play type.
- If no score is called, return {"calls": []}. You describe the audio; you do not decide anything about the match."""
RESPONSE_FORMAT = {"type": "json_schema", "json_schema": {"name": "scoring_calls", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["calls"],
    "properties": {"calls": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["segment", "type", "quote", "team_said", "confidence"],
        "properties": {"segment": {"type": "integer"}, "type": {"type": "string", "enum": list(POINTS)},
                       "quote": {"type": "string"}, "team_said": {"type": ["string", "null"]},
                       "confidence": {"type": "string", "enum": ["high", "low"]}}}}}}}}


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).split())


def text_problems(text: str | None) -> list[str]:
    """Banned-term codes (wording.py + guardrail.py lists + gambling words). Empty = may be shown."""
    t = text or ""
    hits = list(banned_hits(t))
    for rx, code in guardrail.BANNED:
        if rx.search(t) and code not in hits:
            hits.append(code)
    if _GAMBLING.search(t):
        hits.append("gambling")
    return hits


def _usd_micro(u: dict) -> int:
    return int(round((u.get("prompt_tokens", 0) * USD_IN + u.get("completion_tokens", 0) * USD_OUT) * 1e6))


def _post_json(url: str, key: str, body: dict, timeout_s: float) -> tuple[int, Any]:
    import urllib.error
    import urllib.request

    from qortime_ai.ai_ruling.muse import _error_code

    r = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                               headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with _DIRECT.open(r, timeout=timeout_s) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, _error_code(e)
    except Exception as e:  # noqa: BLE001
        raise MuseError(f"network:{type(e).__name__}") from None


class CallExtractor:
    """Muse Spark (non-contributor) reads the segments and lists called scores as JSON."""

    def __init__(self, *, api_key: str | None = None, model: str = DEFAULT_MODEL, base_url: str = BASE_URL,
                 max_tokens: int = 4000, timeout_s: float = 90.0, transport: Callable | None = None) -> None:
        if model != DEFAULT_MODEL:
            raise ValueError("only muse-spark-1.3 (standard, non-contributor) is used here")
        self._key = api_key if api_key is not None else api_key_from_env()
        self.model, self.base_url, self.max_tokens, self.timeout_s = model, base_url.rstrip("/"), max_tokens, timeout_s
        self._transport = transport or _post_json
        self.calls, self.cost_micro_usd = 0, 0

    def __repr__(self) -> str:
        return f"CallExtractor(model={self.model!r}, key={'set' if self._key else 'missing'})"

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    def extract(self, segments: list[Segment]) -> list[dict[str, Any]]:
        if not self._key:
            raise MuseError("api_key_missing")
        if not segments:
            return []
        user = "\n".join(f"{i}. [{s.start_ms / 1000:.1f}s-{s.end_ms / 1000:.1f}s] {s.text}" for i, s in enumerate(segments, 1))
        body = {"model": self.model, "temperature": 0, "max_completion_tokens": self.max_tokens, "reasoning_effort": "minimal",
                "response_format": RESPONSE_FORMAT,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
        self.calls += 1
        status, d = self._transport(f"{self.base_url}/chat/completions", self._key, body, self.timeout_s)
        if status != 200 or not isinstance(d, dict) or "_error_code" in d:
            raise MuseError(f"http_{status}")
        try:
            ch = d["choices"][0]
            if ch.get("finish_reason") == "length":
                raise MuseError("truncated_finish_reason_length")
            calls = json.loads(ch["message"]["content"] or "")["calls"]
        except MuseError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
            raise MuseError(f"malformed_response:{type(e).__name__}") from None
        u = d.get("usage") or {}
        self.cost_micro_usd += _usd_micro({k: u[k] for k in ("prompt_tokens", "completion_tokens") if isinstance(u.get(k), int)})
        return calls if isinstance(calls, list) else []


def validate_calls(raw: Iterable[Any], segments: list[Segment]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep calls whose segment exists, type is known and quote is in that segment. Times come from the segment."""
    kept, dropped = [], []
    for c in raw:
        if not isinstance(c, dict):
            dropped.append({"reason": "not_an_object"}); continue
        i, typ, quote = c.get("segment"), str(c.get("type") or "").upper(), str(c.get("quote") or "")
        if not isinstance(i, int) or isinstance(i, bool) or not 1 <= i <= len(segments):
            dropped.append({"reason": "bad_segment"}); continue
        if typ not in POINTS:
            dropped.append({"reason": "bad_type", "segment": i}); continue
        seg = segments[i - 1]
        if not _norm(quote) or _norm(quote) not in _norm(seg.text):
            dropped.append({"reason": "quote_not_in_segment", "segment": i}); continue
        ts = c.get("team_said")
        backed = bool(re.search(KEYWORDS[typ], seg.text, re.I))
        kept.append({"type": typ, "points": POINTS[typ], "start_ms": seg.start_ms, "end_ms": seg.end_ms,
                     "quote": quote.strip(), "team_said": ts.strip() if isinstance(ts, str) and ts.strip() else None,
                     "confidence": "high" if c.get("confidence") == "high" and backed else "low",
                     "keyword_backed": backed})
    return kept, dropped


def merge_calls(calls: list[dict[str, Any]], gap_ms: int = MERGE_GAP_MS) -> list[dict[str, Any]]:
    """Repeat calls of the same play type close together are one play (earliest start, latest end)."""
    out: list[dict[str, Any]] = []
    for c in sorted(calls, key=lambda x: (x["start_ms"], x["type"])):
        prev = next((p for p in reversed(out) if p["type"] == c["type"]), None)
        if prev and c["start_ms"] - prev["end_ms"] <= gap_ms and (c["team"] == prev["team"] or "unresolved" in (c["team"], prev["team"])):
            prev["end_ms"] = max(prev["end_ms"], c["end_ms"]); prev["mentions"] += 1
            prev["confidence"] = "high" if "high" in (prev["confidence"], c["confidence"]) else "low"
            prev["keyword_backed"] = prev["keyword_backed"] or c["keyword_backed"]
            if prev["team"] == "unresolved":
                prev["team"] = c["team"]
            prev["quotes"].append(c["quote"])
            continue
        out.append({**{k: v for k, v in c.items() if k != "quote"}, "quotes": [c["quote"]], "mentions": 1})
    return out


def resolve_team(call: dict[str, Any], team_names: dict[str, list[str]] | None) -> str:
    """'away' / 'home' only if exactly one side's name from match data is in what was said. Else 'unresolved'."""
    if not team_names:
        return "unresolved"
    said = " " + _norm(" ".join(filter(None, [call.get("team_said"), call.get("quote")]))) + " "
    sides = [s for s in ("away", "home") if any(_norm(n) and f" {_norm(n)} " in said for n in team_names.get(s) or [])]
    return sides[0] if len(sides) == 1 else "unresolved"


def _overlaps(c: dict, lo: int, hi: int) -> bool:
    return c["end_ms"] >= lo and c["start_ms"] <= hi


def _fits(c: dict[str, Any], lock: dict[str, Any]) -> bool:
    """The call could be this lock's play: same source, in its window, right side, points equal or part of a combo."""
    if c["source"] != lock["source"] or not _overlaps(c, lock["t_ms"] - PRE_MS, lock["t_ms"] + POST_MS):
        return False
    if c["team"] not in ("unresolved", lock.get("team")):
        return False
    return c["points"] == lock["points"] or c["type"] in COMBOS.get(lock["points"], ())


def judge_lock(lock: dict[str, Any], calls: list[dict[str, Any]], segments: list[Segment],
               explained: set[str] | None = None) -> dict[str, Any]:
    """``explained`` = ids of calls that fit ANOTHER lock (e.g. the TD call 12 s before the extra-point lock). Such a
    call is the neighbouring lock's play, so it never counts as a conflict here (added Oct 28 2026, see doc)."""
    t, pts, side = lock["t_ms"], lock["points"], lock.get("team")
    lo, hi = t - PRE_MS, t + POST_MS
    row = {"id": lock["id"], "source": lock["source"], "t_ms": t, "team": side, "points": pts, "calls": []}
    near = [c for c in calls if c["source"] == lock["source"] and _overlaps(c, lo, hi)]
    row["calls"] = [c["id"] for c in near]
    if not any(s.end_ms >= lo and s.start_ms <= hi for s in segments):
        return {**row, "result": "unchecked", "reason": "no_commentary_in_window"}
    same_side = [c for c in near if c["team"] in ("unresolved", side)]
    types = {c["type"] for c in same_side}
    if any(c["points"] == pts for c in same_side) or (pts in COMBOS and set(COMBOS[pts]) <= types):
        row["agreeing_calls"] = [c["id"] for c in same_side if c["points"] == pts or c["type"] in COMBOS.get(pts, ())]
        return {**row, "result": "agree"}
    conflict = [c for c in near if c["confidence"] == "high" and c["id"] not in (explained or set())
                and (c["team"] not in ("unresolved", side) or c["points"] != pts)]
    if conflict:
        return {**row, "result": "disagree", "reason": "broadcast_calls_" + "+".join(sorted({c["type"] for c in conflict}))}
    return {**row, "result": "unchecked", "reason": "no_confident_call_in_window" if near else "no_call_in_window"}


def witness(receipt: dict[str, Any], sources: list[dict[str, Any]], locks: list[dict[str, Any]], *,
            asr: VoiceTranscriber | None = None, extractor: CallExtractor | None = None,
            team_names: dict[str, list[str]] | None = None,
            probe_db: Callable[[str], float | None] | None = None,
            to_wav: Callable[[str], bytes] | None = None, quotes_only: bool = False) -> dict[str, Any]:
    """sources = [{"id", "path", "sha256"?}] (audio or video files); locks = [{"id", "source", "t_ms", "team", "points"}]
    with t_ms on that source's timeline. Returns the unsigned sidecar. Never raises.

    ``quotes_only=True`` (for private recordings): the sidecar keeps segment counts and the short quoted score calls
    only (each at most ``MAX_QUOTE_CHARS``), never the transcript."""
    asr = asr or VoiceTranscriber()
    extractor = extractor or CallExtractor()
    probe_db = probe_db or max_volume_db
    to_wav = to_wav or wav_from_media
    src_rows, all_calls, segs_by_src = [], [], {}
    for s in sources:
        sid = str(s["id"])
        row: dict[str, Any] = {"id": sid, "sha256": s.get("sha256"), "status": "ok", "segments": []}
        segs: list[Segment] = []
        try:
            if not asr.has_key or not extractor.has_key:
                raise MuseError("api_key_missing")
            db = probe_db(str(s["path"]))
            row["max_volume_db"] = None if db is None else int(round(db))  # int: JCS-safe in Python and JS
            if db is None:
                raise AsrError("no_audio_track")
            if db < MUTED_MAX_DB:
                raise AsrError("muted")
            segs = asr.transcribe(to_wav(str(s["path"])))
            if not segs:
                raise AsrError("no_speech")
            row["segments"] = [{"start_ms": g.start_ms, "end_ms": g.end_ms,
                                "text": g.text if not text_problems(g.text) else "(withheld by wording filter)"} for g in segs]
            raw = extractor.extract(segs)
            kept, dropped = validate_calls(raw, segs)
            row["dropped_calls"] = dropped
            for c in kept:
                c["source"], c["team"] = sid, resolve_team(c, team_names)
            for c in merge_calls(kept):
                all_calls.append(c)
        except (MuseError, AsrError) as e:
            row["status"], row["reason"], segs = "unchecked", str(e), []
        except Exception as e:  # noqa: BLE001  never take anything down
            row["status"], row["reason"], segs = "unchecked", f"error:{type(e).__name__}", []
        segs_by_src[sid] = segs
        src_rows.append(row)
    for i, c in enumerate(all_calls):
        c["id"] = f"C{i + 1}"
        c.pop("team_said", None)
        c["quotes"] = [q if not text_problems(q) else "(withheld by wording filter)" for q in c["quotes"]]
    lock_rows = []
    for lk in locks:
        try:
            others = [o for o in locks if o is not lk and isinstance(o, dict) and {"source", "t_ms", "points"} <= set(o)]
            explained = {c["id"] for c in all_calls if any(_fits(c, o) for o in others)}
            lock_rows.append(judge_lock(lk, all_calls, segs_by_src.get(str(lk["source"]), []), explained))
        except Exception as e:  # noqa: BLE001  a malformed lock is unchecked, never a disagreement
            lock_rows.append({"id": str((lk or {}).get("id")) if isinstance(lk, dict) else None, "result": "unchecked",
                              "reason": f"bad_lock:{type(e).__name__}", "calls": []})
    # A call is "matched" only if it agreed with a lock; a call merely near a lock it doesn't fit is unmatched.
    matched = {cid for r in lock_rows for cid in r.get("agreeing_calls", [])}
    for c in all_calls:
        c["matched"] = c["id"] in matched
    if quotes_only:
        for row in src_rows:
            segs = row.pop("segments", [])
            row["segments"] = {"count": len(segs), "speech_ms": sum(g["end_ms"] - g["start_ms"] for g in segs),
                               "text": "not included (private recording; quoted score calls only)"}
        for c in all_calls:
            c["quotes"] = [q[:MAX_QUOTE_CHARS] for q in c["quotes"]]
    agree = sum(r["result"] == "agree" for r in lock_rows)
    dis = sum(r["result"] == "disagree" for r in lock_rows)
    if dis:
        state, summary, cap = "disagrees", f"Broadcast disagrees with {dis} of {agree + dis} checked locked scores", PARTIAL
    elif agree:
        state, summary, cap = "agrees", f"Broadcast agrees with {agree} of {agree} checked locked scores", None
    else:
        state, summary, cap = "unchecked", "Broadcast unchecked (no usable commentary; no penalty)", None
    return {"schema": SCHEMA, "label": LABEL, "built_during": BUILT, "affects_verdict": "lower_only", "max_cap": PARTIAL,
            "models": {"asr": ASR_MODEL, "extractor": getattr(extractor, "model", DEFAULT_MODEL)},
            "data_retention": DATA_RETENTION, "receipt_jcs_sha256": receipt_jcs_sha256(receipt),
            "team_mapping": "from match data" if team_names else "unresolved (no team names in match data; never guessed)",
            "sources": src_rows, "calls": all_calls, "locks": lock_rows,
            "unmatched_calls": [c["id"] for c in all_calls if not c["matched"]],
            "checked": agree + dis, "agree": agree, "disagree": dis, "state": state, "cap": cap, "summary": summary,
            "api_calls": {"asr": asr.calls, "muse": extractor.calls}, "cost_micro_usd": extractor.cost_micro_usd,
            "cost_note": "Muse Spark tokens only; Voice Transcribe price not recorded"}


def apply_cap(status: str, cap: str | None) -> str:
    """Only ever VERIFIED -> PARTIAL. Never raises a status, never FAIL."""
    if cap is None:
        return status
    if cap != PARTIAL:
        raise ValueError("the commentary witness can only cap at PARTIAL")
    return PARTIAL if status == VERIFIED else status


def apply_to_result(v: dict[str, Any], sidecar: dict[str, Any] | None) -> dict[str, Any]:
    """Display-layer copy of the verifier output with the cap applied. Input never mutated."""
    out = copy.deepcopy(v)
    if not sidecar or sidecar.get("cap") is None:
        out["commentary_witness"] = "agrees" if sidecar and sidecar.get("checked") else "unchecked"
        return out
    new = apply_cap(out["status"], sidecar["cap"])
    if new != out["status"]:
        out["status"] = new
        out["partial"] = list(out.get("partial") or []) + [CAP_CODE]
    out["commentary_witness"] = "disagrees"
    return out


def check_witness(doc: Any, receipt: dict[str, Any], *, keys: dict[str, Any] | None = None) -> list[str]:
    """Problems with a signed commentary_witness.json for this receipt. Empty list = it may be applied (lower-only)."""
    from qortime_ai.ai_ruling.signing import check_signed

    p = check_signed(doc, receipt, schema=SCHEMA, keys=keys)
    if p == ["not_an_object"]:
        return p
    if doc.get("affects_verdict") != "lower_only" or doc.get("max_cap") != PARTIAL:
        p.append("not_lower_only")
    if doc.get("cap") not in (None, PARTIAL):
        p.append("bad_cap")
    locks = doc.get("locks") if isinstance(doc.get("locks"), list) else []
    if (doc.get("cap") == PARTIAL) != any(isinstance(x, dict) and x.get("result") == "disagree" for x in locks):
        p.append("cap_inconsistent")
    if text_problems(" ".join(str(doc.get(k) or "") for k in ("label", "summary"))):
        p.append("wording")
    return p


# ---- media helpers (ffmpeg) ---------------------------------------------------------------------------------------
def max_volume_db(path: str) -> float | None:
    """Peak level of the first audio stream in dB, or None if there is no audio track."""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise AsrError("ffmpeg_missing")
    r = subprocess.run([ff, "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0?", "-vn", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=600)
    m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", r.stderr)
    if not m:
        return None
    return -200.0 if m.group(1) == "-inf" else float(m.group(1))


def wav_from_media(path: str) -> bytes:
    """Mono 16-bit PCM 24 kHz WAV bytes (the model's native rate). Written to a temp dir, never kept."""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise AsrError("ffmpeg_missing")
    with tempfile.TemporaryDirectory(prefix="cw-") as d:
        out = Path(d) / "a.wav"
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "24000",
                        "-c:a", "pcm_s16le", "-map_metadata", "-1", str(out)], check=True, timeout=600)
        return out.read_bytes()


def from_clips(clips_manifest: dict[str, Any], clip_dir) -> tuple[list[dict], list[dict]]:
    """Sources + locks from a QorCap highlight-clips manifest: one lock per clip at lock_at_s, points = score change."""
    sources, locks = [], []
    for c in clips_manifest.get("clips") or []:
        lk = c.get("lock") or {}
        sb, sa = lk.get("score_before") or {}, lk.get("score_after") or {}
        diff = {k: (sa.get(k) or 0) - (sb.get(k) or 0) for k in ("away", "home")}
        sides = [k for k, v in diff.items() if v > 0]
        if len(sides) != 1 or not isinstance(c.get("lock_at_s"), (int, float)):
            continue
        sid = str(c.get("id"))
        sources.append({"id": sid, "path": str(Path(clip_dir) / str(c.get("file"))), "sha256": c.get("sha256")})
        locks.append({"id": f"{sid}#lock{lk.get('seq')}", "source": sid, "t_ms": int(round(float(c["lock_at_s"]) * 1000)),
                      "team": sides[0], "points": diff[sides[0]],
                      "score_after": {"away": sa.get("away"), "home": sa.get("home")}})
    return sources, locks


def team_names_from_match(match: dict[str, Any] | None) -> dict[str, list[str]] | None:
    """Team names only if match data has them (``teams: {away: {name, abbr}, home: ...}``). Else None (unresolved)."""
    teams = (match or {}).get("teams")
    if not isinstance(teams, dict):
        return None
    out = {}
    for side in ("away", "home"):
        t = teams.get(side)
        names = [t] if isinstance(t, str) else [t.get(k) for k in ("name", "abbr", "city") if isinstance(t, dict)]
        out[side] = [n for n in names if isinstance(n, str) and n.strip()]
    return out if out.get("away") and out.get("home") else None


def main(argv: list[str] | None = None) -> int:
    """python -m qortime_ai.commentary RECEIPT (--clips DIR | --audio FILE --locks LOCKS.json) [--match match.json]
    [--sign-key PATH] [--out FILE]"""
    import argparse

    from qor_receipt.receipt import verify_receipt

    ap = argparse.ArgumentParser(prog="python -m qortime_ai.commentary")
    ap.add_argument("receipt")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--clips", help="folder with a QorCap clips manifest.json and the clip mp4s")
    g.add_argument("--audio", help="full match recording (audio or video file)")
    ap.add_argument("--locks", help="with --audio: JSON list of {id, t_ms, team, points} on the recording timeline")
    ap.add_argument("--match", help="match.json (team names are used only if present)")
    ap.add_argument("--pub")
    ap.add_argument("--sign-key", help="AI ADVISORY key file (never a referee key)")
    ap.add_argument("--out")
    ap.add_argument("--quotes-only", action="store_true", help="keep only short quoted score calls, never the transcript")
    a = ap.parse_args(argv)
    receipt = json.loads(Path(a.receipt).read_text(encoding="utf-8"))
    if a.clips:
        sources, locks = from_clips(json.loads((Path(a.clips) / "manifest.json").read_text(encoding="utf-8")), a.clips)
    else:
        if not a.locks:
            ap.error("--audio needs --locks")
        sources = [{"id": "recording", "path": a.audio, "sha256": hashlib.sha256(Path(a.audio).read_bytes()).hexdigest()}]
        locks = [{**lk, "source": "recording"} for lk in json.loads(Path(a.locks).read_text(encoding="utf-8"))]
    names = team_names_from_match(json.loads(Path(a.match).read_text(encoding="utf-8"))) if a.match else None
    doc = witness(receipt, sources, locks, team_names=names, quotes_only=a.quotes_only)
    v = verify_receipt(receipt, referee_pub=a.pub)
    print(f"verifier: {v['status']}  ->  with commentary witness: {apply_to_result(v, doc)['status']}   "
          f"({doc['summary']}; ASR calls {doc['api_calls']['asr']}, Muse calls {doc['api_calls']['muse']}, "
          f"${doc['cost_micro_usd'] / 1e6:.4f} Muse)")
    if a.sign_key:
        from qor_receipt.keys import FileKey

        from qortime_ai.ai_ruling.signing import sign_ruling
        doc = sign_ruling(doc, FileKey(Path(a.sign_key)))
    out = Path(a.out) if a.out else Path(a.receipt).with_name(FILENAME)
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


__all__ = ["SCHEMA", "FILENAME", "CAP_CODE", "POINTS", "CallExtractor", "witness", "validate_calls", "merge_calls",
           "resolve_team", "judge_lock", "apply_cap", "apply_to_result", "check_witness", "text_problems", "from_clips",
           "team_names_from_match", "max_volume_db", "wav_from_media"]
