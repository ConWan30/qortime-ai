"""Post-model wording filter, applied to ALL AI-written user-facing text in the red-team report.

Citations like ``[trust_tier]`` are removed before scanning, so a field may be cited by name; the receipt value
"single-attested" may never appear in prose.
"""
from __future__ import annotations

import re

BANNED_TERMS = ("attested", "hardware-verified", "certified", "guaranteed", "proven cheat-free")

_RULES = [
    (re.compile(r"attest", re.I), "attested"),
    (re.compile(r"hardware[\s_-]*(verified|backed|proof|proven|secured)", re.I), "hardware-verified"),
    (re.compile(r"certif(ied|y|icate[sd]? of)", re.I), "certified"),
    (re.compile(r"guarantee", re.I), "guaranteed"),
    (re.compile(r"cheat[\s_-]*(free|proof)|proven\s+(clean|fair|legit)", re.I), "proven cheat-free"),
    (re.compile(r"tamper[\s_-]*proof|unhackable|unbreakable|impossible to (cheat|forge|fake)|100\s*%\s*(secure|safe|proof)", re.I), "absolute-security"),
    (re.compile(r"\btpm[\s_-]*(verified|proven)", re.I), "hardware-verified"),
]
_CITE = re.compile(r"\[[^\[\]]*\]")


def banned_hits(text: str | None) -> list[str]:
    """Banned-term codes found in ``text`` (citation brackets ignored). Empty list = text may be shown."""
    prose = _CITE.sub(" ", text or "")
    hits: list[str] = []
    for rx, code in _RULES:
        if rx.search(prose) and code not in hits:
            hits.append(code)
    return hits


def safe_text(text: str | None, *, withheld: str = "(AI text withheld by wording filter)") -> tuple[str, list[str]]:
    hits = banned_hits(text)
    return (withheld if hits else (text or "")), hits
