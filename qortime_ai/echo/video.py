"""Video side of Challenge Echo: pause-menu detection (deterministic), highlight tracking (Meta SAM 3.1, with a
deterministic fallback), all on the video's own timeline.

* Menu present = whole-frame mean luma (320x180 grey) under ``DARK_LUMA`` for >= ``MIN_MENU_S``; onset = first
  such frame. This part is deterministic, not SAM.
* Highlight track (SAM 3.1): only the menu window, only the menu column (left ``CROP_W`` x top ``CROP_H`` of the
  frame, which holds the list and nothing player-identifying), re-encoded at ``SAM_FPS``. A BOX prompt on frame 0
  seeds object 1 with the highlight box found by ``find_highlight``; SAM propagates it forward. Track = box centre y.
* Fallback: ``find_highlight`` on every source frame (bright full-width rows of the highlight box).
* Row pitch (deterministic, for the wrap test in ``match``): spacing of the menu's text lines outside the highlight
  box, median over frames sampled across the menu window. None when it cannot be measured.
Raw SAM output is cached outside the repo by the caller; only summary numbers reach the sidecar.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

DARK_LUMA = 30.0
MIN_MENU_S = 0.3
CROP_W, CROP_H = 0.30, 0.47          # fractions of the frame: the pause-menu list column
SAM_FPS = 30
MAX_SAM_S = 15.0


@dataclass
class VideoObs:
    fps: float
    size: tuple[int, int]
    menu: dict[str, Any]
    track: list[tuple[float, float | None]] = field(default_factory=list)
    tracker: str = "none"
    sam: dict[str, Any] = field(default_factory=dict)
    fallback_agreement: float | None = None
    row_pitch: float | None = None


TEXT_LUMA = 140          # menu text rows: grey above this inside the highlight box's column span
PITCH_SAMPLES = 10


def _cv2():
    import cv2

    return cv2


def find_highlight(gray_crop: np.ndarray) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the highlight box in a grey menu crop, or None. Deterministic."""
    h, w = gray_crop.shape
    band = gray_crop[:, int(w * 0.16):int(w * 0.78)] > 200
    rows = np.where(band.mean(1) > 0.5)[0]
    if len(rows) < 2:
        return None
    # the box is the first bright cluster (rows within 60 px of each other)
    top = int(rows[0])
    grp = rows[rows <= top + max(12, int(h * 0.25))]
    bot = int(grp[-1]) + 1
    if not (h * 0.02 <= bot - top <= h * 0.25):
        return None
    cols = np.where((gray_crop[top:bot] > 200).mean(0) > 0.5)[0]
    if len(cols) < 2:
        return None
    return int(cols[0]), top, int(cols[-1]) + 1, bot


def row_pitch(gray_crop: np.ndarray) -> float | None:
    """Row pitch (px) of the menu list in one grey menu crop: median spacing between centres of consecutive text
    lines outside the highlight box (pairs that straddle the box are skipped, its row is taller). Deterministic.
    None without a highlight box, with fewer than two text lines, or when the spacing is implausible for the box."""
    box = find_highlight(gray_crop)
    if box is None:
        return None
    left, top, right, bot = box
    on = (gray_crop[:, left:right] > TEXT_LUMA).mean(1) > 0.01
    on[max(0, top - 2):bot + 2] = False
    lines, start = [], None
    for y, v in enumerate(on.tolist() + [False]):
        if v and start is None:
            start = y
        elif not v and start is not None:
            if y - start >= 3:
                lines.append((start + y) / 2)
            start = None
    gaps = [b - a for a, b in zip(lines, lines[1:]) if not (a < top and b > bot)]
    if not gaps:
        return None
    pitch = float(np.median(gaps))
    return pitch if 0.5 * (bot - top) <= pitch <= 1.5 * (bot - top) else None


def menu_row_pitch(frames: list[tuple[float, float, Any]], menu: dict[str, Any]) -> float | None:
    """Median ``row_pitch`` over up to PITCH_SAMPLES frames spread across the menu window."""
    inside = [c for t, _, c in frames if menu["onset_s"] <= t <= menu["end_s"]]
    if not inside:
        return None
    ps = [p for p in (row_pitch(c) for c in inside[:: max(1, len(inside) // PITCH_SAMPLES)]) if p is not None]
    return float(np.median(ps)) if ps else None


def scan(path: Path, t0: float, t1: float) -> tuple[float, tuple[int, int], list[tuple[float, float, Any]]]:
    """(fps, (w, h), [(t, mean_luma, grey_menu_crop)]) for source frames in [t0, t1]."""
    cv2 = _cv2()
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t0 * fps)))
    i = max(0, int(t0 * fps))
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        t = i / fps
        i += 1
        if t > t1:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        luma = float(cv2.resize(g, (320, 180), interpolation=cv2.INTER_AREA).mean())
        out.append((t, luma, g[: int(h * CROP_H), : int(w * CROP_W)]))
    cap.release()
    return fps, (w, h), out


def menu_window(frames: list[tuple[float, float, Any]], after_t: float, fps: float) -> dict[str, Any]:
    """First dark run (>= MIN_MENU_S) that reaches past ``after_t`` and shows a highlight box. Its onset is the run's
    true first frame, so a menu already up before the press shows as a negative latency (and fails the check)."""
    runs, cur = [], []
    for k, (_, luma, _) in enumerate(frames):
        if luma < DARK_LUMA:
            cur.append(k)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    for run in runs:
        if frames[run[-1]][0] < after_t or (run[-1] - run[0] + 1) / fps < MIN_MENU_S:
            continue
        if any(find_highlight(frames[k][2]) for k in run[:: max(1, len(run) // 10)]):
            return {"present": True, "onset_s": round(frames[run[0]][0], 4), "end_s": round(frames[run[-1]][0], 4)}
    return {"present": False, "onset_s": None, "end_s": None}


def fallback_track(frames, menu) -> list[tuple[float, float | None]]:
    out = []
    for t, _, crop in frames:
        if menu["onset_s"] <= t <= menu["end_s"]:
            b = find_highlight(crop)
            out.append((t, (b[1] + b[3]) / 2 if b else None))
    return out


def menu_clip(path: Path, t0: float, dur: float, w: int, h: int, dst: Path) -> Path:
    cw, ch = int(w * CROP_W) // 2 * 2, int(h * CROP_H) // 2 * 2
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-i", str(path), "-t", f"{dur:.3f}",
                    "-vf", f"crop={cw}:{ch}:0:0,fps={SAM_FPS}", "-an", "-c:v", "libx264", "-crf", "20",
                    "-pix_fmt", "yuv420p", str(dst)], check=True)
    return dst


def sam_track(path: Path, menu: dict[str, Any], size: tuple[int, int], *, cache: Path | None = None,
              caller=None) -> tuple[list[tuple[float, float | None]], dict[str, Any]]:
    """SAM 3.1 highlight track over the menu window. ``caller`` = qortime_ai.seen.sam_video.call (injectable)."""
    from qortime_ai.seen import sam_video

    caller = caller or sam_video.call
    cv2 = _cv2()
    t0 = menu["onset_s"] + 2 / SAM_FPS
    dur = min(menu["end_s"] - t0, MAX_SAM_S)
    with tempfile.TemporaryDirectory() as td:
        mc = menu_clip(path, t0, dur, *size, Path(td) / "menu.mp4")
        data = mc.read_bytes()
        cap = cv2.VideoCapture(str(mc))
        ok, f0 = cap.read()
        cw, ch = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
    box = find_highlight(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY)) if ok else None
    info: dict[str, Any] = {"model": sam_video.MODEL, "prompt": "box", "fps": SAM_FPS, "frames_sent": None,
                            "frame_size": [cw, ch], "window_s": [round(t0, 3), round(t0 + dur, 3)]}
    if box is None:
        info["error"] = "no_highlight_on_first_frame"
        return [], info
    prompt = sam_video.box_prompt(box, (cw, ch))
    key = hashlib.sha256(data + prompt.encode()).hexdigest()[:16]
    hit = cache / f"echo-sam-{key}.json" if cache else None
    if hit and hit.exists():
        res = json.loads(hit.read_text())
        info["cached"] = True
    else:
        res = caller(prompt, data, forward=True)
        if hit:
            hit.parent.mkdir(parents=True, exist_ok=True)
            hit.write_text(json.dumps(res))
    n = int((res.get("usage") or {}).get("video_frames_processed") or 0)
    info.update(frames_sent=n, usd_est=sam_video.usd(n))
    objs = sam_video.parse(res.get("text", ""), (cw, ch), decode_masks=False)
    nfr = max(objs) + 1 if objs else 0
    track = []
    for k in range(nfr):
        o = next((x for x in objs.get(k, []) if x.object_id == "1"), None)
        track.append((round(t0 + k / SAM_FPS, 4), (o.box[1] + o.box[3]) / 2 if o else None))
    info["frames_tracked"] = sum(1 for _, y in track if y is not None)
    return track, info


def agreement(a: list[tuple[float, float | None]], b: list[tuple[float, float | None]], tol_px: float,
              lag_s: float = 0.0) -> float | None:
    """Share of SAM frames whose centre is within tol_px of the fallback's centre on the nearest source frame."""
    bt = [(t, y) for t, y in b if y is not None]
    if not bt:
        return None
    ts = np.array([t for t, _ in bt])
    n = ok = 0
    for t, y in a:
        if y is None:
            continue
        j = int(np.abs(ts - t - lag_s).argmin())
        n += 1
        ok += abs(bt[j][1] - y) <= tol_px
    return round(ok / n, 3) if n else None


def observe(path: Path, after_t: float, until_t: float, *, use_sam: bool, cache: Path | None = None,
            caller=None) -> VideoObs:
    fps, size, frames = scan(path, max(0.0, after_t - 0.5), until_t)
    menu = menu_window(frames, after_t, fps)
    obs = VideoObs(fps=fps, size=size, menu=menu)
    if not menu["present"]:
        return obs
    obs.row_pitch = menu_row_pitch(frames, menu)
    fb = fallback_track(frames, menu)
    if use_sam:
        try:
            tr, info = sam_track(path, menu, size, cache=cache, caller=caller)
        except Exception as e:  # noqa: BLE001  any SAM failure -> deterministic fallback, said so in the sidecar
            tr, info = [], {"error": type(e).__name__ if not str(e).startswith(("http_", "network", "api_key"))
                            else str(e)}
        obs.sam = info
        if tr and sum(1 for _, y in tr if y is not None) >= 0.8 * len(tr):
            obs.track, obs.tracker = tr, "sam-3.1"
            obs.fallback_agreement = agreement(tr, fb, size[1] / 60)
            return obs
    obs.track, obs.tracker = fb, "deterministic_fallback"
    return obs
