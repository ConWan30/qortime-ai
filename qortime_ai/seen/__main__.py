"""python -m qortime_ai.seen --clips DIR --cache DIR --out DIR [--spark --ledger L] [--render DIR] [--allowlist F]"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from qortime_ai.seen import build as B


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True, type=Path)      # dir with manifest.json + public hl clips
    ap.add_argument("--receipt", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)        # seen.json + stills (committed)
    ap.add_argument("--render", type=Path)                    # overlay MP4s (kept out of git unless < 5 MB)
    ap.add_argument("--allowlist", type=Path)
    ap.add_argument("--spark", action="store_true")
    ap.add_argument("--ledger", type=Path)
    ap.add_argument("--stills", default="")                   # e.g. hl01-q4-a9-h0@8.1,hl02-q4-a10-h0@8.2
    a = ap.parse_args(argv)
    manifest = json.loads((a.clips / "manifest.json").read_text())
    receipt = json.loads(a.receipt.read_text())
    if B.sha256_file(a.receipt) != manifest["receipt"]["sha256"]:
        print("receipt does not match the highlights manifest", file=sys.stderr)
        return 2
    doc, tracks = B.build(manifest, receipt, a.cache, spark=a.spark, ledger=a.ledger)
    a.out.mkdir(parents=True, exist_ok=True)
    if a.render:
        from qortime_ai.seen.render import render_clip

        status = B.verifier_status(receipt, a.allowlist)
        a.render.mkdir(parents=True, exist_ok=True)
        for c in doc["clips"]:
            dst = a.render / f"{c['id']}.seen.mp4"
            render_clip(a.clips / f"{c['id']}.mp4", dst, c, tracks[c["id"]], status)
            c["overlay"] = {"file": dst.name, "sha256": B.sha256_file(dst), "bytes": dst.stat().st_size}
            print(c["id"], "overlay", dst, dst.stat().st_size, "bytes")
        for spec in filter(None, a.stills.split(",")):
            cid, t = spec.split("@")
            still = a.out / f"{cid}_t{t}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", t, "-i", str(a.render / f"{cid}.seen.mp4"),
                            "-frames:v", "1", "-q:v", "4", str(still)], check=True)
            print("still", still)
    (a.out / "seen.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print("wrote", a.out / "seen.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
