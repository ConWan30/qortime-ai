"""Free local checks for Stick Echo (built Oct 28 2026, EXPLORATORY). No model calls. Each check can only DROP frames
from scoring: it never adds a frame, never picks frames by how well they agree with the stick, and never raises a
result. Counts of dropped frames reach the sidecar as totals only.

* ``menu``   a play-call / menu screen leaking into a scored window. Per frame: the share of dark pixels (HSV value
  < 50) in the band 45-85 % down the frame (where the play-call panel sits; the crowd at the top is excluded), and the
  share of turf-green pixels above the scorebug. Menu frame if dark share > 0.30 or turf share < 0.20; 5 frames
  either side are dropped too (the overlay fades in and out).
* ``switch`` Circle switches the controlled player ON DEFENSE ONLY (on offense Circle is a receiver icon / move, and
  is never a switch). In a defense window, each Circle press is mapped to the screen (press time - video start +
  the fixed lag); frames from 3 before to 10 after are dropped, then SAM frames keep being dropped until SAM's feet
  are back on the halo (within max(40 px, marker width) of the marker) for 3 frames in a row. A Circle press with no
  marker jump within +-15 frames is counted as a diagnostic only.
"""
from __future__ import annotations

from typing import Any

import numpy as np

CHECKS = ("menu", "switch")
FPS = 30.0
MENU_DARK_V = 50
MENU_DARK_SHARE = 0.30
MENU_TURF_SHARE = 0.20
MENU_PAD = 5
SWITCH_BEFORE, SWITCH_AFTER, SWITCH_BACK_ON_HALO, SWITCH_DIAG = 3, 10, 3, 15
DEFENSE_CONTEXTS = ("defender", "defense", "kick_cover")
CIRCLE_BIT = 1 << 1          # qorcap hid bit map: CROSS=0, CIRCLE=1, SQUARE=2, TRIANGLE=3


def screen_stats(frame_bgr: np.ndarray) -> tuple[int, int]:
    """(turf share, dark share in the 45-85 % band) of one frame, in permille."""
    import cv2

    h = frame_bgr.shape[0]
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    top = hsv[:int(h * 0.85)]
    turf = (top[..., 0] >= 30) & (top[..., 0] <= 90) & (top[..., 1] >= 60) & (top[..., 2] >= 50)
    dark = hsv[int(h * 0.45):int(h * 0.85), :, 2] < MENU_DARK_V
    return int(round(turf.mean() * 1000)), int(round(dark.mean() * 1000))


def menu_drop(screen: list | None, n: int) -> np.ndarray:
    bad = np.zeros(n, bool)
    if not screen:
        return bad
    for k, s in enumerate(screen[:n]):
        if s is not None and (s[1] > MENU_DARK_SHARE * 1000 or s[0] < MENU_TURF_SHARE * 1000):
            bad[max(0, k - MENU_PAD):k + MENU_PAD + 1] = True
    return bad


def is_defense(context: str) -> bool:
    return any(str(context).lower().startswith(c) for c in DEFENSE_CONTEXTS)


def _on_halo(feet, marker) -> bool:
    return feet is not None and marker is not None and \
        float(np.hypot(feet[0] - marker[0], feet[1] - marker[1])) <= max(40.0, float(marker[2]))


def _jump_near(marker: list, f: int) -> bool:
    for k in range(max(1, f - SWITCH_DIAG), min(len(marker), f + SWITCH_DIAG + 1)):
        a, b = marker[k - 1], marker[k]
        if a is not None and b is not None and np.hypot(b[0] - a[0], b[1] - a[1]) > 40 + 0.5 * b[2]:
            return True
    return False


def switch_drop(win: dict[str, Any], circle_t_us, *, video_start_us: int, lag_s: float) -> tuple[np.ndarray, dict]:
    """-> (frames to drop, {"presses": n, "without_marker_jump": n}). Offense windows: nothing, ever."""
    n = int(win.get("frames") or len(win.get("marker") or []))
    bad = np.zeros(n, bool)
    info = {"presses": 0, "without_marker_jump": 0}
    if not is_defense(win.get("context", "")) or n == 0:
        return bad, info
    mk = (list(win.get("marker") or []) + [None] * n)[:n]
    feet = (list(win.get("sam_feet") or []) + [None] * n)[:n]
    for t in np.asarray(circle_t_us, np.int64):
        f = int(round(((int(t) - video_start_us) / 1e6 + lag_s - float(win["start_s"])) * FPS))
        if f < -SWITCH_AFTER or f >= n + SWITCH_BEFORE:
            continue
        info["presses"] += 1
        if not _jump_near(mk, f):
            info["without_marker_jump"] += 1
        lo, hi = max(0, f - SWITCH_BEFORE), min(n, f + SWITCH_AFTER + 1)
        bad[lo:hi] = True
        run, k = 0, hi
        while k < n and run < SWITCH_BACK_ON_HALO:          # re-anchor to the halo: no new SAM call, only drops
            run = run + 1 if _on_halo(feet[k], mk[k]) else 0
            if run < SWITCH_BACK_ON_HALO:
                bad[k] = True
            k += 1
        if run >= SWITCH_BACK_ON_HALO:                       # the frames back on the halo are kept
            bad[k - SWITCH_BACK_ON_HALO:k] = False
    return bad, info


def apply(win: dict[str, Any], V: dict[int, Any], checks, *, circle_t_us=None, video_start_us: int = 0,
          lag_s: float = 0.0) -> tuple[dict[int, Any], dict[str, int]]:
    """Drop frames from ``V`` (never adds). -> (kept V, counts)."""
    for c in checks:
        if c not in CHECKS:
            raise ValueError(f"checks must be among {CHECKS}")
    n = max([int(win.get("frames") or 0)] + [k + 1 for k in V])
    counts = {"menu_dropped": 0, "switch_dropped": 0, "circle_presses_on_defense": 0, "circle_without_marker_jump": 0}
    drop = np.zeros(n, bool)
    if "menu" in checks:
        m = menu_drop(win.get("screen"), n)
        counts["menu_dropped"] = sum(1 for k in V if m[k])
        drop |= m
    if "switch" in checks and circle_t_us is not None:
        s, info = switch_drop({**win, "frames": n}, circle_t_us, video_start_us=video_start_us, lag_s=lag_s)
        counts["switch_dropped"] = sum(1 for k in V if s[k] and not drop[k])
        counts["circle_presses_on_defense"] = info["presses"]
        counts["circle_without_marker_jump"] = info["without_marker_jump"]
        drop |= s
    return {k: v for k, v in V.items() if not drop[k]}, counts
