"""Button presses (rising edges) from qorcap-inputs/v0 records. Bit map as qortime_ai.hands.track.BUTTON_BITS."""
from __future__ import annotations

from typing import Any, Iterable

CROSS, OPTIONS = 1 << 0, 1 << 9
UP, DOWN, LEFT, RIGHT = 1 << 12, 1 << 13, 1 << 14, 1 << 15
NAMES = {CROSS: "CROSS", OPTIONS: "OPTIONS", UP: "UP", DOWN: "DOWN", LEFT: "LEFT", RIGHT: "RIGHT"}
DPAD = ("UP", "DOWN", "LEFT", "RIGHT")


def press_events(records: Iterable[dict[str, Any]], *, release_gap_us: int | None = None) -> list[dict[str, Any]]:
    """[{t_us, button}] for each rising edge of CROSS / OPTIONS / D-pad, time-ordered.

    A full inputs.jsonl has release reports (b without the bit), so plain edges work and ``release_gap_us`` stays None.
    For extracts that keep only non-zero reports, ``release_gap_us`` treats a gap longer than that between two reports
    carrying the bit as a release (an assumption, reported in the sidecar).
    """
    rows = sorted((r for r in records if isinstance(r, dict) and r.get("type", "in") == "in"
                   and isinstance(r.get("t_us"), int)), key=lambda r: r["t_us"])
    out: list[dict[str, Any]] = []
    prev, seen = 0, {}
    for r in rows:
        b, t = int(r.get("b") or 0), r["t_us"]
        for bit, name in NAMES.items():
            if not b & bit:
                continue
            was = bool(prev & bit)
            if release_gap_us is not None and bit in seen and t - seen[bit] > release_gap_us:
                was = False
            if not was:
                out.append({"t_us": t, "button": name})
            seen[bit] = t
        prev = b
    return out
