"""Stick Echo (built Oct 28 2026, Meta AI Developer Hackathon). SYNTHETIC fixtures only: no real footage, no real
controller input. Stick logs are generated random walks; tracks are generated velocities; frames are drawn here."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import numpy as np
import pytest

from qortime_ai.stickecho import score as SC
from qortime_ai.stickecho import select as SE
from qortime_ai.stickecho import sidecar as S
from qortime_ai.stickecho.__main__ import TRACKS_SCHEMA, lag_from_echo, main, run_score
from qortime_ai.stickecho.log import StickLog

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ["VERIFIED", "PARTIAL", "SELF" + "_ATTESTED", "FAIL"]   # pre-existing verifier statuses
LAG = 1.4
VSU = 2_000_000          # input-clock time of video frame 0


def synth_records(seed: int, dur_s: float = 240.0, step_us: int = 5_000) -> list[dict]:
    """SYNTHETIC stick log: a new random direction every 0.75 s plus a small wander, mostly fully deflected."""
    rng = np.random.default_rng(seed)
    n = int(dur_s * 1e6 / step_us)
    ang = np.repeat(rng.uniform(-np.pi, np.pi, n // 150 + 1), 150)[:n] + np.cumsum(rng.normal(0, 0.03, n))
    mag = np.clip(0.9 + 0.3 * np.sin(np.arange(n) / 700.0), 0, 1)
    lx = np.clip(127.5 + 127.5 * mag * np.cos(ang), 0, 255).round().astype(int)
    ly = np.clip(127.5 + 127.5 * mag * np.sin(ang), 0, 255).round().astype(int)
    out = [{"type": "header", "schema": "qorcap-inputs/v0", "t_us": 0}]
    out += [{"type": "in", "t_us": i * step_us, "b": 0, "lx": int(a), "ly": int(b)} for i, (a, b) in enumerate(zip(lx, ly))]
    return out


@pytest.fixture(scope="module")
def logs():
    return StickLog(synth_records(1), "same"), StickLog(synth_records(2), "o1"), StickLog(synth_records(3), "o2")


def follow_window(log: StickLog, start_s: float, n: int = 120, lag: float = LAG, speed: float = 2.0, noise=0.0, seed=0):
    """Velocities that follow the stick one lag later (what an honest controlled player looks like)."""
    rng = np.random.default_rng(seed)
    t = SC.input_times(start_s, {k: 0 for k in range(n)}, VSU, lag)
    s = log.stick_at(t)
    v = speed * s / np.maximum(np.linalg.norm(s, axis=1, keepdims=True), 1e-9) + rng.normal(0, noise, (n, 2))
    return [list(map(float, x)) for x in v]


def track_doc(vel_windows, *, marker_vel=None, sam_feet=None, marker=None):
    wins = []
    for i, (start, vel) in enumerate(vel_windows):
        n = len(vel)
        wins.append({"start_s": start, "context": "defender", "score_from": 0, "frames": n, "sam_vel": vel,
                     "marker_vel": (marker_vel or {}).get(i, vel),
                     "sam_feet": (sam_feet or {}).get(i, [[100.0, 200.0]] * n),
                     "marker": (marker or {}).get(i, [[100.0, 200.0, 20.0]] * n)})
    return {"schema": TRACKS_SCHEMA, "fps": 30.0, "video_start_us": VSU, "tracker": "sam-3.1", "windows": wins,
            "cost": {"sam_frames": 0, "usd_est_micro": 0}}


# ---------------------------------------------------------------- log
def test_stick_axes_and_hold():
    lg = StickLog([{"type": "in", "t_us": 0, "lx": 255, "ly": 127.5}, {"type": "in", "t_us": 1_000_000, "lx": 127.5, "ly": 0}])
    assert np.allclose(lg.stick_at([0])[0], [1.0, 0.0])                    # right
    assert np.allclose(lg.stick_at([1_000_000])[0], [0.0, -1.0])           # up = -y (screen axes)
    assert np.allclose(lg.stick_at([500_000])[0], [1.0, 0.0])              # no report nearby: hold the last one
    with pytest.raises(ValueError):
        StickLog([{"type": "in", "t_us": 0, "b": 1}])


# ---------------------------------------------------------------- selection
def test_selection_sam_marker_hybrid():
    n = 40
    vs = [[2.0, 0.0]] * n
    vm = [[2.0, 0.0]] * 20 + [[0.0, 2.0]] * 20                       # SAM drifts to another player at frame 20
    feet = [[100.0, 200.0]] * 20 + [[300.0, 200.0]] * 20
    mk = [[100.0, 200.0, 20.0]] * n
    w = {"start_s": 0.0, "score_from": 0, "sam_vel": vs, "marker_vel": vm, "sam_feet": feet, "marker": mk}
    V, src = SE.select(w, "sam")
    assert len(V) == n and src["sam"] == n
    V, src = SE.select(w, "hybrid")
    assert src == {"sam": 20, "marker": 20, "dropped": 0}
    assert np.allclose(V[30], [0.0, 2.0])                            # the marker's motion, not the drifted SAM box
    V, src = SE.select(w, "marker")
    assert src["marker"] == n and np.allclose(V[5], [2.0, 0.0])
    with pytest.raises(ValueError):
        SE.select(w, "best_looking")


def test_hybrid_drops_switch_frames_and_respects_score_from():
    n = 30
    mk = [[100.0, 200.0, 20.0]] * 15 + [[400.0, 200.0, 20.0]] * 15   # marker jumps: control switched
    w = {"start_s": 0.0, "score_from": 5, "sam_vel": [[1.0, 0.0]] * n, "marker_vel": [[1.0, 0.0]] * n,
         "sam_feet": [[m[0], m[1]] for m in mk], "marker": mk}
    V, src = SE.select(w, "hybrid")
    assert min(V) >= 5
    assert all(k not in V for k in range(12, 19)) and src["dropped"] == 7
    w["marker"] = [None] * n
    w["marker_vel"] = [None] * n
    V, src = SE.select(w, "hybrid")
    assert not V and src["dropped"] == n - 5                         # no marker: unsure -> dropped, never guessed


def test_selection_never_reads_the_stick():
    import inspect

    assert "stick" not in inspect.signature(SE.select).parameters
    assert "StickLog" not in inspect.getsource(SE)


# ---------------------------------------------------------------- scoring
def test_cos_sum_gates():
    V = {0: np.array([1.0, 0.0]), 1: np.array([0.1, 0.0]), 2: np.array([0.0, 1.0])}
    s = np.array([[1.0, 0.0], [1.0, 0.0], [0.1, 0.0]])
    tot, n, hit = SC.cos_sum(V, s)
    assert (tot, n, hit) == (1.0, 1, 1)                              # slow player and idle stick frames are not scored


def test_honest_track_agrees_and_shifted_lag_does_not(logs):
    lg, o1, o2 = logs
    wins = [(s, follow_window(lg, s, noise=0.6, seed=i)) for i, s in enumerate((40.0, 90.0, 140.0))]
    doc = track_doc(wins)
    ev, src, sweep = run_score(doc, lg, {"same_game": lg, "o1": o1, "o2": o2}, lag_s=LAG, selection="sam")
    assert ev["frames"] >= 300 and ev["mean_cos"] > 0.6
    assert all(v["z"] >= 3 for v in ev["nulls"].values())
    assert S.decide(ev, 3) == "agree"
    assert abs(max(sweep, key=sweep.get)) <= 0.1                     # diagnostic peak sits at the fixed lag
    ev2, _, _ = run_score(doc, lg, {"same_game": lg, "o1": o1, "o2": o2}, lag_s=LAG + 3.0, selection="sam")
    assert ev2["mean_cos"] < 0.3 and S.decide(ev2, 3) in ("disagree", "inconclusive")


def test_other_players_track_disagrees(logs):
    lg, o1, o2 = logs
    other = StickLog(synth_records(99), "someone_else")
    wins = [(s, follow_window(other, s, seed=i)) for i, s in enumerate((40.0, 90.0, 140.0))]
    ev, _, _ = run_score(track_doc(wins), lg, {"same_game": lg, "o1": o1, "o2": o2}, lag_s=LAG, selection="sam")
    assert ev["frames"] >= 300
    assert max(v["z"] for v in ev["nulls"].values()) < 1
    doc = S.build(ev, method=METHOD, sources=SRC, clock={})
    assert doc["result"] == "disagree" and doc["cap"] == "PARTIAL"
    assert S.apply_to_result({"status": "VERIFIED"}, doc)["status"] == "PARTIAL"


def test_null_excludes_same_moment(logs):
    lg, _, _ = logs
    V = {k: np.array([1.0, 0.0]) for k in range(60)}
    t = SC.input_times(100.0, V, VSU, LAG)
    pool_same = SC.null_pool(lg, True, t, V)
    pool_other = SC.null_pool(lg, False, t, V)
    assert 0 < len(pool_same) < len(pool_other)


def test_evaluate_is_deterministic(logs):
    lg, o1, _ = logs
    doc = track_doc([(50.0, follow_window(lg, 50.0, seed=3))])
    a, _, _ = run_score(doc, lg, {"same_game": lg, "o1": o1}, lag_s=LAG, selection="sam")
    b, _, _ = run_score(doc, lg, {"same_game": lg, "o1": o1}, lag_s=LAG, selection="sam")
    assert a == b


# ---------------------------------------------------------------- sidecar: lower-only, capped at PARTIAL
def ev_with(z, frames=600):
    return {"windows": 6, "frames": frames, "mean_cos": 0.5, "within_45": 0.6, "min_z": min(z),
            "nulls": {f"n{i}": {"mean": 0.03, "sd": 0.14, "z": v, "share_ge": 0.0} for i, v in enumerate(z)}}


METHOD = {"tracker": "sam-3.1", "selection": "sam", "lag_ms": 1432, "response_offset_ms": 0, "preregistered": True}
SRC = {"sam": 600, "marker": 0, "dropped": 0}


@pytest.mark.parametrize("z,frames,result", [([3.9, 3.5, 3.1], 543, "agree"), ([3.9, 2.9], 600, "inconclusive"),
                                             ([0.5, 0.9, -1.0], 600, "disagree"), ([0.1, 0.2], 200, "unscorable")])
def test_decide(z, frames, result):
    doc = S.build(ev_with(z, frames), method=METHOD, sources=SRC, clock={"lag_source": "challenge_echo"})
    assert doc["result"] == result and not S.check(doc)
    assert doc["cap"] == ("PARTIAL" if result == "disagree" else None)


def test_missing_null_is_unscorable():
    ev = ev_with([4.0, 4.0])
    ev["nulls"]["n1"] = None
    doc = S.build(ev, method=METHOD, sources=SRC, clock={})
    assert doc["result"] == "unscorable" and doc["cap"] is None


def test_sidecar_integers_only_and_totals_only():
    doc = S.build(ev_with([3.9, 3.5, 3.1]), method=METHOD, sources=SRC, clock={"lag_source": "challenge_echo"},
                  diagnostics={"lag_sweep_peak_offset_ms": 300})
    txt = json.dumps(doc)
    assert S._ints_only(doc)
    assert doc["totals"]["frames_scored"] == 600 and doc["min_z_centi"] == 310
    assert "per_window" not in txt and "frames_selected_by_source" in txt
    bad = dict(doc, totals=dict(doc["totals"], mean_cos_permille=0.5))
    assert "float_values" in S.check(bad)


@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize("z", [[3.9, 3.5, 3.1], [3.9, 2.0], [0.2, 0.1], [0.1]])
def test_lower_only_never_raises(status, z):
    doc = S.build(ev_with(z), method=METHOD, sources=SRC, clock={})
    out = S.apply_to_result({"status": status}, doc)
    order = {"VERIFIED": 3, "PARTIAL": 2, "SELF" + "_ATTESTED": 1, "FAIL": 0}
    assert order[out["status"]] <= order[status]
    if status != "VERIFIED":
        assert out["status"] == status
    if doc["result"] == "disagree" and status == "VERIFIED":
        assert out["status"] == "PARTIAL" and S.CAP_CODE in out["partial"]


def test_tampered_sidecar_is_ignored():
    doc = S.build(ev_with([3.9, 3.5, 3.1]), method=METHOD, sources=SRC, clock={})
    for bad in (dict(doc, cap="FAIL"), dict(doc, cap="PARTIAL"), dict(doc, affects_verdict="decides"),
                dict(doc, emits_status=True), dict(doc, result="VERIFIED"), "not json", None):
        assert S.check(bad)
        assert S.apply_to_result({"status": "VERIFIED"}, bad) == {"status": "VERIFIED"}
    with pytest.raises(ValueError):
        S.apply_cap("VERIFIED", "FAIL")


def test_wording():
    from qortime_ai.redteam.wording import banned_hits

    doc = S.build(ev_with([3.9, 3.5, 3.1]), method=METHOD, sources=SRC, clock={})
    texts = [S.LABEL, S.SAM_ROLE, doc["summary"], (ROOT / "docs" / "STICK_ECHO.md").read_text(encoding="utf-8"),
             (ROOT / "qortime_ai" / "stickecho" / "README.md").read_text(encoding="utf-8")]
    for t in texts:
        assert banned_hits(t) == [], t[:80]
        assert not re.search(r"proves? (that )?a human|\bwager|\bbet(s|ting)?\b|gambl|QorCap Box", t, re.I)
    assert "controller and video agree" in doc["summary"]


# ---------------------------------------------------------------- CLI
def write_jsonl(p: Path, recs):
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return p


def test_cli_score_and_check(tmp_path, logs):
    lg, _, _ = logs
    inp = write_jsonl(tmp_path / "inputs.jsonl", synth_records(1))
    n1 = write_jsonl(tmp_path / "o1.jsonl", synth_records(2))
    wins = [(s, follow_window(lg, s, noise=0.6, seed=i)) for i, s in enumerate((40.0, 90.0, 140.0))]
    tr = tmp_path / "tracks.json"
    tr.write_text(json.dumps(track_doc(wins)))
    echo = tmp_path / "echo.sidecar.json"
    echo.write_text(json.dumps({"clips": [{"status": "consistent", "latency_median_ms": 1400},
                                          {"status": "consistent", "latency_median_ms": 1410},
                                          {"status": "mismatch", "latency_median_ms": 900}]}))
    out = tmp_path / "stickecho.sidecar.json"
    assert main(["score", str(tr), str(inp), "--null-log", str(n1), "--echo-sidecar", str(echo), "--out", str(out)]) == 0
    doc = json.loads(out.read_text())
    assert doc["result"] == "agree" and doc["method"]["preregistered"] is True
    assert doc["clock"]["echo_spread_ms"] == 10 and doc["method"]["lag_ms"] == 1405
    assert main(["check", str(out)]) == 0
    assert main(["score", str(tr), str(inp), "--null-log", str(n1), "--lag-ms", "1400", "--selection", "hybrid",
                 "--response-offset-ms", "200", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["method"]["preregistered"] is False
    with pytest.raises(SystemExit):
        main(["score", str(tr), str(inp), "--null-log", str(n1), "--out", str(out)])       # no lag fixed beforehand


def test_lag_from_echo_needs_a_consistent_clip(tmp_path):
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"clips": [{"status": "partial", "latency_median_ms": 1500}]}))
    with pytest.raises(SystemExit):
        lag_from_echo([p])


def test_cli_track_refuses_to_send_without_consent(tmp_path):
    with pytest.raises(SystemExit, match="yes-send-to-meta"):
        main(["track", str(tmp_path / "v.mp4"), "--window", "0", "3", "defender", "--video-start-us", "0",
              "--out", str(tmp_path / "t.json")])


# ---------------------------------------------------------------- video (drawn synthetic frames)
def draw_frame(cv2, hx: int, hy: int, cam_dx: int = 0):
    """Turf with yard lines (moving with the camera) and a player standing on a neon hexagon."""
    f = np.zeros((360, 640, 3), np.uint8)
    f[:] = (40, 120, 40)                                              # green turf (BGR)
    for x in range(-40, 700, 60):
        cv2.line(f, (x - cam_dx, 40), (x - cam_dx + 30, 330), (235, 235, 235), 2)
        cv2.circle(f, (x - cam_dx + 15, 120 + (x % 7) * 20), 3, (200, 200, 200), -1)
    pts = np.array([[hx - 18, hy], [hx - 9, hy - 7], [hx + 9, hy - 7], [hx + 18, hy], [hx + 9, hy + 7], [hx - 9, hy + 7]], np.int32)
    cv2.fillPoly(f, [pts], (20, 20, 20))                              # dark see-through fill
    cv2.polylines(f, [pts], True, (170, 255, 60), 2)                  # neon outline
    cv2.rectangle(f, (hx - 7, hy - 40), (hx + 7, hy - 2), (30, 30, 160), -1)   # the player's body
    return f


def test_marker_found_and_badges_rejected():
    cv2 = pytest.importorskip("cv2")
    from qortime_ai.stickecho import video as V

    f = draw_frame(cv2, 300, 220)
    cv2.circle(f, (500, 100), 9, (170, 255, 60), -1)                  # filled round badge: not a marker
    tr = V.track_marker([V.candidates(f)])
    assert tr[0] is not None and abs(tr[0][0] - 300) <= 12 and abs(tr[0][1] - 220) <= 8
    b = V.seed_box(f, tr[0])
    assert b is not None and b[0] <= 300 <= b[2] and b[3] >= 210


def test_camera_compensated_motion():
    cv2 = pytest.importorskip("cv2")
    from qortime_ai.stickecho import video as V

    fr = [draw_frame(cv2, 200 + 3 * k, 220, cam_dx=2 * k) for k in range(12)]
    t = V.window_track(fr, None, 0.0, "defender")
    vel = [v for v in t["marker_vel"] if v is not None]
    assert len(vel) >= 8
    vx = np.median([v[0] for v in vel])
    assert 3.5 <= vx <= 6.5                                           # 3 px on screen + 2 px of camera pan
    assert "sam_vel" not in t


def test_sam_boxes_with_injected_caller(tmp_path):
    cv2 = pytest.importorskip("cv2")
    pytest.importorskip("meta_sam_parser")
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from qortime_ai.stickecho import video as V

    vid = tmp_path / "synthetic.mp4"
    w = cv2.VideoWriter(str(vid), cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 360))
    for k in range(30):
        w.write(draw_frame(cv2, 200 + 2 * k, 220))
    w.release()
    calls = []

    def fake(prompt, data, forward=False):
        calls.append((prompt, len(data), forward))
        text = "".join(f"<{k}f>1<|box;x1={(290 + 3 * k)};y1=270;x2={(312 + 3 * k)};y2=330;w=960;h=540;c=0.9|>"
                       f"<|mask;x=0;y=0;c=0.9;data=2,2,!!|>\n" for k in range(30))
        return {"text": text, "usage": {"video_frames_processed": 30}}

    boxes, info = V.sam_boxes(vid, 0.0, 1.0, [(0, (190, 180, 210, 222))], cache=tmp_path / "cache", caller=fake)
    assert len(calls) == 1 and calls[0][2] is True and "box" in calls[0][0].lower()
    assert boxes[0] is not None and abs(boxes[0][0] - 290 / 1.5) < 1e-6 and abs(boxes[0][3] - 331 / 1.5) < 1e-6
    assert info["frames_sent"] == 30 and info["cached"] is False
    boxes2, info2 = V.sam_boxes(vid, 0.0, 1.0, [(0, (190, 180, 210, 222))], cache=tmp_path / "cache", caller=fake)
    assert info2["cached"] is True and len(calls) == 1 and boxes2 == boxes        # cached: never re-sent
