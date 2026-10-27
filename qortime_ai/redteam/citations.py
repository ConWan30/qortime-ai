"""Cited explanations: every sentence must cite the fact field(s) it relies on, e.g. ``... passed [verdict].``

The checker is deterministic code. It rejects a sentence that cites nothing, cites a field that does not exist, or
states a number / status / winner that the cited fields do not support. The banned-word filter runs on the whole text.
"""
from __future__ import annotations

import re
from typing import Any

from qortime_ai.redteam.wording import banned_hits

DISPLAY = {"VERIFIED": "VERIFIED", "PARTIAL": "PARTIAL", "SELF_ATTESTED": "SELF-SIGNED", "FAIL": "FAIL"}
_CITE = re.compile(r"\[([^\[\]]+)\]")
_SENT = re.compile(r"[^.!?]+(?:[.!?]+|$)")
_NUM = re.compile(r"\b\d+\b")
_STATUS = re.compile(r"\b(VERIFIED|PARTIAL|SELF[-_ ]SIGNED|SELF_ATTESTED|FAIL(?:ED|S)?)\b")
_LOWER_VERIFIED = re.compile(r"\b(is|was|been|fully|officially)\s+verified\b", re.I)
_NEG = re.compile(r"\b(not|never|isn't|wasn't|hasn't)\s+(been\s+|fully\s+|officially\s+)?$", re.I)
_WIN = re.compile(r"\b(home|away)\b[^.]{0,25}?\b(won|wins|winner)\b|\bwinner\b[^.]{0,15}?\b(home|away)\b", re.I)


def facts(receipt: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    """The only fields an explanation may cite. Built by code from the receipt and the verifier's output."""
    m, res = receipt.get("match") or {}, receipt.get("result") or {}
    sig = receipt.get("signatures") or {}
    chs = receipt.get("challenges") or []
    f: dict[str, Any] = {
        "verdict": verdict.get("status"), "errors": list(verdict.get("errors") or []),
        "partial": list(verdict.get("partial") or []), "referee_trust": verdict.get("referee_trust"),
        "trust_tier": receipt.get("trust_tier"),
        "match.game": m.get("game"), "match.platform": m.get("platform"), "match.mode": m.get("mode"),
        "players.count": len(receipt.get("players") or []),
        "challenges.count": len(chs), "challenges.passed": sum(bool((c.get("result") or {}).get("ok")) for c in chs),
        "signatures.referee": "present" if sig.get("referee") else "absent",
        "signatures.players": sorted((sig.get("players") or {}).keys()),
        "agreement.timelines_agree": (receipt.get("agreement") or {}).get("timelines_agree"),
    }
    for k in ("home_score", "away_score", "winner", "quarter", "method", "final_basis"):
        f[f"result.{k}"] = res.get(k)
    for role, cps in sorted((receipt.get("checkpoints") or {}).items()):
        f[f"checkpoints.{role}.count"] = len(cps) if isinstance(cps, list) else None
    for role, v in sorted(((receipt.get("signals") or {}).get("motion_permille") or {}).items()):
        f[f"signals.motion_permille.{role}"] = v
    return f


def sentences(text: str) -> list[tuple[str, list[str]]]:
    """(prose, citations) per sentence. Sentences end at . ! ? or a newline; dots inside [citations] do not split.
    Citations written just after a sentence's period attach to that sentence."""
    cites_store: list[str] = []

    def mask(m: re.Match) -> str:
        cites_store.append(m.group(1))
        return f"\x00{len(cites_store) - 1}\x00"

    masked = _CITE.sub(mask, text or "")
    out: list[list[Any]] = []
    for raw in re.findall(r"[^.!?\n]+(?:[.!?]+|\n|$)", masked):
        s = raw.strip()
        if not s:
            continue
        ids = [int(i) for i in re.findall(r"\x00(\d+)\x00", s)]
        cites = [c.strip() for i in ids for c in cites_store[i].split(",") if c.strip()]
        prose = re.sub(r"\x00\d+\x00", "", s).strip()
        if not prose.strip(".!? ") and out:
            out[-1][1] += cites
            continue
        out.append([prose, cites])
    return [(p, c) for p, c in out]


def _values(v: Any) -> list[Any]:
    return list(v) if isinstance(v, list) else [v]


def check(text: str | None, fx: dict[str, Any]) -> list[dict[str, Any]]:
    """Problems found. Empty list = every sentence is grounded in a cited field and the wording filter passed."""
    probs: list[dict[str, Any]] = []
    t = (text or "").strip()
    if not t:
        return [{"sentence": None, "problem": "empty"}]
    for code in banned_hits(t):
        probs.append({"sentence": None, "problem": f"banned_word:{code}"})
    want = DISPLAY.get(str(fx.get("verdict")))
    for prose, cites in sentences(t):
        def bad(p: str) -> None:
            probs.append({"sentence": prose, "problem": p})
        if not cites:
            bad("missing_citation")
            continue
        unknown = [c for c in cites if c not in fx]
        for c in unknown:
            bad(f"unknown_field:{c}")
        known = [c for c in cites if c in fx]
        nums = {str(x) for c in known for x in _values(fx[c]) if isinstance(x, int) and not isinstance(x, bool)}
        nums |= set(_NUM.findall(" ".join(str(x) for c in known for x in _values(fx[c]))))
        for n in _NUM.findall(prose):
            if n not in nums:
                bad(f"number_not_in_cited_fields:{n}")
        words = {{"SELF-ATTESTED": "SELF-SIGNED", "FAILED": "FAIL", "FAILS": "FAIL"}.get(w, w)
                 for w in (m.group(1).upper().replace(" ", "-").replace("_", "-") for m in _STATUS.finditer(prose))}
        if words:
            if "verdict" not in cites:
                bad("status_without_verdict_citation")
            if words - {want}:
                bad("status_mismatch:" + ",".join(sorted(words - {want})))
        if want != "VERIFIED":
            for m in _LOWER_VERIFIED.finditer(prose):
                if not _NEG.search(prose[max(0, m.start() - 25):m.start()]):
                    bad("claims_verified")
                    break
        for m in _WIN.finditer(prose):
            side = (m.group(1) or m.group(3) or "").lower()
            if "result.winner" not in cites:
                bad("winner_without_citation")
            elif side != str(fx.get("result.winner")).lower():
                bad(f"winner_mismatch:{side}")
    return probs
