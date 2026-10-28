"""Video side of Stick Echo: controlled-player marker, SAM 3.1 seed boxes, camera-compensated motion. Deterministic
except for the SAM 3.1 call. Needs OpenCV, numpy and ffmpeg (``pip install -e '.[seen]'``).

* Marker (Madden NFL 27 default): the controlled player stands on a flat hexagon with a NEON green / teal / gold
  outline (often only the right and bottom edges lit) and a dark see-through fill. Filled badges and signs, long open
  curves (landing arc, route art), oversize shapes and non-neon (white/black) hexagons are rejected by shape gates.
* SAM 3.1: one object, box prompt on the body standing on the marker, first prompt on a frame where the marker has
  been stable for 5 frames, re-anchored every 2 s on stable frames. The clip is the analysis window only (<= 10 s,
  video only, no audio), sent at 960x540; boxes are scaled back to the 640x360 analysis grid.
* Motion: the feet point's frame-to-frame displacement after removing camera motion (homography from tracked
  background corners outside the player's box), smoothed over 7 frames.
Per-frame output is private (``tracks.json``, kept local); only totals reach the sidecar.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

W, H, FPS = 640, 360, 30.0
SEND_W, SEND_H = 960, 540
MAX_CLIP_S = 10.0
REANCHOR_FRAMES = 60
SMOOTH = 7


def _cv2():
    import cv2

    return cv2


def frames(video: Path, start: float = 0.0, dur: float | None = None, w: int = W, h: int = H) -> list[np.ndarray]:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video)]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vf", f"fps={FPS:g},scale={w}:{h}", "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = w * h * 3
    return [np.frombuffer(raw[i:i + n], np.uint8).reshape(h, w, 3) for i in range(0, len(raw) - n + 1, n)]


def encode_clip(video: Path, start: float, dur: float, out: Path, w: int = SEND_W, h: int = SEND_H) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{dur:.3f}",
                    "-vf", f"fps={FPS:g},scale={w}:{h}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True)
    return out


# ---------------------------------------------------------------- controlled-player marker
def candidates(f: np.ndarray) -> list[dict[str, Any]]:
    cv2 = _cv2()
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    fh, fw = f.shape[:2]
    h_, s_, v_ = (hsv[..., i].astype(np.int16) for i in range(3))
    m = (((h_ >= 58) & (h_ <= 95) & (s_ >= 110) & (v_ >= 140)) | ((h_ >= 18) & (h_ < 36) & (s_ > 140) & (v_ > 200))).astype(np.uint8)
    m[int(fh * 0.915):] = 0
    m[:int(fh * 0.12)] = 0
    n0, lab0, st0, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros_like(m)
    for i in range(1, n0):
        if st0[i, 4] >= 5:
            keep[lab0 == i] = 1
    n, _, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(keep, np.ones((5, 11), np.uint8)), 8)
    V, S, Hh = hsv[..., 2], hsv[..., 1], hsv[..., 0]
    out = []
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        if w < 10 or h < 4:
            continue
        sub = keep[y:y + h, x:x + w]
        a = int(sub.sum())
        if a < 12:
            continue
        x0, x1, y0, y1 = max(0, int(x - 0.6 * w)), min(fw, x + w), max(0, y), min(fh, y + h)
        rv, rs, rh = V[y0:y1, x0:x1].astype(np.int16), S[y0:y1, x0:x1], Hh[y0:y1, x0:x1]
        nn = keep[y0:y1, x0:x1] == 0
        den = max(int(nn.sum()), 1)
        dark = float(((rv < 75) & nn).sum() / den)
        star = float(((rs < 60) & (rv > 190) & nn).sum() / den)
        bx0, bx1 = int(max(0, x + 0.15 * w)), int(min(fw, x + 0.85 * w))
        by1 = int(y + 0.5 * h)
        by0 = int(max(0, by1 - max(20, 0.7 * w)))
        bh = hsv[by0:by1, bx0:bx1]
        body = 0.0
        if bh.size:
            turf = (bh[..., 0] >= 35) & (bh[..., 0] <= 95) & (bh[..., 1] > 60)
            body = float((~turf & ~((bh[..., 1] < 60) & (bh[..., 2] > 200))).mean())
        # hexagon centre: span the dark fill + star + neon columns left of the lit corner
        ex0, ex1 = max(0, int(x - 0.9 * w)), min(fw, x + w)
        regm = (keep[y:y + h, ex0:ex1] > 0) | (V[y:y + h, ex0:ex1] < 75) | ((S[y:y + h, ex0:ex1] < 60) & (V[y:y + h, ex0:ex1] > 190))
        cols = np.where(regm.mean(0) > 0.25)[0]
        hx = float(x + w / 2)
        if len(cols):
            cs = set(cols.tolist())
            right = int(cols[cols <= x + w - 1 - ex0].max()) if (cols <= x + w - 1 - ex0).any() else int(cols.max())
            run_l = right
            while any(run_l - g in cs for g in (1, 2, 3)):
                run_l -= next(g for g in (1, 2, 3) if run_l - g in cs)
            hx = float(ex0 + (run_l + right) / 2)
        out.append(dict(hx=hx, cx=float(x + w / 2), cy=float(y + h / 2), w=int(w), h=int(h), area=a,
                        fill=a / (w * h), ar=w / max(h, 1), dark=dark, star=star, body=body))
    return out


def is_marker(c: dict[str, Any]) -> bool:
    if c["w"] < 10 or c["w"] > 135 or c["h"] > 55:
        return False
    if c["ar"] < 1.5 and c["fill"] > 0.25:      # filled round badge
        return False
    if c["ar"] > 6:                             # lines / route art
        return False
    if c["w"] >= 30 and c["dark"] < 0.06 and c["star"] < 0.04:
        return False                            # open curve over turf (landing arc)
    return c["fill"] <= 0.45                    # filled signs


def track_marker(cands: list[list[dict[str, Any]]], lost_after: int = 10) -> list[tuple | None]:
    """Per frame (hx, cy, w, h, cx_neon) or None. Continuity-scored; video only, never the stick log."""
    out, prev, last = [], None, -99
    for k, cs in enumerate(cands):
        if k - last > lost_after:
            prev = None
        best = None
        for c in cs:
            if not is_marker(c):
                continue
            s = c["area"] * (0.5 + 2 * c["dark"] + 2 * c["star"] + c["body"])
            if prev is not None:
                dd = float(np.hypot(c["cx"] - prev[0], c["cy"] - prev[1]))
                if dd > 40 + 0.5 * c["w"]:
                    continue
                s -= 3 * dd
            if best is None or s > best[0]:
                best = (s, c)
        if best is None:
            out.append(None)
            continue
        c = best[1]
        prev, last = (c["cx"], c["cy"]), k
        out.append((c["hx"], c["cy"], c["w"], c["h"], c["cx"]))
    return out


def eff_w(w: float, h: float) -> float:
    return min(w, 1.3 * h + 10)


def seed_box(f: np.ndarray, m: tuple) -> tuple[int, int, int, int] | None:
    """SAM seed box: the biggest non-turf body blob whose feet sit in the marker's rows, left of the lit corner."""
    cv2 = _cv2()
    fh, fw = f.shape[:2]
    hx, cy, w, h, cxn = m
    w = max(eff_w(w, h), 14)
    l, r = int(max(0, min(hx, cxn) - 1.8 * w)), int(min(fw, max(hx, cxn) + 0.4 * w))
    t, b = int(max(0, cy - max(45, 1.4 * w))), int(min(fh, cy + 0.6 * max(h, 8)))
    if r - l < 8 or b - t < 12:
        return None
    hsv = cv2.cvtColor(f[t:b, l:r], cv2.COLOR_BGR2HSV)
    turf = (hsv[..., 0] >= 35) & (hsv[..., 0] <= 95) & (hsv[..., 1] > 60)
    line = (hsv[..., 1] < 60) & (hsv[..., 2] > 185)
    fill = (hsv[..., 2] < 60) & (np.arange(t, b)[:, None] >= cy - 0.5 * max(h, 8))
    body = (~turf & ~line & ~fill).astype(np.uint8)
    body = cv2.morphologyEx(body, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    body = cv2.morphologyEx(body, cv2.MORPH_CLOSE, np.ones((5, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(body, 8)
    best = None
    for i in range(1, n):
        x, y, ww, hh, a = st[i]
        feet = t + y + hh
        if a < 25 or hh < 10 or hh < 0.4 * ww:
            continue
        if not (cy - 0.8 * max(h, 8) - 6 <= feet <= cy + 0.8 * max(h, 8) + 4):
            continue
        sc = a - abs(l + x + ww / 2 - (cxn - 0.6 * w))
        if best is None or sc > best[0]:
            best = (sc, (l + x - 2, t + y - 2, l + x + ww + 2, t + y + hh + 2))
    if best is None:
        return None
    x0, y0, x1, y1 = best[1]
    return max(0, int(x0)), max(0, int(y0)), min(fw - 1, int(x1)), min(fh - 1, int(y1))


def anchors(fr: list[np.ndarray], tr: list[tuple | None]) -> list[tuple[int, tuple[int, int, int, int]]]:
    """Seed + re-anchor boxes on frames where the marker has been stable for 5 frames; size-checked."""
    def stable(k):
        ts = tr[max(0, k - 4):k + 1]
        if len(ts) < 5 or any(t is None for t in ts):
            return False
        ws = [t[2] for t in ts]
        return max(ws) <= 1.4 * min(ws) and max(abs(ts[i][4] - ts[i - 1][4]) for i in range(1, 5)) < 15

    def ok_box(b, t):
        we = eff_w(t[2], t[3])
        return b is not None and 0.5 * we <= b[3] - b[1] <= 2.5 * we + 20 and b[2] - b[0] <= 1.2 * we + 12

    out: list = []
    for k in range(4, len(fr)):
        if (not out or k - out[-1][0] >= REANCHOR_FRAMES) and stable(k):
            b = seed_box(fr[k], tr[k])
            if ok_box(b, tr[k]) and (not out or b[3] - b[1] <= 1.6 * (out[0][1][3] - out[0][1][1]) + 6):
                out.append((k, b))
    return out


# ---------------------------------------------------------------- motion
def camera_homography(g0: np.ndarray, g1: np.ndarray, exclude=None):
    cv2 = _cv2()
    mask = np.zeros_like(g0)
    mask[int(H * 0.12):int(H * 0.915)] = 255
    if exclude is not None:
        l, t, r, b = (int(v) for v in exclude)
        mask[max(0, t - 10):b + 10, max(0, l - 10):r + 10] = 0
    p0 = cv2.goodFeaturesToTrack(g0, 400, 0.01, 6, mask=mask)
    if p0 is None or len(p0) < 20:
        return None
    p1, st, _ = cv2.calcOpticalFlowPyrLK(g0, g1, p0, None, winSize=(21, 21), maxLevel=3)
    ok = st.ravel() == 1
    if ok.sum() < 20:
        return None
    hm, _ = cv2.findHomography(p0[ok], p1[ok], cv2.RANSAC, 2.0)
    return hm


def field_velocity(fr: list[np.ndarray], pts: list, boxes: list) -> dict[int, np.ndarray]:
    """Camera-compensated per-frame motion (px/frame, 640x360) of a point, smoothed over 7 frames."""
    cv2 = _cv2()
    g = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in fr]
    raw = {}
    for k in range(len(g) - 1):
        if pts[k] is None or pts[k + 1] is None:
            continue
        hm = camera_homography(g[k], g[k + 1], boxes[k])
        if hm is None:
            continue
        p = cv2.perspectiveTransform(np.array([[pts[k]]], np.float32), hm)[0, 0]
        raw[k] = np.array(pts[k + 1]) - p
    return {k: np.mean([raw[j] for j in range(k - SMOOTH // 2, k + SMOOTH // 2 + 1) if j in raw], 0) for k in raw}


# ---------------------------------------------------------------- SAM 3.1
def sam_prompt(objects: dict[int, list], size: tuple[int, int]) -> str:
    from meta_sam_parser import FramePrompt, PromptBox, PromptObject, build_object_prompt

    return build_object_prompt(size=tuple(size), objects=[PromptObject(id=int(i), prompts=[
        FramePrompt(frame=int(k), box=PromptBox(*map(int, b))) for k, b in anc]) for i, anc in sorted(objects.items())])


def sam_boxes(video: Path, start: float, dur: float, anc: list, *, cache: Path | None, caller=None) -> tuple[list, dict]:
    """One SAM 3.1 call (or a cache hit) for one window. Returns per-frame boxes at 640x360 and call info."""
    from qortime_ai.seen import sam_video

    caller = caller or sam_video.call
    sc = SEND_W / W
    with tempfile.TemporaryDirectory() as td:
        data = encode_clip(video, start, dur, Path(td) / "w.mp4").read_bytes()
    prompt = sam_prompt({1: [(k, tuple(v * sc for v in b)) for k, b in anc]}, (SEND_W, SEND_H))
    key = hashlib.sha256(data + prompt.encode()).hexdigest()[:16]
    hit = cache / f"stickecho-sam-{key}.json" if cache else None
    info: dict[str, Any] = {"model": sam_video.MODEL, "cached": False}
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
    objs = sam_video.parse(res.get("text", ""), (SEND_W, SEND_H), decode_masks=False)
    nfr = int(round(dur * FPS)) + 2
    boxes: list = [None] * nfr
    for k, lst in objs.items():
        if 0 <= k < nfr:
            for o in lst:
                if str(o.object_id) == "1":
                    boxes[k] = tuple(float(v) / sc for v in o.box)
    return boxes, info


def feet(b) -> tuple[float, float] | None:
    return None if b is None else ((b[0] + b[2]) / 2, b[3])


def window_track(fr: list[np.ndarray], boxes: list | None, start_s: float, context: str, score_from: int = 0,
                 tr: list | None = None) -> dict[str, Any]:
    """Private per-frame track for one window (the input to ``select``). ``boxes`` None = no SAM (marker only)."""
    tr = tr if tr is not None else track_marker([candidates(f) for f in fr])
    n = len(fr)
    mk = [None if t is None else (float(t[0]), float(t[1]), float(t[2])) for t in tr[:n]]
    mfeet = [None if m is None else (m[0], m[1]) for m in mk]
    mbox = [None if m is None else (m[0] - m[2], m[1] - 2.5 * m[2], m[0] + m[2], m[1] + 5) for m in mk]
    vm = field_velocity(fr, mfeet, mbox)
    out: dict[str, Any] = {"start_s": round(start_s, 4), "context": context, "score_from": int(score_from), "frames": n,
                           "marker": [None if m is None else [round(v, 2) for v in m] for m in mk],
                           "marker_vel": [None if k not in vm else [float(x) for x in vm[k]] for k in range(n)]}
    if boxes is not None:
        bx = (list(boxes) + [None] * n)[:n]
        vs = field_velocity(fr, [feet(b) for b in bx], bx)
        out["sam_feet"] = [None if b is None else [round(v, 2) for v in feet(b)] for b in bx]
        out["sam_vel"] = [None if k not in vs else [float(x) for x in vs[k]] for k in range(n)]
    return out
