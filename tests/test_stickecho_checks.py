"""Stick Echo free local checks (menu screen, defensive Circle switch): drop-only. SYNTHETIC data only."""
from __future__ import annotations

import json

import numpy as np
import pytest

from qortime_ai.stickecho import checks as CK
from qortime_ai.stickecho.__main__ import TRACKS_SCHEMA, main
from qortime_ai.stickecho.log import StickLog
from qortime_ai.stickecho import sidecar as S

VSU, LAG = 2_000_000, 1.4


def test_menu_rule_and_padding():
    n = 40
    screen = [[600, 20]] * n
    screen[20] = [400, 700]                  # dark play-call panel in the lower band
    bad = CK.menu_drop(screen, n)
    assert bad[15:26].all() and not bad[:15].any() and not bad[26:].any()
    screen2 = [[100, 0]] * 3 + [[600, 20]] * 20   # almost no turf above the scorebug: full-screen menu
    assert CK.menu_drop(screen2, 23)[:8].all() and not CK.menu_drop(screen2, 23)[8:].any()
    assert not CK.menu_drop(None, 10).any()      # old tracks without screen stats: nothing dropped


def test_screen_stats_synthetic_frames():
    cv2 = pytest.importorskip("cv2")
    field = np.zeros((360, 640, 3), np.uint8)
    field[:] = cv2.cvtColor(np.uint8([[[60, 150, 120]]]), cv2.COLOR_HSV2BGR)[0, 0]
    turf, dark = CK.screen_stats(field)
    assert turf > 900 and dark == 0
    menu = field.copy()
    menu[170:300, :] = (10, 10, 10)          # dark panel over the lower half
    t2, d2 = CK.screen_stats(menu)
    assert d2 > CK.MENU_DARK_SHARE * 1000 and CK.menu_drop([[t2, d2]], 1)[0]


def win(context, n=90, start=10.0, on_halo_from=None):
    mk = [[100.0, 200.0, 30.0]] * n
    feet = [[100.0, 200.0]] * n
    if on_halo_from is not None:
        feet = [[300.0, 200.0] if k < on_halo_from else [100.0, 200.0] for k in range(n)]
    return {"start_s": start, "context": context, "frames": n, "marker": mk, "sam_feet": feet}


def press_at(frame, start=10.0):
    """Input-clock time of a press that shows on screen at ``frame`` of a window starting at ``start``."""
    return int(VSU + (start + frame / 30.0 - LAG) * 1e6)


def test_circle_on_defense_drops_and_reanchors_to_halo():
    w = win("defender", on_halo_from=50)
    bad, info = CK.switch_drop(w, [press_at(30)], video_start_us=VSU, lag_s=LAG)
    assert bad[27:41].all() and not bad[:27].any()
    assert bad[41:50].all()                  # SAM off the halo after the switch: still dropped (re-anchor)
    assert not bad[50:].any()                # back on the halo for 3 frames in a row: kept
    assert info == {"presses": 1, "without_marker_jump": 1}   # no marker jump: diagnostic only


def test_circle_on_offense_is_never_a_switch():
    """Con: on offense Circle is a receiver icon (a throw to the Circle receiver), never a player switch."""
    for ctx in ("pass+ball_carrier", "ball_carrier (kick return)", "returner", "qb_pocket"):
        bad, info = CK.switch_drop(win(ctx), [press_at(30)], video_start_us=VSU, lag_s=LAG)
        assert not bad.any() and info["presses"] == 0


def test_marker_jump_counts_as_matched_switch():
    w = win("defender")
    w["marker"] = [[100.0, 200.0, 30.0]] * 32 + [[400.0, 220.0, 30.0]] * 58
    w["sam_feet"] = [[400.0, 220.0]] * 90
    _, info = CK.switch_drop(w, [press_at(30)], video_start_us=VSU, lag_s=LAG)
    assert info == {"presses": 1, "without_marker_jump": 0}


def test_apply_only_ever_drops():
    w = win("defender", on_halo_from=50)
    w["screen"] = [[600, 20]] * 90
    w["screen"][80] = [600, 800]
    V = {k: np.array([1.0, 0.0]) for k in range(0, 90, 2)}
    kept, c = CK.apply(w, V, ("menu", "switch"), circle_t_us=[press_at(30)], video_start_us=VSU, lag_s=LAG)
    assert set(kept) <= set(V) and len(kept) < len(V)
    assert c["menu_dropped"] > 0 and c["switch_dropped"] > 0 and c["circle_presses_on_defense"] == 1
    with pytest.raises(ValueError):
        CK.apply(w, V, ("box",))


def test_press_times_rising_edges():
    recs = [{"type": "in", "t_us": t, "b": b, "lx": 128, "ly": 128}
            for t, b in [(0, 0), (10, 2), (20, 2), (30, 0), (40, 3), (50, 1), (60, 2)]]
    lg = StickLog(recs)
    assert list(lg.press_times(CK.CIRCLE_BIT)) == [10, 40, 60]
    assert list(lg.press_times(1)) == [40]


def synth(seed, dur_s=200.0, step=5000, circle_at=()):
    rng = np.random.default_rng(seed)
    n = int(dur_s * 1e6 / step)
    ang = np.repeat(rng.uniform(-np.pi, np.pi, n // 150 + 1), 150)[:n]
    out = [{"type": "header", "schema": "qorcap-inputs/v0", "t_us": 0}]
    for i in range(n):
        t = i * step
        b = 2 if any(c <= t < c + 60_000 for c in circle_at) else 0
        out.append({"type": "in", "t_us": t, "b": b, "lx": int(127.5 + 120 * np.cos(ang[i])), "ly": int(127.5 + 120 * np.sin(ang[i]))})
    return out


def test_cli_checks_reach_sidecar_as_totals(tmp_path):
    press = press_at(30, start=40.0)
    recs = synth(1, circle_at=[press])
    lg = StickLog(recs)
    (tmp_path / "in.jsonl").write_text("\n".join(json.dumps(r) for r in recs))
    (tmp_path / "o.jsonl").write_text("\n".join(json.dumps(r) for r in synth(2)))
    wins = []
    for i, (start, ctx) in enumerate(((40.0, "defender"), (90.0, "pass+ball_carrier"), (140.0, "defender"))):
        t = VSU + ((start + np.arange(150) / 30.0) - LAG) * 1e6
        s = lg.stick_at(t.astype(np.int64))
        v = (2 * s / np.maximum(np.linalg.norm(s, axis=1, keepdims=True), 1e-9)).tolist()
        screen = [[600, 20]] * 150
        if i == 1:
            screen[100] = [600, 850]
        wins.append({"start_s": start, "context": ctx, "score_from": 0, "frames": 150, "sam_vel": v, "marker_vel": v,
                     "sam_feet": [[100.0, 200.0]] * 150, "marker": [[100.0, 200.0, 30.0]] * 150, "screen": screen})
    tr = tmp_path / "tracks.json"
    tr.write_text(json.dumps({"schema": TRACKS_SCHEMA, "fps": 30.0, "video_start_us": VSU, "tracker": "sam-3.1",
                              "windows": wins, "cost": {"sam_frames": 0, "usd_est_micro": 0}}))
    out = tmp_path / "sc.json"
    assert main(["score", str(tr), str(tmp_path / "in.jsonl"), "--null-log", str(tmp_path / "o.jsonl"),
                 "--lag-ms", "1400", "--checks", "menu,switch", "--out", str(out)]) == 0
    doc = json.loads(out.read_text())
    fc = doc["totals"]["free_checks"]
    assert fc["menu_frames_dropped"] == 11 and fc["switch_frames_dropped"] == 14
    assert fc["circle_presses_on_defense"] == 1 and fc["circle_presses_without_marker_jump"] == 1
    assert doc["method"]["checks"] == ["menu", "switch"] and doc["method"]["preregistered"] is False
    assert S.check(doc) == [] and "checks" not in doc["totals"]["frames_selected_by_source"]
    assert "exploratory" in doc["summary"]
    with pytest.raises(SystemExit):
        main(["score", str(tr), str(tmp_path / "in.jsonl"), "--null-log", str(tmp_path / "o.jsonl"),
              "--lag-ms", "1400", "--checks", "box", "--out", str(out)])
