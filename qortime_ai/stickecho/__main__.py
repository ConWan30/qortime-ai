"""Stick Echo CLI (built Oct 28 2026). Two steps, so footage and per-frame data never leave the machine:

  python -m qortime_ai.stickecho track VIDEO --window START_S DUR_S CONTEXT [--window ...] --out tracks.json
         [--no-sam | --yes-send-to-meta] [--max-calls 6] [--cache DIR] [--ledger FILE]
  python -m qortime_ai.stickecho score tracks.json inputs.jsonl --null-log OTHER.jsonl [--null-log ...]
         (--lag-ms N | --echo-sidecar echo.sidecar.json ...) [--video-start-us N] [--selection sam|hybrid|marker]
         [--response-offset-ms N] [--checks menu,switch] [--receipt receipt.v0.json] [--out stickecho.sidecar.json]
  python -m qortime_ai.stickecho check stickecho.sidecar.json

``track`` writes PRIVATE per-frame tracks (keep them local). SAM 3.1 needs META_API_KEY (never printed) and an
explicit --yes-send-to-meta; --no-sam keeps the marker track only. ``score`` writes the totals-only sidecar
(default next to --receipt, else ./stickecho.sidecar.json). The lag must be fixed before scoring: take it from this
game's Challenge Echo sidecar(s), never from the lag sweep, which is printed as a diagnostic only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import statistics
import sys
from pathlib import Path
from typing import Any

from qortime_ai.stickecho import checks as CK
from qortime_ai.stickecho import score as SC
from qortime_ai.stickecho import select as SE
from qortime_ai.stickecho import sidecar as S
from qortime_ai.stickecho.log import StickLog

TRACKS_SCHEMA = "qortime.stickecho.tracks.v0"


def lag_from_echo(paths: list[Path]) -> tuple[float, dict[str, Any]]:
    """Median press-to-screen latency of the CONSISTENT Challenge Echo clips; their spread is the drift check."""
    lat = []
    for p in paths:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        lat += [c["latency_median_ms"] for c in doc.get("clips", []) if c.get("status") == "consistent"
                and c.get("latency_median_ms") is not None]
    if not lat:
        raise SystemExit("no consistent Challenge Echo clip: cannot fix the lag beforehand (pass --lag-ms)")
    return statistics.median(lat) / 1000, {"lag_source": "challenge_echo", "echo_clips": len(lat),
                                           "echo_spread_ms": int(max(lat) - min(lat))}


def cmd_track(a) -> int:
    from qortime_ai.stickecho import video as V

    if not a.no_sam and not a.yes_send_to_meta:
        raise SystemExit("refusing: pass --yes-send-to-meta (each window is one short video-only clip sent to SAM 3.1), "
                         "or --no-sam for the marker track only")
    if len(a.window) > a.max_calls and not a.no_sam:
        raise SystemExit(f"{len(a.window)} windows exceed --max-calls {a.max_calls}")
    wins, cost = [], {"sam_frames": 0, "usd_est": 0.0}
    for start, dur, ctx in a.window:
        start, dur = float(start), min(float(dur), V.MAX_CLIP_S)
        fr = V.frames(a.video, start, dur)
        tr = V.track_marker([V.candidates(f) for f in fr])
        anc = V.anchors(fr, tr)
        if not anc:
            print(f"  window {start:.2f}s: no stable marker to seed, skipped (no call)")
            continue
        k0 = anc[0][0]
        if k0:                                   # SAM propagates forward: start at the first prompt
            start, dur = start + k0 / V.FPS, dur - k0 / V.FPS
            fr = V.frames(a.video, start, dur)           # re-decode from the trimmed start (same as the SAM clip)
            tr = tr[k0:k0 + len(fr)]
            anc = [(k - k0, b) for k, b in anc]
        boxes = None
        if not a.no_sam:
            boxes, info = V.sam_boxes(a.video, start, dur, anc, cache=a.cache)
            if not info["cached"]:
                cost["sam_frames"] += info["frames_sent"]
                cost["usd_est"] += info["usd_est"]
                if a.ledger:
                    with open(a.ledger, "a") as f:
                        f.write(json.dumps({"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                                            "tag": "stick echo", "step": f"track {start:.1f}s", "model": info["model"],
                                            "video_frames": info["frames_sent"], "usd_est": info["usd_est"]}) + "\n")
        wins.append(V.window_track(fr, boxes, start, ctx, tr=tr))
        print(f"  window {start:.2f}s ({ctx}): {len(fr)} frames, {len(anc)} seed box(es), "
              f"tracker {'none (marker only)' if boxes is None else 'sam-3.1'}")
    doc = {"schema": TRACKS_SCHEMA, "private": "per-frame data: keep local, never publish", "fps": V.FPS,
           "video_start_us": a.video_start_us, "tracker": "none" if a.no_sam else "sam-3.1", "windows": wins,
           "cost": {"sam_frames": cost["sam_frames"], "usd_est_micro": round(cost["usd_est"] * 1e6)}}
    a.out.write_text(json.dumps(doc) + "\n")
    print(f"tracks -> {a.out} (PRIVATE)")
    return 0


def run_score(tracks: dict[str, Any], log: StickLog, nulls: dict[str, StickLog], *, lag_s: float, selection: str,
              response_offset_ms: int = 0, video_start_us: int | None = None,
              checks: tuple[str, ...] = ()) -> tuple[dict, dict, dict]:
    """``checks`` (EXPLORATORY, drop-only): see ``checks.py``. Counts go to ``src["checks"]``."""
    vsu = int(tracks.get("video_start_us") if video_start_us is None else video_start_us)
    lag = lag_s + response_offset_ms / 1000
    circle = log.press_times(CK.CIRCLE_BIT) if "switch" in checks else None
    wins, src = [], {"sam": 0, "marker": 0, "dropped": 0}
    ck: dict[str, int] = {}
    for w in tracks["windows"]:
        V, s = SE.select(w, selection)
        for k in src:
            src[k] += s[k]
        if checks:
            V, c = CK.apply(w, V, checks, circle_t_us=circle, video_start_us=vsu, lag_s=lag_s)  # screen lag
            for k, v in c.items():
                ck[k] = ck.get(k, 0) + int(v)
        wins.append({"start_s": float(w["start_s"]), "V": V})
    if checks:
        src = {**src, "checks": ck}
    ev = SC.evaluate(wins, log, nulls, video_start_us=vsu, lag_s=lag)
    sweep = SC.lag_sweep(wins, log, video_start_us=vsu, lag_s=lag)
    return ev, src, sweep


def cmd_score(a) -> int:
    tracks = json.loads(a.tracks.read_text(encoding="utf-8"))
    if tracks.get("schema") != TRACKS_SCHEMA:
        raise SystemExit("not a Stick Echo tracks file")
    if a.lag_ms is not None:
        lag_s, clock = a.lag_ms / 1000, {"lag_source": "supplied --lag-ms"}
    elif a.echo_sidecar:
        lag_s, clock = lag_from_echo(a.echo_sidecar)
    else:
        raise SystemExit("the lag must be fixed beforehand: pass --echo-sidecar (this game's pauses) or --lag-ms")
    log = StickLog.from_path(a.inputs, "same_game")
    nulls = {"same_game": log}
    for i, p in enumerate(a.null_log, start=1):
        nulls[f"other_game_{i}"] = StickLog.from_path(p, f"other_game_{i}")
    if a.selection == "sam" and tracks.get("tracker") != "sam-3.1":
        raise SystemExit("selection 'sam' needs a SAM 3.1 tracks file")
    checks = tuple(c for c in (a.checks or "").split(",") if c)
    for c in checks:
        if c not in CK.CHECKS:
            raise SystemExit(f"--checks: unknown check {c!r} (choose from {', '.join(CK.CHECKS)})")
    ev, src, sweep = run_score(tracks, log, nulls, lag_s=lag_s, selection=a.selection,
                               response_offset_ms=a.response_offset_ms, video_start_us=a.video_start_us, checks=checks)
    method = {"tracker": tracks.get("tracker"), "selection": a.selection, "lag_ms": round(lag_s * 1000),
              "response_offset_ms": a.response_offset_ms, "checks": list(checks),
              "preregistered": a.selection == SE.PREREGISTERED and a.response_offset_ms == 0 and not checks}
    clock = {**clock, "video_start_us": int(tracks.get("video_start_us") if a.video_start_us is None else a.video_start_us),
             "rule": "stick sample at frame time minus the lag (input clock); lag fixed before scoring"}
    peak = max(sweep, key=sweep.get) if sweep else None
    diag = {"lag_sweep_peak_offset_ms": None if peak is None else round(peak * 1000),
            "note": "lag sweep is a diagnostic only; it never sets the lag"}
    rj = None
    if a.receipt:
        from qortime_ai.ai_ruling.signing import receipt_jcs_sha256

        rj = receipt_jcs_sha256(json.loads(a.receipt.read_text(encoding="utf-8")))
    c = tracks.get("cost") or {}
    doc = S.build(ev, method=method, sources=src, clock=clock, receipt_jcs_sha256=rj, diagnostics=diag,
                  cost={"sam_frames": int(c.get("sam_frames", 0)), "sam_usd_est_micro": int(c.get("usd_est_micro", 0))})
    out = a.out or ((a.receipt.parent if a.receipt else Path(".")) / "stickecho.sidecar.json")
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(doc["summary"])
    for n in doc["nulls"]:
        print(f"  null {n['source']}: " + (n.get("error") or f"mean {n['mean_permille']}/1000, z {n['z_centi'] / 100:.2f}"))
    print(f"  lag sweep peak (diagnostic only): {diag['lag_sweep_peak_offset_ms']} ms from the fixed lag -> {out}")
    return 0


def cmd_check(a) -> int:
    p = S.check(json.loads(a.sidecar.read_text(encoding="utf-8")))
    print("ok" if not p else "problems: " + ", ".join(p))
    return 0 if not p else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="qortime_ai.stickecho")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("track")
    t.add_argument("video", type=Path)
    t.add_argument("--window", nargs=3, action="append", required=True, metavar=("START_S", "DUR_S", "CONTEXT"))
    t.add_argument("--out", type=Path, required=True)
    t.add_argument("--video-start-us", type=int, required=True, help="input-clock time (t_us) of the video's frame 0")
    t.add_argument("--no-sam", action="store_true")
    t.add_argument("--yes-send-to-meta", action="store_true")
    t.add_argument("--max-calls", type=int, default=6)
    t.add_argument("--cache", type=Path)
    t.add_argument("--ledger", type=Path)
    s = sub.add_parser("score")
    s.add_argument("tracks", type=Path)
    s.add_argument("inputs", type=Path)
    s.add_argument("--null-log", action="append", default=[], required=True)
    s.add_argument("--lag-ms", type=int)
    s.add_argument("--echo-sidecar", type=Path, action="append")
    s.add_argument("--video-start-us", type=int)
    s.add_argument("--selection", choices=SE.SELECTIONS, default=SE.PREREGISTERED)
    s.add_argument("--response-offset-ms", type=int, default=0,
                   help="EXPLORATORY: extra movement response time added to the Echo lag; must be fixed from other games")
    s.add_argument("--checks", default="",
                   help="EXPLORATORY drop-only free checks, comma list of: " + ",".join(CK.CHECKS))
    s.add_argument("--receipt", type=Path)
    s.add_argument("--out", type=Path)
    c = sub.add_parser("check")
    c.add_argument("sidecar", type=Path)
    a = ap.parse_args(argv)
    return {"track": cmd_track, "score": cmd_score, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
