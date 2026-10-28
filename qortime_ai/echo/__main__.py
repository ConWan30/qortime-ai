"""python -m qortime_ai.echo VIDEO INPUTS_JSONL --video-start-us N [--pattern LEFT,DOWN,RIGHT,UP] [--no-sam]
       [--cache DIR] [--ledger FILE] [--release-gap-ms MS] [--receipt receipt.v0.json] [--id NAME] [--out FILE]

VIDEO is one capture (or a clip of it) holding one pause challenge. ``--video-start-us`` is the input-clock time
(t_us) of the video's frame 0. Writes echo.sidecar.json (default next to --receipt, else ./echo.sidecar.json).
SAM 3.1 needs META_API_KEY (never printed); without it, or with --no-sam, the deterministic tracker is used.
Keep VIDEO, INPUTS and --cache local: the cache holds per-frame SAM output.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

from qortime_ai.echo import match as M
from qortime_ai.echo import sidecar as S
from qortime_ai.echo.presses import press_events


def run_clip(video: Path, records: list[dict[str, Any]], video_start_us: int, pattern: list[str], *,
             use_sam: bool = True, cache: Path | None = None, release_gap_us: int | None = None,
             clip_id: str = "c0", caller=None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(clip result for the sidecar, sam info). Pure orchestration of presses -> video -> match."""
    from qortime_ai.echo import video as V

    ev = press_events(records, release_gap_us=release_gap_us)
    pr = [{"t": (e["t_us"] - video_start_us) / 1e6, "button": e["button"]} for e in ev]
    opt = next((p for p in pr if p["button"] == "OPTIONS" and p["t"] > -1.0), None)
    if opt is None:
        res = M.score_clip([], [], {"present": False}, pattern)
        return {"id": clip_id, **res, "tracker": "none"}, {}
    pr = [p for p in pr if p["t"] >= opt["t"]]
    end = next((p["t"] for p in pr if p["button"] == "CROSS"), opt["t"] + 20)
    obs = V.observe(video, opt["t"], end + M.LAT_MAX_MS / 1000 + 1.0, use_sam=use_sam, cache=cache, caller=caller)
    moves = M.moves_from_track(obs.track, obs.size[1]) if obs.track else []
    res = M.score_clip(pr, moves, obs.menu, pattern)
    out = {"id": clip_id, **res, "tracker": obs.tracker, "frame_step_ms": round(1000 / (V.SAM_FPS if obs.tracker ==
           "sam-3.1" else obs.fps)), "highlight_moves_seen": len(moves)}
    if obs.fallback_agreement is not None:
        out["sam_vs_fallback_agreement_permille"] = round(obs.fallback_agreement * 1000)
    return out, obs.sam


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="qortime_ai.echo")
    ap.add_argument("video", type=Path)
    ap.add_argument("inputs", type=Path)
    ap.add_argument("--video-start-us", type=int, required=True)
    ap.add_argument("--pattern", default="LEFT,DOWN,RIGHT,UP")
    ap.add_argument("--no-sam", action="store_true")
    ap.add_argument("--cache", type=Path)
    ap.add_argument("--ledger", type=Path)
    ap.add_argument("--release-gap-ms", type=int)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--id", default="c0")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    pattern = [x.strip().upper() for x in a.pattern.split(",") if x.strip()]
    recs = [json.loads(x) for x in a.inputs.read_text(encoding="utf-8").splitlines() if x.strip()]
    clip, sam = run_clip(a.video, recs, a.video_start_us, pattern, use_sam=not a.no_sam, cache=a.cache,
                         release_gap_us=a.release_gap_ms * 1000 if a.release_gap_ms else None, clip_id=a.id)
    rj = None
    if a.receipt:
        from qortime_ai.ai_ruling.signing import receipt_jcs_sha256

        rj = receipt_jcs_sha256(json.loads(a.receipt.read_text(encoding="utf-8")))
    clock = {"video_start_source": "supplied --video-start-us",
             "release_rule": f"gap > {a.release_gap_ms} ms = release (non-zero-only extract)" if a.release_gap_ms
             else "rising edges"}
    cost = {"sam_frames": sam.get("frames_sent") or 0, "sam_usd_est_micro": round((sam.get("usd_est") or 0) * 1e6),
            "cached": bool(sam.get("cached"))} if sam else None
    doc = S.build([clip], pattern=pattern, clock=clock, receipt_jcs_sha256=rj, cost=cost)
    if a.ledger and sam and not sam.get("cached") and sam.get("frames_sent"):
        with open(a.ledger, "a") as f:
            f.write(json.dumps({"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                                "tag": "challenge echo", "step": f"echo {a.id}", "model": sam.get("model"),
                                "video_frames": sam["frames_sent"], "usd_est": sam.get("usd_est")}) + "\n")
    out = a.out or ((a.receipt.parent if a.receipt else Path(".")) / "echo.sidecar.json")
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{a.id}: {clip['status']} ({clip.get('why') or 'ok'}), directions {clip['directions_matched']}/"
          f"{clip['directions_total']}, median latency {clip.get('latency_median_ms')} ms, tracker {clip['tracker']}"
          f" -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
