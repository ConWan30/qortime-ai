"""Meta SAM 3.1 video tracking: request building, streaming call, and mask decoding via Meta's ``meta-sam-parser``.

Two prompts per public clip:
  * BOX prompt = the referee's own scorebug OCR region (``REFEREE_SCOREBUG_ROI``), forward propagation, one object id;
  * CONCEPT prompt "football player", used only to split frame-difference energy into aggregate regions.
Visualization / info only. Nothing here is a referee input or a status signal.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from qortime_ai.ai_ruling.muse import BASE_URL, _open, api_key_from_env

MODEL = "sam-3.1"
USD_PER_1K_FRAMES = 0.20
MIN_FRAMES_BILLED = 50
CONCEPT_PROMPT = "football player"
# The referee's madden27_standard scorebug OCR region at its 640x360 reference scale: the union of the profile's
# logo (8-80, 340-358), score_panel (200-300, 341-357) and clock_box (428-484, 341-356) boxes in
# qor_receipt/_vendor/qoresence/vision/local_scorebug/profile.py (pre-existing). (left, top, right, bottom), half-open.
REF_W, REF_H = 640, 360
REFEREE_SCOREBUG_ROI = (8, 340, 485, 359)


class SamVideoError(Exception):
    """Network/format failure. Message never contains the key."""


def box_prompt(roi: tuple[int, int, int, int] = REFEREE_SCOREBUG_ROI, size: tuple[int, int] = (REF_W, REF_H)) -> str:
    """SAM object-prompt text that seeds object 1 on frame 0 with the referee's scorebug ROI."""
    from meta_sam_parser import FramePrompt, PromptBox, PromptObject, build_object_prompt

    return build_object_prompt(size=size, objects=[PromptObject(id=1, prompts=[FramePrompt(frame=0, box=PromptBox(*roi))])])


def request_body(prompt: str, video: bytes, *, forward: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {"model": MODEL, "stream": True, "input": [{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": prompt},
        {"type": "input_video", "video_url": "data:video/mp4;base64," + base64.b64encode(video).decode()}]}]}
    body["metadata"] = {"include_confidence": "true", **({"propagation_direction": "forward"} if forward else {})}
    return body


def usd(frames: int) -> float:
    return round(max(int(frames or 0), MIN_FRAMES_BILLED) * USD_PER_1K_FRAMES / 1000, 6)


def call(prompt: str, video: bytes, *, forward: bool = False, api_key: str | None = None, base_url: str = BASE_URL,
         timeout_s: float = 300.0) -> dict[str, Any]:
    """POST /v1/responses (SSE). Returns {"text", "usage", "http", "secs"}; text is the concatenated output_text."""
    key = api_key or api_key_from_env()
    if not key:
        raise SamVideoError("api_key_missing")
    req = urllib.request.Request(f"{base_url.rstrip('/')}/responses", method="POST",
                                 data=json.dumps(request_body(prompt, video, forward=forward)).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                          "Accept": "text/event-stream"})
    t, parts, usage = time.time(), [], {}
    try:
        with _open(req, timeout_s) as r:
            status = r.status
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                ev = json.loads(line[6:])
                if ev.get("type") == "response.output_text.delta":
                    parts.append(ev.get("delta") or "")
                elif ev.get("type") == "response.completed":
                    usage = (ev.get("response") or {}).get("usage") or {}
    except urllib.error.HTTPError as e:
        raise SamVideoError(f"http_{e.code}") from None
    except Exception as e:  # noqa: BLE001
        raise SamVideoError(f"network:{type(e).__name__}") from None
    return {"text": "".join(parts), "usage": usage, "http": status, "secs": round(time.time() - t, 1)}


@dataclass(frozen=True)
class Obj:
    frame: int
    object_id: str
    box: tuple[float, float, float, float]          # left, top, right, bottom (source pixels)
    confidence: float | None
    mask: Any = None                                # numpy bool array at frame size, or None


def parse(text: str, frame_size: tuple[int, int], *, decode_masks: bool = True) -> dict[int, list[Obj]]:
    """Per-frame objects from SAM's video output text, decoded with Meta's meta-sam-parser."""
    from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, video_segmentation_format

    p = video_segmentation_format().create_parser()
    p.push(text if text.endswith("\n") else text + "\n", emit=False)
    res = p.finish(CompletedOutcome()).result
    w, h = frame_size
    boxes: dict[tuple[int, str], tuple] = {}
    masks: dict[tuple[int, str], Any] = {}
    for rec in res.records:
        if rec.kind not in ("box", "mask") or rec.frame is None:
            continue
        k = (rec.frame.frame_index, rec.object_id)
        if rec.kind == "box":
            boxes[k] = ((rec.left, rec.top, rec.right, rec.bottom), rec.confidence)
        elif decode_masks:
            masks[k] = _place(rec, decode_mask_to_raster(rec.mask), w, h)
    out: dict[int, list[Obj]] = {}
    for k in sorted(set(boxes) | set(masks)):
        b, c = boxes.get(k, (None, None))
        m = masks.get(k)
        if b is None and m is not None:
            ys, xs = m.nonzero()
            b = (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)) if len(xs) else None
        if b is None:
            continue
        out.setdefault(k[0], []).append(Obj(k[0], k[1], tuple(float(v) for v in b), c, m))
    return out


def _place(rec: Any, raster: bytes, w: int, h: int):
    """Box-local raster -> full-frame bool mask (nearest-neighbour resize into the half-open bounds)."""
    import numpy as np
    import cv2

    mw, mh = rec.mask.width, rec.mask.height
    local = np.frombuffer(raster, dtype=np.uint8)[: mw * mh].reshape(mh, mw)
    l, t, r, b = (int(round(v)) for v in (rec.bounds.left, rec.bounds.top, rec.bounds.right, rec.bounds.bottom))
    full = np.zeros((h, w), dtype=bool)
    l2, t2, r2, b2 = max(l, 0), max(t, 0), min(r, w), min(b, h)
    if r2 <= l2 or b2 <= t2:
        return full
    if (r - l, b - t) != (mw, mh):
        local = cv2.resize(local, (r - l, b - t), interpolation=cv2.INTER_NEAREST)
    full[t2:b2, l2:r2] = local[t2 - t:b2 - t, l2 - l:r2 - l] > 0
    return full
