"""Which on-screen motion counts as "the player the gamer controls", frame by frame. Pure numpy, video-free.

A window's private track holds, per frame (30 fps): the SAM 3.1 box's feet point and its camera-compensated velocity,
and the game's controlled-player marker (centre x, y and width) with its own camera-compensated velocity. The stick
log is never an input here, so no frame is chosen by how well it agrees.

Selections:
* ``sam``    (phase-3 method, the pre-registered bar): every frame with a SAM velocity.
* ``hybrid`` (built Oct 28 2026 after the phase-3 results, EXPLORATORY): SAM where it stays on the marker and moves
  with it; where SAM has drifted to another player, the marker's own motion; frames around a control switch or with
  neither source are dropped.
* ``marker`` (diagnostic): the marker's motion only, no SAM.
"""
from __future__ import annotations

from typing import Any

import numpy as np

SELECTIONS = ("sam", "hybrid", "marker")
PREREGISTERED = "sam"
MIN_SPEED = 0.6            # px/frame at 640x360; slower frames carry no direction
AGREE_COS = 0.5            # SAM and marker velocities must point the same way (cos >= 0.5) when both move
SWITCH_PAD = 3             # frames dropped either side of a marker jump (control switch)


def _vec(x: Any) -> np.ndarray | None:
    return None if x is None else np.asarray(x, float)


def switch_frames(marker: list) -> np.ndarray:
    """Frames next to a marker jump larger than 40 px + half the marker width (control switched players)."""
    n = len(marker)
    bad = np.zeros(n, bool)
    for k in range(1, n):
        a, b = marker[k - 1], marker[k]
        if a is None or b is None:
            continue
        if np.hypot(b[0] - a[0], b[1] - a[1]) > 40 + 0.5 * b[2]:
            bad[max(0, k - SWITCH_PAD):k + SWITCH_PAD + 1] = True
    return bad


def sam_agrees(feet, vel_sam, marker, vel_marker) -> bool:
    """SAM's player stands on the marker (feet within max(40 px, marker width)) and moves with it."""
    if feet is None or marker is None or vel_sam is None or vel_marker is None:
        return False
    if np.hypot(feet[0] - marker[0], feet[1] - marker[1]) > max(40.0, float(marker[2])):
        return False
    a, b = _vec(vel_sam), _vec(vel_marker)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na >= MIN_SPEED and nb >= MIN_SPEED:
        return float(a @ b) / (na * nb) >= AGREE_COS
    return True


def select(win: dict[str, Any], how: str = PREREGISTERED) -> tuple[dict[int, np.ndarray], dict[str, int]]:
    """-> ({frame: velocity}, frame counts by source). Frames before ``score_from`` are never scored."""
    if how not in SELECTIONS:
        raise ValueError(f"selection must be one of {SELECTIONS}")
    vs, vm = win.get("sam_vel") or [], win.get("marker_vel") or []
    feet, mk = win.get("sam_feet") or [], win.get("marker") or []
    n = max(len(vs), len(vm), len(mk))
    pad = lambda a: list(a) + [None] * (n - len(a))
    vs, vm, feet, mk = pad(vs), pad(vm), pad(feet), pad(mk)
    k0 = int(win.get("score_from", 0))
    V: dict[int, np.ndarray] = {}
    src = {"sam": 0, "marker": 0, "dropped": 0}
    bad = switch_frames(mk) if how == "hybrid" else np.zeros(n, bool)
    for k in range(k0, n):
        if how == "sam":
            if vs[k] is not None:
                V[k] = _vec(vs[k]); src["sam"] += 1
            continue
        if how == "marker":
            if vm[k] is not None and mk[k] is not None:
                V[k] = _vec(vm[k]); src["marker"] += 1
            continue
        if bad[k]:
            src["dropped"] += 1
        elif sam_agrees(feet[k], vs[k], mk[k], vm[k]):
            V[k] = _vec(vs[k]); src["sam"] += 1
        elif vm[k] is not None and mk[k] is not None:
            V[k] = _vec(vm[k]); src["marker"] += 1
        else:
            src["dropped"] += 1
    return V, src
