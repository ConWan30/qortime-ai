"""One short Muse Spark caption per segment, citing seen.json / receipt fields in [brackets].

Deterministic gates run AFTER the model (reused from qortime_ai.redteam): the citation checker (every sentence cites a
field; every number must come from a cited field; no status words, since this feature emits no status) and the
banned-word filter. Plus a "not a coach" lint: no play, speed, route or player-quality language. A caption that fails
any gate is replaced by a deterministic template caption (marked source="template").
"""
from __future__ import annotations

import json
import re
from typing import Any

from qortime_ai.redteam.citations import check

COACH = re.compile(r"\b(speed|fast(est)?|slow(est)?|routes?|yards?|yardage|tackl\w*|catch\w*|throw\w*|pass(es|ing)?|"
                   r"rush\w*|blitz\w*|coverage|defen[cs]\w*|offen[cs]\w*|sprint\w*|mph|best|worst|great|skill\w*|"
                   r"quarterback|receiver|play quality|good play|bad play|performance)\b", re.I)
MAX_WORDS = 28

SYSTEM = ("You caption a VISUALIZATION of a gaming-integrity referee's evidence. You are not a coach or sports analyst. "
          "Write exactly one short, plain-English caption per segment (max 22 words, 1 or 2 sentences). Every sentence must end with "
          "the [field] names it relies on, from that segment's FIELDS only, and every number you write must be the "
          "value of a field you cite. Describe only: where motion energy was (players / HUD / rest of screen) and "
          "whether the scorebug stayed in place. Write every *_pct value with a % sign (e.g. 'players 9%'). "
          "If the scorebug was not in place on every frame, say so plainly. Never mention speed, routes, yards, plays, skill, who is better, any "
          "verdict or status word, or words like attested, certified, guaranteed, hardware-verified. "
          "Return JSON only: {\"captions\":[{\"seq\":<int>,\"text\":\"...\"}]}")


def facts(seg: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    """Citable fields for one segment. ``verdict`` is None so any status word fails the checker."""
    sb, mo = seg["scorebug"], seg["motion_pct"]
    f = {"verdict": None, "seen.seq": seg["seq"], "seen.motion.players_pct": mo["players"],
         "seen.motion.hud_pct": mo["hud"], "seen.motion.rest_pct": mo["rest"],
         "seen.scorebug.frames": sb["frames"], "seen.scorebug.in_place": sb["in_place"],
         "seen.scorebug.off_roi": sb["off_roi"], "seen.scorebug.dropouts": sb["dropouts"],
         "match.scorebug_profile": ((receipt.get("match") or {}).get("scorebug_profile"))}
    for role, v in sorted(((receipt.get("signals") or {}).get("motion_permille") or {}).items()):
        f[f"signals.motion_permille.{role}"] = v
    return f


def template(seg: dict[str, Any]) -> str:
    sb, mo = seg["scorebug"], seg["motion_pct"]
    a = (f"Motion energy: players {mo['players']}%, HUD {mo['hud']}%, rest {mo['rest']}% "
         "[seen.motion.players_pct, seen.motion.hud_pct, seen.motion.rest_pct].")
    if sb["in_place"] == sb["frames"]:
        b = f"Scorebug in place on all {sb['frames']} frames [seen.scorebug.frames, seen.scorebug.in_place]."
    else:
        b = (f"Scorebug in place on {sb['in_place']} of {sb['frames']} frames "
             "[seen.scorebug.in_place, seen.scorebug.frames].")
    return a + " " + b


def gate(text: str | None, fx: dict[str, Any]) -> list[str]:
    probs = [p["problem"] for p in check(text, fx)]
    prose = re.sub(r"\[[^\[\]]*\]", " ", text or "")
    if COACH.search(prose):
        probs.append("coach_language:" + COACH.search(prose).group(0).lower())
    for k in ("seen.motion.players_pct", "seen.motion.hud_pct", "seen.motion.rest_pct"):
        if k in (text or "") and not re.search(rf"\b{fx.get(k)}\s*%", prose):
            probs.append("percent_without_%:" + k)      # "3 players" must never stand for "3%"
    if len(prose.split()) > MAX_WORDS:
        probs.append("too_long")
    return probs


def user_prompt(segs: list[dict[str, Any]], receipt: dict[str, Any]) -> str:
    rows = [{"seq": s["seq"], "FIELDS": {k: v for k, v in facts(s, receipt).items() if k != "verdict"}} for s in segs]
    return "Segments:\n" + json.dumps(rows, separators=(",", ":"))


def parse_reply(text: str) -> dict[int, str]:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    out = {}
    for c in d.get("captions") or []:
        try:
            out[int(c["seq"])] = str(c["text"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
    return out


def finalize(segs: list[dict[str, Any]], receipt: dict[str, Any], model_text: dict[int, str], model: str) -> None:
    """Attach {caption, caption_source, caption_rejected} to each segment in place."""
    for s in segs:
        fx = facts(s, receipt)
        t = model_text.get(s["seq"])
        probs = gate(t, fx) if t is not None else ["no_model_caption"]
        if probs:
            s["caption"], s["caption_source"] = template(s), "template"
            s["caption_rejected"] = sorted(set(probs))[:4]
            assert not gate(s["caption"], fx), gate(s["caption"], fx)
        else:
            s["caption"], s["caption_source"] = t, model
