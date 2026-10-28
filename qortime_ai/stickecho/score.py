"""Angle agreement between the controlled player's on-screen motion and the left stick, with swapped-log nulls.

Per scored frame: cosine between the player's camera-compensated velocity and the stick direction one lag earlier
(frames with speed >= 0.6 px/frame and stick >= 0.35 only). The true value is the mean cosine over all windows.
Null: the same video motion scored against stick timelines taken from other moments of the same game (>= 10 s
away) and from other games' logs, each held to the same stick-activity rule as the window selection (stick active
in >= 50 % of the window). 5000 random draws, one null start per window, give the null mean and sd; z = (true -
null mean) / null sd. Pass bar (pre-registered in phase 3): z >= 3 against every null source.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from qortime_ai.stickecho.log import ACTIVE, StickLog
from qortime_ai.stickecho.select import MIN_SPEED

FPS = 30.0
DRAWS = 5000
SEED = 7
NULL_STEP_US = 500_000
NULL_EDGE_US = 5_000_000
SAME_GAME_EXCLUDE_US = 10_000_000
MIN_NULL_FRAMES = 5
SWEEP_S = tuple(round(-0.9 + 0.1 * i, 1) for i in range(16))     # lag sweep, diagnostic only


def cos_sum(V: dict[int, np.ndarray], stick: np.ndarray) -> tuple[float, int, int]:
    """(sum of cosines, frames scored, frames within 45 deg). ``stick`` is aligned with sorted(V)."""
    ks = sorted(V)
    if not ks:
        return 0.0, 0, 0
    v = np.array([V[k] for k in ks], float)
    sp, sm = np.linalg.norm(v, axis=1), np.linalg.norm(stick, axis=1)
    ok = (sp >= MIN_SPEED) & (sm >= ACTIVE)
    if not ok.any():
        return 0.0, 0, 0
    c = (v[ok] * stick[ok]).sum(1) / (sp[ok] * sm[ok])
    return float(c.sum()), int(ok.sum()), int((c > np.cos(np.radians(45))).sum())


def input_times(start_s: float, V: dict[int, Any], video_start_us: int, lag_s: float) -> np.ndarray:
    """Input-clock time of the stick sample that should show up on frame k: frame time minus the lag."""
    vt = start_s + np.array(sorted(V), float) / FPS
    return ((vt + video_start_us / 1e6 - lag_s) * 1e6).astype(np.int64)


def null_pool(nl: StickLog, same_game: bool, t_true: np.ndarray, V: dict[int, np.ndarray]) -> np.ndarray:
    span = int(t_true[-1] - t_true[0])
    res = []
    for st in np.arange(nl.T[0] + NULL_EDGE_US, nl.T[-1] - NULL_EDGE_US - span, NULL_STEP_US):
        if same_game and abs(st - t_true[0]) < SAME_GAME_EXCLUDE_US:
            continue
        s = nl.stick_at(t_true - t_true[0] + st)
        if (np.linalg.norm(s, axis=1) >= ACTIVE).mean() < 0.5:
            continue
        r = cos_sum(V, s)
        if r[1] >= MIN_NULL_FRAMES:
            res.append(r[:2])
    return np.array(res) if res else np.zeros((0, 2))


def evaluate(windows: list[dict[str, Any]], log: StickLog, nulls: dict[str, StickLog], *, video_start_us: int,
             lag_s: float, draws: int = DRAWS, seed: int = SEED) -> dict[str, Any]:
    """windows: [{"start_s", "V": {frame: velocity}}]. ``nulls`` maps a label to a log; the same-game log is
    recognised by identity (``nl is log``). Returns floats; the sidecar converts to integers."""
    rng = np.random.default_rng(seed)
    W = []
    for w in windows:
        if not w["V"]:
            continue
        t = input_times(w["start_s"], w["V"], video_start_us, lag_s)
        tr = cos_sum(w["V"], log.stick_at(t))
        if tr[1] > 0:
            W.append((w, t, tr))
    nt = sum(x[2][1] for x in W)
    out: dict[str, Any] = {"windows": len(W), "frames": nt, "mean_cos": None, "within_45": None, "nulls": {}, "min_z": None}
    if not nt:
        return out
    true = sum(x[2][0] for x in W) / nt
    out.update(mean_cos=true, within_45=sum(x[2][2] for x in W) / nt)
    for name, nl in nulls.items():
        pl = [null_pool(nl, nl is log, t, w["V"]) for w, t, _ in W]
        if any(len(p) == 0 for p in pl):
            out["nulls"][name] = None
            continue
        d = np.array([sum(p[i][0] for p, i in zip(pl, idx)) / sum(p[i][1] for p, i in zip(pl, idx))
                      for idx in (tuple(rng.integers(len(p)) for p in pl) for _ in range(draws))])
        sd = float(d.std())
        out["nulls"][name] = {"mean": float(d.mean()), "sd": sd, "z": (true - float(d.mean())) / sd if sd > 0 else None,
                              "share_ge": float((d >= true).mean()), "pool_min": int(min(len(p) for p in pl))}
    zs = [v["z"] for v in out["nulls"].values() if v and v["z"] is not None]
    out["min_z"] = min(zs) if len(zs) == len(nulls) and zs else None
    return out


def lag_sweep(windows: list[dict[str, Any]], log: StickLog, *, video_start_us: int, lag_s: float) -> dict[float, float]:
    """Mean cosine at the fixed lag +- 0.9 s. DIAGNOSTIC ONLY: never used to pick the lag (that would be lag-shopping)."""
    out = {}
    for d in SWEEP_S:
        tot = n = 0
        for w in windows:
            if w["V"]:
                s, k, _ = cos_sum(w["V"], log.stick_at(input_times(w["start_s"], w["V"], video_start_us, lag_s + d)))
                tot += s; n += k
        if n:
            out[d] = tot / n
    return out
