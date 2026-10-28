"""Pure scoring: logged presses vs the tracked pause-menu highlight. No video, no network (unit-tested).

Clock: every time here is seconds on the VIDEO's timeline. Presses are mapped onto it with the caller's
``video_start_us`` (input-clock time of video frame 0), so a latency is pixel time minus press time on that mapping.

Menu model (Madden pause menu, a vertical list): DOWN moves the highlight one row down, UP one row up, and both wrap
(DOWN on the last row jumps to the first). LEFT and RIGHT do nothing on this menu, so for them Echo can only check
that the highlight stayed still ("no-op held"); they are counted, but marked not visible.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Sequence

LAT_MIN_MS, LAT_MAX_MS = 0, 2500          # broad press-to-pixel bound (same ceiling as the referee's rule v2)
TOL_MS = 100                              # a press and its move must sit within this of the clip's common lag
MERGE_MS = 100                            # same-direction steps closer than this are one move (box animation)
MENU_VS_DPAD_MS = (-150, 1000)            # menu darkening may trail the D-pad lag (fade), never lead it much
RELAY_GAP_BAND_S = (0.5, 2.4)             # known capture/relay gap, reported against (info)
MOVING = {"UP": -1, "DOWN": 1}
STILL = ("LEFT", "RIGHT")
STATUSES = ("consistent", "partial", "mismatch", "unscorable")


@dataclass(frozen=True)
class Move:
    t: float          # first frame showing the new highlight position (video seconds)
    direction: str    # "UP" / "DOWN"
    wrap: bool = False


def moves_from_track(track: Sequence[tuple[float, float | None]], frame_h: int, *, min_step_frac: float = 1 / 90,
                     wrap_frac: float = 1 / 6) -> list[Move]:
    """Highlight moves from a (t, centre_y | None) track. Unknown frames are skipped, never treated as moves."""
    min_step, wrap_px = frame_h * min_step_frac, frame_h * wrap_frac
    out: list[Move] = []
    last = None
    for t, y in sorted(track, key=lambda x: x[0]):
        if y is None:
            continue
        if last is not None and abs(y - last) >= min_step:
            dy = y - last
            wrap = abs(dy) >= wrap_px
            d = ("UP" if dy > 0 else "DOWN") if wrap else ("DOWN" if dy > 0 else "UP")
            if out and out[-1].direction == d and (t - out[-1].t) * 1000 < MERGE_MS and not wrap:
                pass                                   # same move still animating
            else:
                out.append(Move(round(float(t), 4), d, wrap))
        last = y
    return out


def _fit_lag(moving: list[dict[str, Any]], moves: list[Move], tol: float) -> tuple[float | None, int]:
    best: tuple[int, float, float] | None = None
    for p in moving:
        for m in moves:
            lag = m.t - p["t"]
            if m.direction != p["button"] or not (LAT_MIN_MS / 1000 <= lag <= LAT_MAX_MS / 1000):
                continue
            res = [min((abs(q.t - x["t"] - lag) for q in moves if q.direction == x["button"]), default=9e9)
                   for x in moving]
            hit = [r for r in res if r <= tol]
            key = (len(hit), -sum(hit), lag)
            if best is None or key[:2] > best[:2]:
                best = key
    if best is None:
        return None, 0
    lag0 = best[2]
    resid = []
    for x in moving:
        r = [q.t - x["t"] for q in moves if q.direction == x["button"] and abs(q.t - x["t"] - lag0) <= tol]
        if r:
            resid.append(min(r, key=lambda v: abs(v - lag0)))
    return (statistics.median(resid) if resid else lag0), best[0]


def score_clip(presses: Sequence[dict[str, Any]], moves: Sequence[Move], menu: dict[str, Any],
               pattern: Sequence[str], *, tol_ms: int = TOL_MS) -> dict[str, Any]:
    """presses: [{t (video s), button}] time-ordered; menu: {present, onset_s, end_s}; pattern: e.g. LEFT,DOWN,..."""
    tol = tol_ms / 1000
    spec = [p for p in pattern if p != "OPTIONS"]
    out: dict[str, Any] = {"status": "unscorable", "why": None, "presses": [], "directions_matched": 0,
                           "directions_total": len(spec), "presses_echoed": 0, "presses_logged": 0,
                           "unexplained_moves": 0, "lag_ms": None, "jitter_ms": None,
                           "menu": {"appeared": False, "latency_ms": None, "vs_dpad_ms": None}}
    opt = next((p for p in presses if p["button"] == "OPTIONS"), None)
    if opt is None:
        out["why"] = "no_options_press"
        return out
    end = next((p["t"] for p in presses if p["button"] == "CROSS" and p["t"] > opt["t"]), float("inf"))
    dpad = [p for p in presses if opt["t"] < p["t"] < end and p["button"] in ("UP", "DOWN", "LEFT", "RIGHT")]
    out["presses_logged"] = len(dpad)
    out["logged_order_matches_pattern"] = [p["button"] for p in dpad] == spec
    present, onset = bool(menu.get("present")), menu.get("onset_s")
    if present and onset is not None:
        out["menu"]["latency_ms"] = round((onset - opt["t"]) * 1000)
    if not present or onset is None:
        out["why"] = "no_pause_menu_in_video"
        return out
    if not dpad:
        out["why"] = "no_dpad_presses_logged"
        return out
    moving = [p for p in dpad if p["button"] in MOVING]
    if not moving:
        out["why"] = "no_visible_dpad_press"     # LEFT/RIGHT only: nothing on screen to line up
        return out
    lo = opt["t"]
    hi = (end if end != float("inf") else max(p["t"] for p in dpad)) + LAT_MAX_MS / 1000
    cand = [m for m in moves if lo < m.t <= hi]
    lag, _ = _fit_lag(moving, cand, tol)
    if lag is None:
        out.update(status="mismatch", why="no_highlight_move_after_any_press")
        out["unexplained_moves"] = len(cand)
        _menu_check(out, opt, onset, None)
        return out
    hi = min(hi, (end if end != float("inf") else hi) + lag + tol)
    cand = [m for m in cand if m.t <= hi]
    used: set[int] = set()
    lats = []
    for p in dpad:
        row: dict[str, Any] = {"button": p["button"], "visible": p["button"] in MOVING, "echoed": False,
                               "latency_ms": None}
        near = [i for i, m in enumerate(cand) if i not in used and abs(m.t - p["t"] - lag) <= tol]
        if p["button"] in MOVING:
            hit = [i for i in near if cand[i].direction == p["button"]]
            if hit:
                i = min(hit, key=lambda j: abs(cand[j].t - p["t"] - lag))
                used.add(i)
                row.update(echoed=True, latency_ms=round((cand[i].t - p["t"]) * 1000), wrap=cand[i].wrap)
                lats.append(row["latency_ms"])
        else:
            row["echoed"] = not near                    # highlight held still, as a no-op should
        out["presses"].append(row)
    out["unexplained_moves"] = len(cand) - len(used)
    out["presses_echoed"] = sum(r["echoed"] for r in out["presses"])
    out["lag_ms"] = round(lag * 1000)
    out["jitter_ms"] = max(abs(x - out["lag_ms"]) for x in lats) if lats else None
    out["latency_median_ms"] = round(statistics.median(lats)) if lats else None
    out["in_relay_gap_band"] = (RELAY_GAP_BAND_S[0] * 1000 <= out["latency_median_ms"] <= RELAY_GAP_BAND_S[1] * 1000
                                if lats else None)
    pool = [r["button"] for r in out["presses"] if r["echoed"]]
    n = 0
    for d in spec:
        if d in pool:
            pool.remove(d)
            n += 1
    out["directions_matched"] = n
    first_move = min((cand[i].t for i in used), default=None)
    menu_ok = _menu_check(out, opt, onset, lag, first_move)
    vis = [r for r in out["presses"] if r["visible"]]
    vis_ok = sum(r["echoed"] for r in vis)
    if not menu_ok:
        out.update(status="mismatch", why="pause_menu_timing")
    elif vis_ok * 2 < len(vis) or out["unexplained_moves"] >= 2:
        out.update(status="mismatch", why="video_does_not_follow_inputs")
    elif out["presses_echoed"] == len(dpad) and not out["unexplained_moves"] and n == len(spec):
        out.update(status="consistent", why=None)
    else:
        why = ("pattern_directions_missing" if n < len(spec) else
               "unexplained_move" if out["unexplained_moves"] else "press_not_echoed")
        out.update(status="partial", why=why)
    return out


def _menu_check(out: dict[str, Any], opt: dict[str, Any], onset: float, lag: float | None,
                first_move: float | None = None) -> bool:
    lat = (onset - opt["t"]) * 1000
    ok = LAT_MIN_MS <= lat <= LAT_MAX_MS + MENU_VS_DPAD_MS[1]
    if lag is not None:
        vs = lat - lag * 1000
        out["menu"]["vs_dpad_ms"] = round(vs)
        ok = ok and MENU_VS_DPAD_MS[0] <= vs <= MENU_VS_DPAD_MS[1]
    if first_move is not None:
        ok = ok and onset <= first_move + 0.05
    out["menu"]["appeared"] = bool(ok)
    return bool(ok)
