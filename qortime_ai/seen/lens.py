"""Evidence Lens timing (deterministic). Mirrors web/seen-view.js ``lensState``.

The lens exists ONLY inside a receipt event window: materialize (300 ms) -> hold (follows the SAM track) -> dissolve
(400 ms). Windows come from the receipt timeline (score locks, challenge windows) and the lock's receipt-bound
segment; positions come from SAM. Gold is reserved for a score lock on a receipt the verifier calls VERIFIED.
"""
from __future__ import annotations

from typing import Any

MATERIALIZE_S = 0.30
DISSOLVE_S = 0.40
AQUA = "aqua"
GOLD = "gold"


def color_for(kind: str, verifier_status: str | None) -> str:
    return GOLD if kind == "score_lock" and verifier_status == "VERIFIED" else AQUA


def state(event: dict[str, Any], t: float, verifier_status: str | None = None) -> dict[str, Any] | None:
    """None outside [t0, t1). Else {phase, p (0..1 within phase), alpha, color}."""
    t0, t1 = float(event["t0"]), float(event["t1"])
    if not (t0 <= t < t1) or t1 <= t0:
        return None
    dur = t1 - t0
    m = min(MATERIALIZE_S, dur / 2)
    d = min(DISSOLVE_S, dur / 2)
    col = color_for(str(event.get("kind")), verifier_status)
    if t < t0 + m:
        p = (t - t0) / m
        return {"phase": "materialize", "p": p, "alpha": p, "color": col}
    if t >= t1 - d:
        p = (t - (t1 - d)) / d
        return {"phase": "dissolve", "p": p, "alpha": 1 - p, "color": col}
    return {"phase": "hold", "p": (t - t0 - m) / max(dur - m - d, 1e-9), "alpha": 1.0, "color": col}
