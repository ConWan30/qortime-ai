"""Overlay render: Evidence Lens (holographic box at receipt moments only) + HUD bar + corner label -> H.264 MP4.

Frames are drawn with numpy/OpenCV (lens, glow, scanline, shimmer) and Pillow (text), then piped to ffmpeg.
Aqua on near-black navy; gold ONLY for a score-lock lens on a receipt the pre-existing verifier calls VERIFIED.
Visualization only: nothing drawn here feeds the referee.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from qortime_ai.seen import lens
from qortime_ai.seen.analyze import FPS, Tracks, in_place

CORNER_LABEL = "SAM 3.1 · visualization, not a referee input"
NAVY = (32, 16, 11)            # BGR of #0B1020
AQUA = (214, 230, 46)          # BGR of #2EE6D6
GOLD = (74, 184, 232)          # BGR of #E8B84A (referee-VERIFIED score lock only)
PANEL_H = 120
FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")


def _font(size: int, mono: bool = False):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(FONTS[1 if mono else 0], size)
    except OSError:
        return ImageFont.load_default()


def track_box(ev: dict[str, Any], tr: Tracks, f: int, scale: float) -> tuple[int, int, int, int] | None:
    """See _track_box. Returns None for a scorebug lens when the scorebug is not in place on this frame."""
    if ev["track"] == "scorebug" and not in_place(tr, f):
        return None
    return _track_box(ev, tr, f, scale)


def _track_box(ev: dict[str, Any], tr: Tracks, f: int, scale: float) -> tuple[int, int, int, int] | None:
    """Lens position from SAM: the scorebug object's box (last in-place box if it left), or the players' union box
    (smoothed over +-3 frames). Render-only; never published per frame."""
    if ev["track"] == "scorebug":
        g = next((k for k in range(f, -1, -1) if in_place(tr, k)), None)
        b = tr.sb_box[g] if g is not None else None
    else:
        win = tr.pl_box[max(0, f - 3): f + 4]
        win = win[~np.isnan(win).any(axis=1)]
        b = np.median(win, axis=0) if len(win) else None
    if b is None:
        return None
    return tuple(int(round(v * scale)) for v in b)


def draw_lens(img: np.ndarray, box: tuple[int, int, int, int], st: dict[str, Any], f: int) -> None:
    import cv2

    H, W = img.shape[:2]
    pad = 6
    x1, y1, x2, y2 = max(box[0] - pad, 2), max(box[1] - pad, 2), min(box[2] + pad, W - 3), min(box[3] + pad, H - 3)
    col = GOLD if st["color"] == lens.GOLD else AQUA
    a, ph, p = st["alpha"], st["phase"], st["p"]
    rng = np.random.default_rng(f)
    layer = np.zeros_like(img)
    # corner brackets draw in from the corners while materializing
    L = int(min(x2 - x1, y2 - y1, 60) * (0.45 if ph != "materialize" else 0.45 * max(p, 0.05)))
    L = max(L, 4)
    for cx, cy, sx, sy in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        cv2.line(layer, (cx, cy), (cx + sx * L * 2, cy), col, 3, cv2.LINE_AA)
        cv2.line(layer, (cx, cy), (cx, cy + sy * L), col, 3, cv2.LINE_AA)
    frame = layer.copy()
    cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2, cv2.LINE_AA)
    shimmer = 0.85 + 0.15 * rng.random()
    glow = cv2.GaussianBlur(cv2.dilate(frame, np.ones((5, 5), np.uint8)), (0, 0), 6)
    out = img.astype(np.float32)
    out[y1:y2, x1:x2] = out[y1:y2, x1:x2] * (1 - 0.10 * a) + np.array(col, np.float32) * 0.10 * a   # faint holo fill
    out += glow.astype(np.float32) * (1.4 * a * shimmer)
    out += frame.astype(np.float32) * (0.75 * a * shimmer)
    if ph == "materialize":                      # one horizontal scanline sweep through the box
        sy = int(y1 + (y2 - y1) * p)
        sl = np.zeros_like(img)
        cv2.line(sl, (x1, sy), (x2, sy), (255, 255, 255), 2, cv2.LINE_AA)
        out += cv2.GaussianBlur(sl, (0, 0), 2).astype(np.float32) * 0.8
        noise = (rng.random((y2 - y1, x2 - x1, 1)) < 0.03) * np.array(col, np.float32) * 0.6
        out[y1:y2, x1:x2] += noise
    np.clip(out, 0, 255, out=out)
    img[:] = out.astype(np.uint8)


def _text(img: np.ndarray, items: list[tuple[tuple[int, int], str, int, tuple, bool, float]]) -> None:
    """items: ((x, y), text, size, bgr, mono, alpha). Pillow, anti-aliased, Unicode."""
    from PIL import Image, ImageDraw

    pil = Image.fromarray(img[:, :, ::-1])
    over = Image.new("RGBA", pil.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for (x, y), t, size, bgr, mono, al in items:
        d.text((x, y), t, font=_font(size, mono), fill=(bgr[2], bgr[1], bgr[0], int(255 * al)))
    img[:] = np.array(Image.alpha_composite(pil.convert("RGBA"), over).convert("RGB"))[:, :, ::-1]


def _tag(img: np.ndarray, box: tuple[int, int, int, int], text: str, col: tuple, alpha: float) -> None:
    import cv2

    from PIL import ImageDraw, Image

    f = _font(17, mono=True)
    w = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(text, font=f)) + 20
    x = min(max(box[0], 8), img.shape[1] - w - 8)
    y = box[1] - 40 if box[1] - 40 > 8 else box[3] + 12
    ov = img.copy()
    cv2.rectangle(ov, (x, y), (x + w, y + 28), NAVY, -1)
    img[:] = cv2.addWeighted(ov, 0.82 * alpha, img, 1 - 0.82 * alpha, 0)
    cv2.rectangle(img, (x, y), (x + w, y + 28), tuple(int(c * alpha) for c in col), 1, cv2.LINE_AA)
    _text(img, [((x + 10, y + 4), text, 17, col, True, alpha)])


def tag_text(ev: dict[str, Any], seg: dict[str, Any] | None) -> str:
    if ev["kind"] == "score_lock":
        s = ev["score"]
        return f"SCORE READ AWAY {s['away']}–HOME {s['home']} · [{ev['cite']}]"
    if ev["kind"] == "motion_segment":
        extra = f" · players {seg['motion_pct']['players']}%" if seg else ""
        return f"MOTION SEGMENT {ev['seq']}{extra} · [{ev['cite']}]"
    return f"CHALLENGE WINDOW · [{ev['cite']}]"


def _wrap(text: str, n: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > n:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return out + ([cur] if cur else [])


def render_clip(src: Path, dst: Path, clip: dict[str, Any], tr: Tracks, verifier_status: str | None,
                crf: int = 30) -> None:
    import cv2

    cap = cv2.VideoCapture(str(src))
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = W / 640.0
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H + PANEL_H}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", str(crf), "-preset", "slow",
                             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)], stdin=subprocess.PIPE)
    segs = clip["segments"]
    f = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        t = f / FPS
        canvas = np.zeros((H + PANEL_H, W, 3), np.uint8)
        canvas[:] = NAVY
        canvas[:H] = fr
        img = canvas[:H]
        seg = next((s for s in segs if s["t0"] <= t < s["t1"]), None)
        for ev in clip["lens_events"]:
            st = lens.state(ev, t, verifier_status)
            if st is None or f >= len(tr.sb_box):
                continue
            if ev["track"] == "players":     # soft translucent player fill, only inside the motion-segment window
                m = cv2.resize(tr.pl_mask[f].astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST).astype(bool)
                tint = img.astype(np.float32)
                tint[m] = tint[m] * (1 - 0.22 * st["alpha"]) + np.array(AQUA, np.float32) * 0.22 * st["alpha"]
                img[:] = tint.astype(np.uint8)
            b = track_box(ev, tr, f, scale)
            if b is None:
                last = _track_box(ev, tr, f, scale) if ev["track"] == "scorebug" else None
                if last is not None and (st["phase"] != "materialize" or st["p"] > 0.5):   # tag only, no box
                    _tag(img, last, tag_text(ev, None) + " · scorebug not on screen now (SAM)", AQUA, st["alpha"])
                continue
            draw_lens(canvas if ev["track"] == "scorebug" else img, b, st, f)   # scorebug lens may spill into the bar
            if st["phase"] != "materialize" or st["p"] > 0.5:
                _tag(img, b, tag_text(ev, next((s for s in segs if s["seq"] == ev.get("seq")), None)),
                     GOLD if st["color"] == lens.GOLD else AQUA, st["alpha"])
        # HUD bar (bottom panel): attribution numbers + cited caption + corner label
        items = [((W - 470, H + 92), CORNER_LABEL, 16, AQUA, False, 0.9)]
        if seg:
            mo, sb = seg["motion_pct"], seg["scorebug"]
            items.append(((20, H + 10), f"SEGMENT {seg['seq']} · motion energy: players {mo['players']}% · HUD {mo['hud']}% · "
                          f"rest of screen {mo['rest']}% · scorebug in place {sb['in_place']}/{sb['frames']} frames",
                          18, AQUA, True, 1.0))
            for i, line in enumerate(_wrap(seg["caption"], 118)[:2]):
                items.append(((20, H + 40 + 22 * i), line, 16, (235, 235, 235), False, 0.95))
        _text(canvas, items)
        proc.stdin.write(canvas.tobytes())
        f += 1
    proc.stdin.close()
    proc.wait()
    cap.release()
