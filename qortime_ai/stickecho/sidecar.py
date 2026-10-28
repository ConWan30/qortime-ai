"""``stickecho.sidecar.json`` (schema qortime.stickecho.v0): build, check, lower-only apply. receipt.v0.json is not touched.

Integers only (no floats), so the file can later be JCS-signed like the other advisory sidecars. Totals only:
nothing per frame, per window or per player, and no raw controller timeline.

Result, decided by fixed rules (never by a model):
* ``unscorable``   fewer than ``MIN_FRAMES`` scored frames, or a null source had no usable null windows -> note only
* ``agree``        z >= 3 against every null source: "controller and video agree" -> note only (never an upgrade)
* ``inconclusive`` anything in between -> note only
* ``disagree``     enough frames and z < 1 against every null source -> may suggest VERIFIED -> PARTIAL, nothing else
"""
from __future__ import annotations

import copy
from typing import Any

SCHEMA = "qortime.stickecho.v0"
PARTIAL = "PARTIAL"
CAP_CODE = "stick_echo_disagree"
RESULTS = ("agree", "inconclusive", "disagree", "unscorable")
MIN_FRAMES = 300
AGREE_Z = 3.0
DISAGREE_Z = 1.0
BUILT = "Meta AI Developer Hackathon, Oct 26 - Nov 4 2026 (built Oct 28 2026)"
LABEL = ("INFO-ONLY, LOWER-ONLY. Stick Echo checks that the on-screen movement of the player being controlled follows "
         "the logged left stick. It never raises a status and never makes the call; a clear disagreement can only "
         "suggest lowering VERIFIED to PARTIAL. It does not show who held the controller.")
SAM_ROLE = ("Meta SAM 3.1 tracks the controlled player (box prompt seeded on the game's controlled-player marker, "
            "forward propagation). Marker detection, camera compensation, frame selection, the lag and the scoring "
            "are deterministic code.")


def _i(x: float | None, scale: int) -> int | None:
    return None if x is None else int(round(x * scale))


def decide(ev: dict[str, Any], n_nulls: int) -> str:
    zs = [v["z"] for v in ev.get("nulls", {}).values() if v and v.get("z") is not None]
    if ev.get("frames", 0) < MIN_FRAMES or len(zs) != n_nulls or not zs:
        return "unscorable"
    if min(zs) >= AGREE_Z:
        return "agree"
    if max(zs) < DISAGREE_Z:
        return "disagree"
    return "inconclusive"


def decide_cap(result: str) -> str | None:
    return PARTIAL if result == "disagree" else None


def build(ev: dict[str, Any], *, method: dict[str, Any], sources: dict[str, int], clock: dict[str, Any],
          receipt_jcs_sha256: str | None = None, diagnostics: dict[str, Any] | None = None,
          cost: dict[str, Any] | None = None) -> dict[str, Any]:
    nulls = [{"source": k, "mean_permille": _i(v["mean"], 1000), "sd_permille": _i(v["sd"], 1000),
              "z_centi": _i(v["z"], 100), "draws_ge_true_permille": _i(v["share_ge"], 1000)} if v else
             {"source": k, "error": "too_few_null_windows"} for k, v in ev["nulls"].items()]
    result = decide(ev, len(ev["nulls"]))
    doc: dict[str, Any] = {
        "schema": SCHEMA, "label": LABEL, "built_during": BUILT, "affects_verdict": "lower_only", "max_cap": PARTIAL,
        "emits_status": False, "receipt_jcs_sha256": receipt_jcs_sha256, "sam_role": SAM_ROLE, "method": method,
        "clock": clock,
        "rules": {"min_frames": MIN_FRAMES, "agree_z_centi": int(AGREE_Z * 100), "disagree_z_centi": int(DISAGREE_Z * 100),
                  "min_speed_milli_px_per_frame": 600, "min_stick_permille": 350, "null_draws": 5000},
        "not_published": "frames, crops, per-frame boxes and velocities, per-window values, raw controller timeline",
        "totals": {"windows": ev["windows"], "frames_scored": ev["frames"],
                   "mean_cos_permille": _i(ev["mean_cos"], 1000), "within_45_deg_permille": _i(ev["within_45"], 1000),
                   "frames_selected_by_source": {k: int(v) for k, v in sources.items() if k != "checks"}},
        "nulls": nulls, "min_z_centi": _i(ev.get("min_z"), 100), "result": result, "cap": decide_cap(result)}
    if sources.get("checks") is not None:
        c = sources["checks"]
        doc["totals"]["free_checks"] = {
            "rule": "drop-only: frames removed before scoring; never adds frames or raises a result",
            "menu_frames_dropped": int(c.get("menu_dropped", 0)), "switch_frames_dropped": int(c.get("switch_dropped", 0)),
            "circle_presses_on_defense": int(c.get("circle_presses_on_defense", 0)),
            "circle_presses_without_marker_jump": int(c.get("circle_without_marker_jump", 0))}
    if diagnostics:
        doc["diagnostics"] = diagnostics
    if cost is not None:
        doc["cost"] = cost
    words = {"agree": "controller and video agree", "inconclusive": "inconclusive",
             "disagree": "controller and video disagree", "unscorable": "not scorable"}
    doc["summary"] = (f"{words[result]}: {ev['frames']} frames in {ev['windows']} window(s), mean cosine "
                      f"{doc['totals']['mean_cos_permille']}/1000, min z "
                      f"{'n/a' if doc['min_z_centi'] is None else format(doc['min_z_centi'] / 100, '.2f')} over "
                      f"{len(nulls)} null source(s); method {method.get('selection')}"
                      f"{'' if method.get('preregistered') else ' (exploratory)'}.")
    return doc


def _ints_only(x: Any) -> bool:
    if isinstance(x, float):
        return False
    if isinstance(x, dict):
        return all(_ints_only(v) for v in x.values())
    if isinstance(x, list):
        return all(_ints_only(v) for v in x)
    return True


def check(doc: Any) -> list[str]:
    """Problems with a Stick Echo sidecar. Empty = it may be shown / applied (lower-only)."""
    if not isinstance(doc, dict):
        return ["not_an_object"]
    p = []
    if doc.get("schema") != SCHEMA:
        p.append("bad_schema")
    if doc.get("affects_verdict") != "lower_only" or doc.get("max_cap") != PARTIAL or doc.get("emits_status") is not False:
        p.append("not_lower_only")
    if doc.get("result") not in RESULTS:
        p.append("bad_result")
    if doc.get("cap") not in (None, PARTIAL):
        p.append("bad_cap")
    if doc.get("cap") != decide_cap(doc.get("result")):
        p.append("cap_inconsistent")
    if not _ints_only(doc):
        p.append("float_values")
    return p


def apply_cap(status: str, cap: str | None) -> str:
    if cap is None:
        return status
    if cap != PARTIAL:
        raise ValueError("stick echo cap must be PARTIAL or None")
    return PARTIAL if status == "VERIFIED" else status


def apply_to_result(v: dict[str, Any], doc: Any) -> dict[str, Any]:
    """Copy of a verifier result with Stick Echo applied: VERIFIED -> PARTIAL on ``disagree``, otherwise a note only."""
    out = copy.deepcopy(v)
    if check(doc):
        return out
    out.setdefault("notes", []).append("stick_echo: " + doc["summary"])
    new = apply_cap(out["status"], doc["cap"])
    if new != out["status"]:
        out["status"] = new
        out.setdefault("partial", []).append(CAP_CODE)
    return out
