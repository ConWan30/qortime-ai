"""``echo.sidecar.json`` (schema qortime.echo.v0): build, check, lower-only apply. receipt.v0.json is not touched.

Integers only (no floats), so the file can later be JCS-signed like the other advisory sidecars.
Nothing per frame and no raw controller timeline: per press only its button, whether it was echoed, and its latency.
"""
from __future__ import annotations

import copy
from typing import Any

from qortime_ai.echo import match as M

SCHEMA = "qortime.echo.v0"
PARTIAL = "PARTIAL"
CAP_CODE = "challenge_echo_mismatch"
BUILT = "Meta AI Developer Hackathon, Oct 26 - Nov 4 2026 (built Oct 27 2026)"
LABEL = ("INFO-ONLY, LOWER-ONLY. Challenge Echo checks that the video's pause-menu highlight follows the logged D-pad "
         "presses. It never raises a status; a mismatch can only suggest lowering VERIFIED to PARTIAL. AI explains, it "
         "never decides; the referee's own challenge check is unchanged.")
SAM_ROLE = ("Meta SAM 3.1 tracks the pause-menu highlight box (box prompt on the first menu frame, forward "
            "propagation). Menu detection, press edges and the matching are deterministic code.")


def decide_cap(clips: list[dict[str, Any]]) -> str | None:
    return PARTIAL if any(c.get("status") == "mismatch" for c in clips) else None


def build(clips: list[dict[str, Any]], *, pattern: list[str], clock: dict[str, Any],
          receipt_jcs_sha256: str | None = None, cost: dict[str, Any] | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema": SCHEMA, "label": LABEL, "built_during": BUILT, "affects_verdict": "lower_only",
        "max_cap": PARTIAL, "emits_status": False, "receipt_jcs_sha256": receipt_jcs_sha256,
        "pattern": [p for p in pattern if p != "OPTIONS"], "clock": clock, "sam_role": SAM_ROLE,
        "menu_model": "vertical list: DOWN/UP move the highlight one row (with wrap); LEFT/RIGHT are no-ops "
                      "(checked as 'highlight held still', marked visible=false)",
        "relay_gap_band_ms": [int(M.RELAY_GAP_BAND_S[0] * 1000), int(M.RELAY_GAP_BAND_S[1] * 1000)],
        "tolerances_ms": {"press_to_move": M.TOL_MS, "latency_bound": [M.LAT_MIN_MS, M.LAT_MAX_MS],
                          "menu_vs_dpad": list(M.MENU_VS_DPAD_MS)},
        "not_published": "frames, crops, per-frame boxes, raw controller timeline",
        "clips": clips, "cap": decide_cap(clips)}
    if cost is not None:
        doc["cost"] = cost
    n = {s: sum(1 for c in clips if c.get("status") == s) for s in M.STATUSES}
    doc["summary"] = (f"{n['consistent']} consistent, {n['partial']} partial, {n['mismatch']} mismatch, "
                      f"{n['unscorable']} unscorable of {len(clips)} challenge window(s).")
    return doc


def check(doc: Any) -> list[str]:
    """Problems with an echo sidecar. Empty = it may be shown / applied (lower-only)."""
    if not isinstance(doc, dict):
        return ["not_an_object"]
    p = []
    if doc.get("schema") != SCHEMA:
        p.append("bad_schema")
    if doc.get("affects_verdict") != "lower_only" or doc.get("max_cap") != PARTIAL or doc.get("emits_status") is not False:
        p.append("not_lower_only")
    if doc.get("cap") not in (None, PARTIAL):
        p.append("bad_cap")
    clips = doc.get("clips") if isinstance(doc.get("clips"), list) else []
    if doc.get("cap") != decide_cap(clips):
        p.append("cap_inconsistent")
    return p


def apply_cap(status: str, cap: str | None) -> str:
    if cap is None:
        return status
    if cap != PARTIAL:
        raise ValueError("echo cap must be PARTIAL or None")
    return PARTIAL if status == "VERIFIED" else status


def apply_to_result(v: dict[str, Any], doc: Any) -> dict[str, Any]:
    """Copy of a verifier result with Echo applied: VERIFIED -> PARTIAL on a mismatch, otherwise a note only."""
    out = copy.deepcopy(v)
    if check(doc):
        return out
    out.setdefault("notes", []).append("challenge_echo: " + doc["summary"])
    new = apply_cap(out["status"], doc["cap"])
    if new != out["status"]:
        out["status"] = new
        out.setdefault("partial", []).append(CAP_CODE)
    return out
