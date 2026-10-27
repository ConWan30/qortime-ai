"""Deterministic analysis on SAM 3.1 tracks: scorebug continuity + motion-energy attribution (aggregates only).

Energy is the referee's own measure (qor_receipt.review.media.motion_series: mean |gray_t - gray_{t-1}|, x100),
recomputed on the public clip at 640x360 and SPLIT by where the changed pixels are:
  players = inside the union of SAM "football player" masks (frame t or t-1)
  hud     = inside SAM's tracked scorebug mask (box prompt = the referee's OCR region), not already players
  rest    = field, crowd, camera motion.
QorCap's burned-in highlight label (top-left, added after capture) is excluded from every bucket.
Only per-segment percentages leave this module; never per-player or per-frame data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from qortime_ai.seen.sam_video import REF_H, REF_W, REFEREE_SCOREBUG_ROI, parse

FPS = 30
TRACK_MIN_CONF = 0.5
BURN_IN = (0, 0, 358, 72)          # sam_scorebug.PROFILES["madden27_standard"]["mask"] at 640x360 (QorCap label)


@dataclass
class Tracks:
    sb_box: np.ndarray        # (N,4) float, nan where missing
    sb_conf: np.ndarray       # (N,) float, nan where missing
    sb_mask: np.ndarray       # (N,H,W) bool
    pl_mask: np.ndarray       # (N,H,W) bool union of player masks
    pl_box: np.ndarray        # (N,4) union bbox of player masks, nan where none (render only, never published)
    pl_ids: int               # distinct object ids across the clip (aggregate)


def load_tracks(scorebug_text: str, players_text: str, n: int, cache: Path | None = None) -> Tracks:
    if cache is not None and cache.exists():
        z = np.load(cache)
        H, W = REF_H, REF_W
        return Tracks(z["sb_box"], z["sb_conf"], np.unpackbits(z["sb_mask"], axis=-1)[..., :W].astype(bool).reshape(-1, H, W),
                      np.unpackbits(z["pl_mask"], axis=-1)[..., :W].astype(bool).reshape(-1, H, W), z["pl_box"], int(z["pl_ids"]))
    sb, pl = parse(scorebug_text, (REF_W, REF_H)), parse(players_text, (REF_W, REF_H))
    t = Tracks(np.full((n, 4), np.nan), np.full(n, np.nan), np.zeros((n, REF_H, REF_W), bool),
               np.zeros((n, REF_H, REF_W), bool), np.full((n, 4), np.nan),
               len({o.object_id for v in pl.values() for o in v}))
    for f, objs in sb.items():
        if 0 <= f < n and objs:
            o = max(objs, key=lambda o: o.confidence or 0)
            t.sb_box[f] = o.box
            t.sb_conf[f] = o.confidence if o.confidence is not None else 1.0
            if o.mask is not None:
                t.sb_mask[f] = o.mask
    for f, objs in pl.items():
        if 0 <= f < n:
            for o in objs:
                if o.mask is not None:
                    t.pl_mask[f] |= o.mask
            ys, xs = t.pl_mask[f].nonzero()
            if len(xs):
                t.pl_box[f] = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    if cache is not None:
        np.savez_compressed(cache, sb_box=t.sb_box, sb_conf=t.sb_conf, pl_box=t.pl_box, pl_ids=t.pl_ids,
                            sb_mask=np.packbits(t.sb_mask, axis=-1), pl_mask=np.packbits(t.pl_mask, axis=-1))
    return t


def gray_frames(path: str | Path) -> np.ndarray:
    import cv2

    cap, out = cv2.VideoCapture(str(path)), []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if f.shape[:2] != (REF_H, REF_W):
            f = cv2.resize(f, (REF_W, REF_H), interpolation=cv2.INTER_AREA)
        out.append(f.mean(axis=2).astype(np.int16))
    return np.stack(out)


def energy_split(gray: np.ndarray, tr: Tracks) -> np.ndarray:
    """(N,3) per-frame summed |diff| in [players, hud, rest]; row 0 is zero (no previous frame)."""
    n = min(len(gray), len(tr.sb_mask))
    keep = np.ones((REF_H, REF_W), bool)
    x1, y1, x2, y2 = BURN_IN
    keep[y1:y2, x1:x2] = False
    out = np.zeros((n, 3), np.int64)
    for t in range(1, n):
        d = np.abs(gray[t] - gray[t - 1]) * keep
        p = tr.pl_mask[t] | tr.pl_mask[t - 1]
        h = (tr.sb_mask[t] | tr.sb_mask[t - 1]) & ~p
        tot, ps, hs = int(d.sum()), int(d[p].sum()), int(d[h].sum())
        out[t] = (ps, hs, tot - ps - hs)
    return out


def pct3(v: np.ndarray) -> dict[str, int]:
    """Largest-remainder integer percentages that sum to 100 (or all 0 when there was no motion)."""
    s = float(v.sum())
    if s <= 0:
        return {"players": 0, "hud": 0, "rest": 0}
    raw = v * 100.0 / s
    fl = np.floor(raw).astype(int)
    for i in np.argsort(-(raw - fl))[: 100 - fl.sum()]:
        fl[i] += 1
    return dict(zip(("players", "hud", "rest"), (int(x) for x in fl)))


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


ON_ROI_PERMILLE = 500   # frame counts as "in place" when at least half the referee's OCR region is inside SAM's mask


def roi_cover(tr: Tracks, f: int) -> int:
    rx1, ry1, rx2, ry2 = REFEREE_SCOREBUG_ROI
    return int(tr.sb_mask[f][ry1:ry2, rx1:rx2].sum()) * 1000 // ((rx2 - rx1) * (ry2 - ry1))


def in_place(tr: Tracks, f: int) -> bool:
    c = tr.sb_conf[f]
    return bool(not np.isnan(c) and c >= TRACK_MIN_CONF and roi_cover(tr, f) >= ON_ROI_PERMILLE)


def scorebug_continuity(tr: Tracks, f0: int, f1: int) -> dict[str, Any]:
    """Frames [f0, f1) of the ONE box-prompted SAM object (id 1).
    in_place = tracked (conf >= 0.5) AND >= 50% of the referee's OCR region inside SAM's scorebug mask;
    off_roi = tracked but SAM's object is elsewhere (e.g. the game swapped in another graphic); dropouts = not tracked.
    max_anchor_jump_px = largest frame-to-frame move of the box's left/top/bottom edges across in-place frames (the
    right edge is excluded: the game's down-and-distance panel changes the strip's width by design)."""
    ip = [f for f in range(f0, f1) if in_place(tr, f)]
    tracked = [f for f in range(f0, f1) if not np.isnan(tr.sb_conf[f]) and tr.sb_conf[f] >= TRACK_MIN_CONF]
    ips = set(ip)
    jumps = [float(np.max(np.abs(tr.sb_box[f][[0, 1, 3]] - tr.sb_box[f - 1][[0, 1, 3]]))) for f in ip if f - 1 in ips]
    return {"frames": f1 - f0, "in_place": len(ip), "off_roi": len(tracked) - len(ip), "dropouts": (f1 - f0) - len(tracked),
            "max_anchor_jump_px": int(round(max(jumps))) if jumps else None,
            "roi_in_mask_min_permille": min(roi_cover(tr, f) for f in ip) if ip else None,
            "first_not_in_place_s": next((round(f / FPS, 2) for f in range(f0, f1) if f not in ips), None)}


def segments_for_clip(clip: dict[str, Any], n_frames: int, min_frames: int = 10) -> list[dict[str, Any]]:
    """Chain segments a public highlight clip covers, with clip-relative times. Times come from each segment's
    wall_ms close stamp relative to the lock's t_ms (approximate to about one frame; clips are re-encoded)."""
    lock, lat = clip["lock"], float(clip["lock_at_s"])
    out, dur = [], n_frames / FPS
    for s in clip["source"]["segments"]:
        end = (int(s["wall_ms"]) - int(lock["t_ms"])) / 1000 + lat
        start = end - 2.0
        a, b = max(0.0, start), min(dur, end)
        f0, f1 = int(round(a * FPS)), int(round(b * FPS))
        if f1 - f0 >= min_frames:
            out.append({"seq": int(s["seq"]), "segment_sha256": s["sha256"], "t0": round(a, 3), "t1": round(b, 3),
                        "f0": f0, "f1": f1})
    return out


def events_for_clip(clip: dict[str, Any], receipt: dict[str, Any], segs: list[dict[str, Any]], n_frames: int,
                    hold_s: float = 2.5) -> list[dict[str, Any]]:
    """Evidence Lens windows from the receipt timeline only (deterministic)."""
    lock, lat, dur = clip["lock"], float(clip["lock_at_s"]), n_frames / FPS
    role = (lock.get("evidence") or {}).get("role") or "away"
    cps = (receipt.get("checkpoints") or {}).get(role) or []
    idx = next((i for i, c in enumerate(cps) if c.get("hash") == lock.get("hash")), None)
    ev: list[dict[str, Any]] = []
    seg = next((s for s in segs if s["seq"] == int(lock.get("segment_seq", -1))), None)
    if seg is not None:
        ev.append({"kind": "motion_segment", "t0": seg["t0"], "t1": seg["t1"], "track": "players",
                   "seq": seg["seq"], "cite": f"signals.motion_permille.{role}"})
    if idx is not None:
        sa = lock.get("score_after") or {}
        ev.append({"kind": "score_lock", "t0": lat, "t1": round(min(dur, lat + hold_s), 3), "track": "scorebug",
                   "score": {"away": sa.get("away"), "home": sa.get("home")}, "cite": f"checkpoints.{role}[{idx}]"})
    for i, ch in enumerate(receipt.get("challenges") or []):
        end_ms = (ch.get("result") or {}).get("done_ms") or ch.get("deadline_ms")
        a = (int(ch["issued_ms"]) - int(lock["t_ms"])) / 1000 + lat
        b = (int(end_ms) - int(lock["t_ms"])) / 1000 + lat
        if b > 0 and a < dur:
            ev.append({"kind": "challenge", "t0": round(max(0, a), 3), "t1": round(min(dur, b), 3), "track": "scorebug",
                       "cite": f"challenges[{i}]"})
    return ev
