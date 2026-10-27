"""Paid step (run once, by hand): SAM 3.1 video calls for the public 170123 highlight clips; raw outputs cached.

python -m qortime_ai.seen.fetch CLIPS_DIR CACHE_DIR LEDGER   (key from META_API_KEY; never printed)
Each clip is re-encoded to 640x360 @30 fps (the referee's reference scale) before upload. The cache holds per-frame
masks, so it stays OUT of the repo; only summary numbers reach seen.json.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

from qortime_ai.seen import sam_video

CLIPS = ("hl00-q3-a3-h0", "hl01-q4-a9-h0", "hl02-q4-a10-h0")   # public match 170123 highlight clips only
TAG = "sam overlay oct27"


def small(src: Path, dst: Path) -> Path:
    if not dst.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "scale=640:360,fps=30", "-an",
                        "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(dst)], check=True)
    return dst


def log(ledger: Path, row: dict) -> None:
    row = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "tag": TAG, **row}
    with open(ledger, "a") as f:
        f.write(json.dumps(row) + "\n")


def main(argv: list[str]) -> int:
    clips_dir, cache, ledger = Path(argv[0]), Path(argv[1]), Path(argv[2])
    cache.mkdir(parents=True, exist_ok=True)
    for cid in CLIPS:
        vid = small(clips_dir / f"{cid}.mp4", cache / f"{cid}.640.mp4").read_bytes()
        for kind, prompt, fwd in (("scorebug", sam_video.box_prompt(), True), ("players", sam_video.CONCEPT_PROMPT, False)):
            out = cache / f"{cid}.{kind}.json"
            if out.exists():
                continue
            try:
                r = sam_video.call(prompt, vid, forward=fwd)
            except sam_video.SamVideoError as e:
                log(ledger, {"step": f"sam overlay {cid} {kind}", "model": sam_video.MODEL, "error": str(e), "usd_est": 0})
                print(cid, kind, "ERROR", e)
                continue
            n = int(r["usage"].get("video_frames_processed") or 0)
            log(ledger, {"step": f"sam overlay oct27 {cid} {kind} (public 170123 clip, 640x360)", "model": sam_video.MODEL,
                         "http": r["http"], "video_frames": n, "usd_est": sam_video.usd(n)})
            out.write_text(json.dumps({"clip": cid, "kind": kind, "prompt": prompt, "forward": fwd, **r}))
            print(cid, kind, "http", r["http"], "frames", n, "secs", r["secs"], "chars", len(r["text"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
