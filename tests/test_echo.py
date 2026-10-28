"""Challenge Echo (built Oct 27 2026, Meta AI Developer Hackathon). SYNTHETIC fixtures only: no real footage,
no real controller input. The synthetic video is drawn here (grey 'gameplay', then a dark menu with a white box)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from qortime_ai.echo import match as M
from qortime_ai.echo import sidecar as S
from qortime_ai.echo.presses import CROSS, DOWN, LEFT, OPTIONS, RIGHT, UP, press_events

ROOT = Path(__file__).resolve().parents[1]
PAT = ["LEFT", "DOWN", "RIGHT", "UP"]
STATUSES = ["VERIFIED", "PARTIAL", "SELF" + "_ATTESTED", "FAIL"]   # pre-existing verifier statuses


def recs(events, start_us=1_000_000, hold_us=60_000, rate_us=4_000, until_us=None):
    """SYNTHETIC full-rate inputs (with releases): events = [(t_us, mask)]."""
    end = until_us or max(t for t, _ in events) + 500_000
    out = []
    for t in range(start_us, end, rate_us):
        b = 0
        for et, m in events:
            if et <= t < et + hold_us:
                b |= m
        out.append({"type": "in", "t_us": t, "b": b})
    return out


def presses(lag=1.2, order=("LEFT", "DOWN", "RIGHT", "UP"), t0=2.0, gap=0.35):
    pr = [{"t": t0, "button": "OPTIONS"}]
    t = t0 + 1.5
    for b in order:
        pr.append({"t": round(t, 3), "button": b})
        t += gap
    pr.append({"t": round(t + 0.5, 3), "button": "CROSS"})
    return pr


def moves_for(pr, lag=1.2, jitter=(0.0,), skip=(), extra=()):
    out = []
    k = 0
    for i, p in enumerate(pr):
        if p["button"] in M.MOVING and i not in skip:
            out.append(M.Move(round(p["t"] + lag + jitter[k % len(jitter)], 4), p["button"]))
            k += 1
    return sorted(out + list(extra), key=lambda m: m.t)


def menu_at(pr, after=1.55):
    return {"present": True, "onset_s": pr[0]["t"] + after, "end_s": pr[-1]["t"] + 2.0}


# ---- presses ----------------------------------------------------------------------------------------------------
def test_press_edges_full_inputs():
    ev = press_events(recs([(1_100_000, OPTIONS), (1_500_000, DOWN), (1_900_000, DOWN), (2_300_000, UP | CROSS)]))
    assert [e["button"] for e in ev] == ["OPTIONS", "DOWN", "DOWN", "CROSS", "UP"]
    assert ev[1]["t_us"] == 1_500_000


def test_release_gap_rule_for_nonzero_only_extracts():
    rows = [{"t_us": t, "b": DOWN} for t in (0, 4_000, 8_000, 300_000, 304_000)]
    assert len(press_events(rows)) == 1                                   # no release rows: one edge
    assert len(press_events(rows, release_gap_us=120_000)) == 2           # gap > 120 ms = released


# ---- track -> moves ---------------------------------------------------------------------------------------------
def test_moves_down_up_wrap_merge_and_gaps():
    tr = [(0.0, 70), (0.1, 70), (0.2, None), (0.3, 100), (0.317, 108), (0.6, 108), (0.9, 70), (1.2, 272), (1.5, 70)]
    mv = M.moves_from_track(tr, 720)
    assert [(m.direction, m.wrap) for m in mv] == [("DOWN", False), ("UP", False), ("UP", True), ("DOWN", True)]
    assert mv[0].t == 0.3                                                  # box growing 100->108 is the same move


# ---- wrap test from the menu's measured row pitch -----------------------------------------------------------------
PITCH = 28.5                                  # SYNTHETIC geometry: 720p frame, menu rows 28.5 px apart


def _rows(n, top=72.0, pitch=PITCH):
    return [top + k * pitch for k in range(n)]


def test_seven_row_menu_steps_and_wraps():
    r = _rows(7)
    tr = [(0.0, r[0]), (0.3, r[1]), (0.6, r[2]), (0.9, r[1]), (1.2, r[0]), (1.5, r[6] + 2), (1.8, r[0])]
    mv = M.moves_from_track(tr, 720, row_pitch=PITCH)
    assert [(m.direction, m.wrap) for m in mv] == [("DOWN", False), ("DOWN", False), ("UP", False), ("UP", False),
                                                   ("UP", True), ("DOWN", True)]


@pytest.mark.parametrize("scale", [1.0, 0.5])            # 720p and a 360p capture of the same menu
def test_five_row_menu_wrap_is_a_wrap(scale):
    """Halftime-style 5-row list: the wrap jump is 4 pitches (114 px at 720p, 57 px at 360p), under the old fixed
    frame_h/6 rule, so that rule read it as a one-row move the other way. The pitch-based test calls it a wrap."""
    h, pitch = int(720 * scale), PITCH * scale
    r = _rows(5, top=72 * scale, pitch=pitch)
    tr = [(0.0, r[0]), (0.3, r[0]), (0.6, r[4]), (0.9, r[4]), (1.2, r[0])]
    mv = M.moves_from_track(tr, h, row_pitch=pitch)
    assert [(m.direction, m.wrap) for m in mv] == [("UP", True), ("DOWN", True)]
    old = M.moves_from_track(tr, h)                          # no measured pitch: fallback reproduces the old misread
    assert [(m.direction, m.wrap) for m in old] == [("DOWN", False), ("UP", False)]


@pytest.mark.parametrize("pitch", [10.0, 14.25, 28.5, 40.0, 60.0])
@pytest.mark.parametrize("step", [0.6, 0.9, 1.0, 1.1, 1.32])   # 1.32: a taller highlighted row (sub-line) grows the box
def test_single_row_move_is_never_a_wrap(pitch, step):
    for h in (360, 720, 1080, 2160):
        tr = [(0.0, 300.0), (0.3, 300.0 + step * pitch), (0.6, 300.0)]
        mv = M.moves_from_track(tr, h, row_pitch=pitch)
        assert not any(m.wrap for m in mv), (pitch, step, h)
        if step * pitch >= h / 90:                           # below the min-step floor no move is reported at all
            assert [(m.direction, m.wrap) for m in mv] == [("DOWN", False), ("UP", False)], (pitch, step, h)
    assert M.WRAP_PITCHES * pitch < 2 * pitch                # the shortest wrap (3-row list) is still a wrap


def test_wrap_threshold_basis_and_fallback():
    assert M.wrap_threshold(720, 28.5) == (pytest.approx(M.WRAP_PITCHES * 28.5), "row_pitch")
    assert M.wrap_threshold(720, None) == (pytest.approx(120.0), "frame_fraction_fallback")
    assert M.wrap_threshold(720, 0) == (pytest.approx(120.0), "frame_fraction_fallback")


def _menu_crop(n_rows, hl=0, pitch=PITCH, w=384, h=338, text=True):
    """SYNTHETIC grey menu crop: dark list, white highlight box on row ``hl``, dimmer text bars on the other rows."""
    g = np.full((h, w), 12, np.uint8)
    for k, c in enumerate(_rows(n_rows, top=72, pitch=pitch)):
        if k == hl:
            g[int(c - 19):int(c + 20), 49:343] = 255
        elif text:
            g[int(c - 7):int(c + 7), 57:57 + 60 + 9 * k] = 180
    return g


@pytest.mark.parametrize("n", [7, 5])
def test_row_pitch_measured_from_menu_frame(n):
    from qortime_ai.echo import video as V

    assert V.row_pitch(_menu_crop(n)) == pytest.approx(PITCH, abs=1.0)
    assert V.row_pitch(_menu_crop(n, hl=2)) == pytest.approx(PITCH, abs=1.0)   # gap across the box is skipped
    assert V.row_pitch(_menu_crop(n, text=False)) is None                     # nothing to measure -> fallback


# ---- scoring ----------------------------------------------------------------------------------------------------
def test_consistent_live_session():
    pr = presses()
    r = M.score_clip(pr, moves_for(pr, jitter=(0.0, 0.02)), menu_at(pr), PAT)
    assert r["status"] == "consistent" and r["directions_matched"] == 4 and r["presses_echoed"] == 4
    assert [x["visible"] for x in r["presses"]] == [False, True, False, True]
    assert r["latency_median_ms"] == 1210 and r["jitter_ms"] <= 20 and r["menu"]["appeared"] is True
    assert r["in_relay_gap_band"] is True and r["logged_order_matches_pattern"] is True


def test_order_differs_from_pattern_is_info_only():
    pr = presses(order=("DOWN", "LEFT", "RIGHT", "UP"))
    r = M.score_clip(pr, moves_for(pr), menu_at(pr), PAT)
    assert r["status"] == "consistent" and r["logged_order_matches_pattern"] is False


def test_missing_move_is_partial_and_extra_moves_mismatch():
    pr = presses()
    r = M.score_clip(pr, moves_for(pr, skip=(4,)), menu_at(pr), PAT)          # UP never shows on screen
    assert r["status"] == "partial" and r["presses_echoed"] == 3
    extra = (M.Move(pr[2]["t"] + 1.2 + 0.6, "UP"), M.Move(pr[3]["t"] + 1.2 + 0.2, "DOWN"))
    r = M.score_clip(pr, moves_for(pr, extra=extra), menu_at(pr), PAT)
    assert r["status"] == "mismatch" and r["unexplained_moves"] == 2


def test_noop_press_with_move_is_not_echoed():
    pr = presses()
    mv = moves_for(pr) + [M.Move(pr[1]["t"] + 1.2, "DOWN")]                   # highlight moved on LEFT
    r = M.score_clip(pr, sorted(mv, key=lambda m: m.t), menu_at(pr), PAT)
    assert r["presses"][0]["echoed"] is False and r["status"] != "consistent"


def test_video_not_following_inputs_is_mismatch():
    pr = presses()
    r = M.score_clip(pr, [M.Move(pr[2]["t"] + 1.2, "UP"), M.Move(pr[4]["t"] + 1.2, "DOWN")], menu_at(pr), PAT)
    assert r["status"] == "mismatch"
    r = M.score_clip(pr, [], menu_at(pr), PAT)
    assert r["status"] == "mismatch" and r["why"] == "no_highlight_move_after_any_press"


def test_relayed_video_with_drifting_gap_breaks_the_echo():
    pr = presses()                       # a relay gap that wanders 0.5 s between presses can't line up
    r = M.score_clip(pr, moves_for(pr, lag=1.2, jitter=(0.0, 0.5)), menu_at(pr), PAT)
    assert r["status"] != "consistent"


def test_menu_before_options_or_late_menu_is_mismatch():
    pr = presses()
    r = M.score_clip(pr, moves_for(pr), menu_at(pr, after=-0.4), PAT)
    assert r["status"] == "mismatch" and r["menu"]["appeared"] is False
    r = M.score_clip(pr, moves_for(pr), menu_at(pr, after=3.0), PAT)
    assert r["status"] == "mismatch"


def test_lag_out_of_bounds_does_not_line_up():
    pr = presses()
    r = M.score_clip(pr, moves_for(pr, lag=3.4), menu_at(pr, after=3.7), PAT)
    assert r["status"] == "mismatch" and r["lag_ms"] is None


def test_sloppy_entry_held_down_is_partial():
    pr = [{"t": 2.0, "button": "OPTIONS"}] + [{"t": 3.6 + 0.2 * i, "button": "DOWN"} for i in range(5)] + \
         [{"t": 5.0, "button": "CROSS"}]
    r = M.score_clip(pr, moves_for(pr), menu_at(pr), PAT)
    assert r["status"] == "partial" and r["directions_matched"] == 1 and r["presses_echoed"] == 5


@pytest.mark.parametrize("menu,why", [({"present": False}, "no_pause_menu_in_video")])
def test_unscorable(menu, why):
    pr = presses()
    assert M.score_clip(pr, moves_for(pr), menu, PAT)["why"] == why
    assert M.score_clip([p for p in pr if p["button"] != "OPTIONS"], [], menu_at(pr), PAT)["why"] == "no_options_press"
    only_lr = presses(order=("LEFT", "RIGHT"))
    assert M.score_clip(only_lr, [], menu_at(only_lr), PAT)["status"] == "unscorable"


# ---- sidecar: lower-only ----------------------------------------------------------------------------------------
def _doc(statuses):
    clips = [{"id": f"c{i}", "status": s} for i, s in enumerate(statuses)]
    return S.build(clips, pattern=PAT, clock={"video_start_source": "test"})


@pytest.mark.parametrize("st", ["consistent", "partial", "mismatch", "unscorable"])
@pytest.mark.parametrize("v", STATUSES)
def test_never_raises_and_caps_at_partial(st, v):
    out = S.apply_to_result({"status": v, "partial": []}, _doc([st]))
    order = {s: i for i, s in enumerate(STATUSES)}
    assert order[out["status"]] >= order[v]                               # never better than the verifier said
    assert out["status"] == ("PARTIAL" if (st == "mismatch" and v == "VERIFIED") else v)
    assert any(n.startswith("challenge_echo") for n in out["notes"])


def test_tampered_sidecar_is_ignored():
    d = _doc(["consistent"])
    assert S.check(d) == []
    for k, val in (("affects_verdict", "raise"), ("cap", "VERIFIED"), ("emits_status", True), ("max_cap", "FAIL")):
        bad = json.loads(json.dumps(d))
        bad[k] = val
        assert S.check(bad) and S.apply_to_result({"status": "PARTIAL"}, bad)["status"] == "PARTIAL"
    bad = json.loads(json.dumps(d))
    bad["cap"] = "PARTIAL"                                                # a cap with no mismatch behind it
    assert "cap_inconsistent" in S.check(bad)
    assert S.apply_to_result({"status": "VERIFIED"}, bad)["status"] == "VERIFIED"


def test_sidecar_is_integers_only_and_has_no_raw_timeline():
    pr = presses()
    clip = {"id": "c0", **M.score_clip(pr, moves_for(pr, jitter=(0.0, 0.013)), menu_at(pr), PAT)}
    doc = S.build([clip], pattern=PAT, clock={"video_start_source": "test"})
    def walk(x):
        if isinstance(x, float):
            raise AssertionError(f"float in sidecar: {x}")
        for v in (x.values() if isinstance(x, dict) else x if isinstance(x, list) else ()):
            walk(v)
    walk(doc)
    assert "t_us" not in json.dumps(doc) and '"t"' not in json.dumps(doc)


def test_wording_rules():
    from qortime_ai.redteam.wording import banned_hits

    for p in (ROOT / "qortime_ai" / "echo").glob("*.py"):
        assert not banned_hits(p.read_text()), p
    readme = (ROOT / "README.md").read_text()
    sec = readme[readme.index("## Challenge Echo"):readme.index("## Red-Team the Referee")]
    assert not banned_hits(sec) and "Built Oct 27 2026" in sec
    pub = ROOT / "examples" / "practice-echo" / "echo.sidecar.json"
    assert not banned_hits(pub.read_text()) and "t_us" not in pub.read_text()
    assert S.check(json.loads(pub.read_text())) == []
    assert not banned_hits(json.dumps(_doc(["mismatch"])))


# ---- synthetic video end to end (deterministic tracker; SAM failure falls back) ----------------------------------
ROWS = [70, 100, 130, 160, 190, 220, 250]


def _write_video(path: Path, fps=60, w=640, h=360, menu_on=3.0, menu_off=7.0, moves=((4.2, 1), (4.9, 0))):
    cv2 = pytest.importorskip("cv2")
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    s = h / 720
    for i in range(int(8.0 * fps)):
        t = i / fps
        if menu_on <= t < menu_off:
            f = np.full((h, w, 3), 10, np.uint8)
            row = 0
            for mt, r in moves:
                if t >= mt:
                    row = r
            y = int(ROWS[row] * s)
            cv2.rectangle(f, (int(50 * s), y - int(14 * s)), (int(340 * s), y + int(14 * s)), (255, 255, 255), -1)
        else:
            f = np.full((h, w, 3), 90 + (i % 7), np.uint8)
        vw.write(f)
    vw.release()
    return path


def test_observe_synthetic_video_fallback(tmp_path):
    from qortime_ai.echo import video as V

    p = _write_video(tmp_path / "synthetic.mp4")
    obs = V.observe(p, 1.5, 7.5, use_sam=False)
    assert obs.menu["present"] and abs(obs.menu["onset_s"] - 3.0) < 0.05 and obs.tracker == "deterministic_fallback"
    mv = M.moves_from_track(obs.track, obs.size[1])
    assert [m.direction for m in mv] == ["DOWN", "UP"] and abs(mv[0].t - 4.2) < 0.05


def test_sam_failure_falls_back(tmp_path):
    from qortime_ai.echo import video as V
    from qortime_ai.seen.sam_video import SamVideoError

    def boom(*a, **k):
        raise SamVideoError("api_key_missing")

    if not __import__("shutil").which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    p = _write_video(tmp_path / "synthetic.mp4")
    obs = V.observe(p, 1.5, 7.5, use_sam=True, caller=boom)
    assert obs.tracker == "deterministic_fallback" and obs.sam["error"] == "api_key_missing"


def test_cli_end_to_end_synthetic(tmp_path):
    from qortime_ai.echo.__main__ import main

    vid = _write_video(tmp_path / "synthetic.mp4", moves=((4.2, 1), (4.9, 0)))
    start = 10_000_000                                    # input-clock time of video frame 0
    lag = 1_200_000
    ev = [(start + 1_800_000, OPTIONS), (start + 2_700_000, LEFT), (start + 3_000_000 - 0, DOWN & 0),
          (start + 4_200_000 - lag, DOWN), (start + 3_350_000, RIGHT), (start + 4_900_000 - lag, UP),
          (start + 4_300_000, CROSS)]
    ev = [e for e in ev if e[1]]
    inp = tmp_path / "inputs.jsonl"
    inp.write_text("\n".join(json.dumps(r) for r in recs(ev, start_us=start, until_us=start + 7_500_000)))
    out = tmp_path / "echo.sidecar.json"
    assert main([str(vid), str(inp), "--video-start-us", str(start), "--no-sam", "--out", str(out),
                 "--pattern", "LEFT,DOWN,RIGHT,UP"]) == 0
    doc = json.loads(out.read_text())
    c = doc["clips"][0]
    assert S.check(doc) == [] and doc["cap"] is None and c["status"] == "consistent", c
    assert c["directions_matched"] == 4 and abs(c["latency_median_ms"] - 1200) <= 40


def test_observe_five_row_menu_wrap_end_to_end(tmp_path):
    """SYNTHETIC 360p video of a 5-row menu with text rows: UP on the first row wraps to the last. The pitch is
    measured from the drawn rows and the deterministic track reads the jump as an UP wrap, not a DOWN step."""
    cv2 = pytest.importorskip("cv2")
    from qortime_ai.echo import video as V

    fps, w, h, pitch, top = 30, 640, 360, 14.25, 36.0
    rows = [top + k * pitch for k in range(5)]
    path = tmp_path / "five_rows.mp4"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(int(6.0 * fps)):
        t = i / fps
        if 1.0 <= t < 5.0:
            f = np.full((h, w, 3), 10, np.uint8)
            hl = 4 if t >= 3.0 else 0
            for k, c in enumerate(rows):
                if k == hl:
                    cv2.rectangle(f, (25, int(c - 10)), (171, int(c + 10)), (255, 255, 255), -1)
                else:
                    cv2.rectangle(f, (29, int(c - 3)), (29 + 30 + 5 * k, int(c + 3)), (180, 180, 180), -1)
        else:
            f = np.full((h, w, 3), 90 + (i % 7), np.uint8)
        vw.write(f)
    vw.release()
    obs = V.observe(path, 0.5, 5.5, use_sam=False)
    assert obs.row_pitch == pytest.approx(pitch, abs=1.5)
    mv = M.moves_from_track(obs.track, obs.size[1], row_pitch=obs.row_pitch)
    assert [(m.direction, m.wrap) for m in mv] == [("UP", True)] and abs(mv[0].t - 3.0) < 0.05
