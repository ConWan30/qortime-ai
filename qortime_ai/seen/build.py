"""Build seen.json (schema seen.v0) + overlay clips + stills for the public match 170123 highlight clips.

python -m qortime_ai.seen --clips DIR --cache DIR --out DIR [--spark] [--ledger spend.jsonl] [--render]
  * SAM outputs come from CACHE (made once by qortime_ai.seen.fetch; per-frame masks stay out of the repo).
  * Muse Spark captions are cached in qortime_ai/seen/fixtures/spark_captions.json; --spark refreshes them (paid).
seen.json carries summary numbers only (no per-frame masks or boxes, nothing per player) and never a status.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from qortime_ai.seen import analyze as A
from qortime_ai.seen import captions as C
from qortime_ai.seen import sam_video

SCHEMA = "seen.v0"
LABEL = "visualization / info only — not a referee input"
FIXTURES = Path(__file__).parent / "fixtures"
CAPTIONS_PATH = FIXTURES / "spark_captions.json"
SPARK_MODEL = "muse-spark-1.3"
SPARK_USD = (1.25e-6, 4.25e-6)
SEGMENT_BASIS = ("Chain segments covered by QorCap's public highlight clips of this match, bound by segment seq + "
                 "segment sha256 (qorcap-highlights manifest) and the receipt checkpoint each clip's score lock is in. "
                 "receipt.v0 does not publish which segments the motion rule's random draw sampled, so these are NOT "
                 "claimed to be the referee's motion sample.")
ENERGY_BASIS = ("Frame-difference energy as in the referee's motion_series (mean |gray_t - gray_t-1|), recomputed at "
                "640x360 on the public clip, split by SAM 3.1 masks: players = 'football player' masks, hud = the "
                "box-prompted scorebug mask, rest = everything else (field, crowd, camera). QorCap's burned-in label is "
                "excluded. motion_permille in the receipt is a controller-vs-video correlation; this explains only its "
                "video side and does not recompute it.")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def receipt_jcs_sha256(receipt: dict[str, Any]) -> str:
    from qor_receipt.jcs import canonicalize

    return hashlib.sha256(canonicalize(receipt)).hexdigest()


def verifier_status(receipt: dict[str, Any], allowlist: Path | None) -> str | None:
    """Status from the PRE-EXISTING verifier (qor_receipt.receipt.verify_receipt), used only to pick gold vs aqua."""
    from qor_receipt.receipt import verify_receipt

    pub = (receipt.get("referee") or {}).get("pubkey")
    return verify_receipt(receipt, referee_pub=pub, allowlist_path=str(allowlist) if allowlist else None).get("status")


def analyze_clip(clip: dict[str, Any], receipt: dict[str, Any], cache: Path) -> tuple[dict[str, Any], A.Tracks]:
    cid = clip["id"]
    gray = A.gray_frames(cache / f"{cid}.640.mp4")
    n = len(gray)
    sb_raw = json.loads((cache / f"{cid}.scorebug.json").read_text())
    pl_raw = json.loads((cache / f"{cid}.players.json").read_text())
    tr = A.load_tracks(sb_raw["text"], pl_raw["text"], n, cache / f"{cid}.tracks.npz")
    e = A.energy_split(gray, tr)
    segs = A.segments_for_clip(clip, n)
    out_segs = []
    for s in segs:
        out_segs.append({"seq": s["seq"], "segment_sha256": s["segment_sha256"], "t0": s["t0"], "t1": s["t1"],
                         "scorebug": A.scorebug_continuity(tr, s["f0"], s["f1"]),
                         "motion_pct": A.pct3(e[s["f0"]:s["f1"]].sum(0))})
    ev = A.events_for_clip(clip, receipt, segs, n)
    for x in ev:   # one summary reference box (median over the window, 640x360) for the web viewer's still
        f0, f1 = int(x["t0"] * A.FPS), int(x["t1"] * A.FPS)
        if x["track"] == "scorebug":
            bx = [tr.sb_box[f] for f in range(f0, min(f1, n)) if A.in_place(tr, f)]
        else:
            bx = [b for b in tr.pl_box[f0:f1] if not np.isnan(b).any()]
        x["box_ref"] = [int(round(v)) for v in np.median(bx, axis=0)] if bx else None
    lock = clip["lock"]
    doc = {"id": cid, "clip_sha256": clip["sha256"], "frames": n, "fps": A.FPS,
           "lock": {"checkpoint": next((v["cite"] for v in ev if v["kind"] == "score_lock"), None),
                    "hash": lock["hash"], "segment_seq": lock.get("segment_seq"), "t_s": clip["lock_at_s"]},
           "sam_frames_processed": {"scorebug": int(sb_raw["usage"].get("video_frames_processed") or 0),
                                    "players": int(pl_raw["usage"].get("video_frames_processed") or 0)},
           "scorebug": A.scorebug_continuity(tr, 0, n), "motion_pct": A.pct3(e.sum(0)),
           "player_objects_tracked": tr.pl_ids, "segments": out_segs, "lens_events": ev}
    return doc, tr


def spark_captions(clips: list[dict[str, Any]], receipt: dict[str, Any], ledger: Path | None) -> dict[str, Any]:
    from qortime_ai.ai_ruling.muse import MuseClient

    cli = MuseClient(model=SPARK_MODEL, max_tokens=4000, reasoning_effort="low", timeout_s=120)
    out: dict[str, Any] = {"model": SPARK_MODEL, "system": C.SYSTEM, "clips": {}}
    for c in clips:
        r = cli.chat(C.SYSTEM, C.user_prompt(c["segments"], receipt))
        pi, po = r.usage.get("prompt_tokens", 0), r.usage.get("completion_tokens", 0)
        usd = pi * SPARK_USD[0] + po * SPARK_USD[1]
        out["clips"][c["id"]] = {"text": r.text, "usage": r.usage}
        if ledger:
            with open(ledger, "a") as f:
                f.write(json.dumps({"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                                    "tag": "sam overlay oct27", "step": f"sam overlay oct27 spark captions {c['id']}",
                                    "model": SPARK_MODEL, "http": 200, "prompt_tokens": pi, "completion_tokens": po,
                                    "usd_est": round(usd, 6)}) + "\n")
    return out


def build(manifest: dict[str, Any], receipt: dict[str, Any], cache: Path, *, spark: bool = False,
          ledger: Path | None = None, captions_path: Path = CAPTIONS_PATH) -> tuple[dict[str, Any], dict[str, A.Tracks]]:
    clips, tracks = [], {}
    for c in manifest["clips"]:
        d, tr = analyze_clip(c, receipt, cache)
        clips.append(d)
        tracks[c["id"]] = tr
    if spark:
        captions_path.write_text(json.dumps(spark_captions(clips, receipt, ledger), indent=1) + "\n")
    cap = json.loads(captions_path.read_text()) if captions_path.exists() else {"clips": {}}
    for d in clips:
        C.finalize(d["segments"], receipt, C.parse_reply((cap["clips"].get(d["id"]) or {}).get("text", "")),
                   cap.get("model", SPARK_MODEL))
    sam_frames = sum(v for d in clips for v in d["sam_frames_processed"].values())
    doc = {"schema": SCHEMA, "label": LABEL, "affects_verdict": False, "emits_status": False,
           "built_during": "Meta AI Developer Hackathon, Oct 26 - Nov 4 2026 (built Oct 27 2026)",
           "match_id": (receipt.get("match") or {}).get("match_id"),
           "receipt_jcs_sha256": receipt_jcs_sha256(receipt),
           "receipt_file_sha256": manifest["receipt"]["sha256"],
           "models": {"tracking": sam_video.MODEL, "captions": cap.get("model", SPARK_MODEL),
                      "mask_decoding": "meta-sam-parser 0.1.0"},
           "prompts": [{"type": "box", "target": "scorebug", "box_640x360": list(sam_video.REFEREE_SCOREBUG_ROI),
                        "source": "the referee's madden27_standard scorebug OCR region", "propagation": "forward",
                        "objects": 1},
                       {"type": "concept", "text": sam_video.CONCEPT_PROMPT, "use": "motion attribution only (aggregate %)"}],
           "segment_basis": SEGMENT_BASIS, "energy_basis": ENERGY_BASIS,
           "lens_basis": "Evidence Lens windows come from the receipt timeline (score-lock checkpoint, challenge windows) "
                         "and the lock's receipt-bound segment; positions come from SAM tracks. Gold only for a score "
                         "lock when the pre-existing verifier returns VERIFIED; never decided by AI.",
           "not_published": "per-frame masks, per-frame boxes, anything per player",
           "clips": clips,
           "cost_usd_est": {"sam": round(sam_frames * sam_video.USD_PER_1K_FRAMES / 1000, 4)}}
    return doc, tracks
