"""'What the referee saw' (SAM 3.1 Evidence Lens) — offline tests. Built Oct 27 2026 (Meta AI Developer Hackathon)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from qortime_ai.seen import analyze as A
from qortime_ai.seen import captions as C
from qortime_ai.seen import lens
from qortime_ai.seen.build import CAPTIONS_PATH, receipt_jcs_sha256

ROOT = Path(__file__).resolve().parents[1]
SEEN = json.loads((ROOT / "examples/170123/seen.json").read_text())
RECEIPT_PATH = ROOT / "examples/170123/receipt.json"
FORBIDDEN = {"status", "verdict", "cap", "max_cap", "masks", "boxes", "per_frame", "frames_data"}


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


# ---- Evidence Lens timing and colour ----
def test_lens_only_inside_event_windows():
    inside = 0
    for c in SEEN["clips"]:
        for f in range(c["frames"]):
            t = f / c["fps"]
            for ev in c["lens_events"]:
                st = lens.state(ev, t, "VERIFIED")
                if t < ev["t0"] or t >= ev["t1"]:
                    assert st is None, (c["id"], ev["kind"], t)
                else:
                    assert st is not None
                    inside += 1
    assert inside > 0


def test_lens_phases():
    ev = {"kind": "score_lock", "t0": 8.0, "t1": 10.5}
    assert lens.state(ev, 8.1)["phase"] == "materialize"
    assert lens.state(ev, 9.0)["phase"] == "hold" and lens.state(ev, 9.0)["alpha"] == 1.0
    assert lens.state(ev, 10.3)["phase"] == "dissolve"
    assert lens.state(ev, 7.99) is None and lens.state(ev, 10.5) is None


def test_gold_only_for_verified_score_lock():
    assert lens.color_for("score_lock", "VERIFIED") == lens.GOLD
    for st in ("PARTIAL", "FAIL", "SELF_ATTESTED", None):
        assert lens.color_for("score_lock", st) == lens.AQUA
    for kind in ("motion_segment", "challenge"):
        assert lens.color_for(kind, "VERIFIED") == lens.AQUA
    ev = {"kind": "motion_segment", "t0": 0, "t1": 2}
    assert lens.state(ev, 1.0, "VERIFIED")["color"] == lens.AQUA


def test_lens_windows_come_from_receipt_timeline():
    for c in SEEN["clips"]:
        kinds = {e["kind"] for e in c["lens_events"]}
        assert "score_lock" in kinds
        sl = next(e for e in c["lens_events"] if e["kind"] == "score_lock")
        assert sl["t0"] == c["lock"]["t_s"] and sl["cite"] == c["lock"]["checkpoint"]
        ms = next(e for e in c["lens_events"] if e["kind"] == "motion_segment")
        assert ms["seq"] == c["lock"]["segment_seq"]


# ---- seen.json: info only, summary only, bound to the receipt ----
def test_seen_json_is_info_only_and_summary_only():
    assert SEEN["schema"] == "seen.v0" and SEEN["affects_verdict"] is False and SEEN["emits_status"] is False
    assert "not a referee input" in SEEN["label"]
    assert not (FORBIDDEN & set(_keys(SEEN)))
    assert len(json.dumps(SEEN)) < 40_000            # summary numbers only, no per-frame data
    for c in SEEN["clips"]:
        assert set(c["motion_pct"]) == {"players", "hud", "rest"} and sum(c["motion_pct"].values()) == 100
        for s in c["segments"]:
            assert sum(s["motion_pct"].values()) in (0, 100)


def test_seen_bound_to_receipt():
    if not RECEIPT_PATH.exists():
        pytest.skip("run scripts/fetch_upstream.sh")
    r = json.loads(RECEIPT_PATH.read_text())
    assert SEEN["receipt_jcs_sha256"] == receipt_jcs_sha256(r)
    r["result"]["home_score"] = 31
    assert SEEN["receipt_jcs_sha256"] != receipt_jcs_sha256(r)


def test_published_captions_pass_gates_offline():
    if not RECEIPT_PATH.exists():
        pytest.skip("run scripts/fetch_upstream.sh")
    r = json.loads(RECEIPT_PATH.read_text())
    cached = json.loads(CAPTIONS_PATH.read_text())
    for c in SEEN["clips"]:
        segs = [{k: v for k, v in s.items() if not k.startswith("caption")} for s in c["segments"]]
        C.finalize(segs, r, C.parse_reply(cached["clips"][c["id"]]["text"]), cached["model"])
        for got, pub in zip(segs, c["segments"]):
            assert got["caption"] == pub["caption"]
            assert not C.gate(got["caption"], C.facts(got, r))


# ---- caption gates ----
SEG = {"seq": 448, "motion_pct": {"players": 9, "hud": 1, "rest": 90},
       "scorebug": {"frames": 60, "in_place": 60, "off_roi": 0, "dropouts": 0}}


@pytest.mark.parametrize("text,problem", [
    ("Players moved fast here [seen.motion.players_pct].", "coach_language"),
    ("The best route ran 9% [seen.motion.players_pct].", "coach_language"),
    ("Motion 9 players [seen.motion.players_pct].", "percent_without_%"),
    ("Scorebug VERIFIED [seen.scorebug.in_place].", "status_mismatch"),
    ("Players 12% [seen.motion.players_pct].", "number_not_in_cited_fields"),
    ("Players 9%.", "missing_citation"),
    ("Certified clean, players 9% [seen.motion.players_pct].", "banned_word"),
])
def test_caption_gate_rejects(text, problem):
    assert any(p.startswith(problem) for p in C.gate(text, C.facts(SEG, {})))


def test_template_caption_passes_and_fallback_used():
    seg = dict(SEG)
    C.finalize([seg], {}, {448: "Fastest players were 9% [seen.motion.players_pct]."}, "muse-spark-1.3")
    assert seg["caption_source"] == "template" and seg["caption_rejected"]
    assert not C.gate(seg["caption"], C.facts(seg, {}))


# ---- analysis on synthetic arrays ----
def _tracks(n=4):
    H, W = A.REF_H, A.REF_W
    sb = np.zeros((n, H, W), bool)
    x1, y1, x2, y2 = A.REFEREE_SCOREBUG_ROI
    sb[:, y1:y2, x1:x2] = True
    pl = np.zeros((n, H, W), bool)
    pl[:, 100:200, 100:200] = True
    box = np.tile(np.array([x1, y1, x2, y2], float), (n, 1))
    return A.Tracks(box, np.full(n, 0.9), sb, pl, np.full((n, 4), np.nan), 1)


def test_energy_split_attributes_by_mask():
    tr = _tracks()
    g = np.zeros((4, A.REF_H, A.REF_W), np.int16)
    g[1, 100:200, 100:200] = 50        # players region changes
    g[2, 345:355, 50:100] = 20         # scorebug region changes
    g[3, 150:160, 400:500] = 10        # elsewhere changes
    g[3, 0:10, 0:10] = 200             # QorCap burn-in label: excluded
    e = A.energy_split(g, tr)
    assert e[0].sum() == 0 and e[1][0] > 0 and e[1][1] == 0
    assert A.pct3(e.sum(0))["players"] + A.pct3(e.sum(0))["hud"] + A.pct3(e.sum(0))["rest"] == 100
    assert e[:, :].sum() == 50 * 100 * 100 * 2 + 20 * 10 * 50 * 2 + 10 * 10 * 100


def test_scorebug_continuity_flags_swap_and_dropout():
    tr = _tracks(6)
    tr.sb_mask[3] = False
    tr.sb_mask[3, 50:60, 50:60] = True      # SAM's object moved elsewhere (another graphic)
    tr.sb_conf[5] = np.nan                  # dropout
    r = A.scorebug_continuity(tr, 0, 6)
    assert (r["in_place"], r["off_roi"], r["dropouts"]) == (4, 1, 1)
    assert r["first_not_in_place_s"] == round(3 / A.FPS, 2)


def test_box_prompt_is_referee_roi():
    pytest.importorskip("meta_sam_parser")
    from qortime_ai.seen.sam_video import box_prompt, request_body

    assert box_prompt() == "<0f>1<|box;x1=8;y1=340;x2=484;y2=358;w=640;h=360|>"
    b = request_body(box_prompt(), b"x", forward=True)
    assert b["model"] == "sam-3.1" and b["metadata"]["propagation_direction"] == "forward"
