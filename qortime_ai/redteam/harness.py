"""Apply each attack to a synthetic receipt signed by fresh TEST keys and run the real, unmodified verifier.

Safety: TEST keys are generated in memory per run (never a real key, never the live referee, never held-out match
data). The baseline is the pre-existing qor_receipt synthetic match, played through its real referee service in-process.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from qor_receipt.jcs import canonicalize
from qor_receipt.keys import SoftwareKey, kid
from qor_receipt.receipt import verify_receipt

from qor_receipt.receipt import sign_player, sign_referee

from qortime_ai.redteam.mutations import PINS, MutationError, apply_ops, resign
from qortime_ai.redteam.wording import safe_text

FIXTURES = Path(__file__).with_name("fixtures")
ATTACKS_PATH = FIXTURES / "wonder_attacks.json"


def load_attacks(path: str | Path | None = None) -> dict[str, Any]:
    return json.loads(Path(path or ATTACKS_PATH).read_text(encoding="utf-8"))


class Sandbox:
    """Fresh TEST referee + TEST allowlist (temp file) + an honest receipt and an honest donor (another match)."""

    def __init__(self) -> None:
        from fastapi.testclient import TestClient
        from qor_receipt.demo import FakeClock, run_match
        from qor_receipt.referee.app import create_app

        self.referee = SoftwareKey()          # TEST key, in memory only
        self.attacker = SoftwareKey()
        self.attacker_players: dict[str, SoftwareKey] = {}
        clock = FakeClock()
        client = TestClient(create_app(self.referee, clock))
        self.receipt, k1 = run_match(client, clock, "dual")
        clock.t += 3_600_000
        self.donor, k2 = run_match(client, clock, "dual")
        # Honest TEST player keys by pubkey (used only by the insider pass).
        self.player_keys = {k.pubkey_hex: k for k in [*k1.values(), *k2.values()]}
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"schema": "qortime-trusted-referees/v1", "referees": [
            {"id": "redteam-TEST-referee", "pubkey": self.referee.pubkey_hex, "key_id": kid(self.referee.pubkey_hex),
             "status": "active", "label": "TEST key generated for this run"}]}, self._tmp)
        self._tmp.close()
        self.allowlist = self._tmp.name

    def verify(self, r: dict, pin: str = "honest") -> dict[str, Any]:
        pub = {"honest": self.referee.pubkey_hex, "attacker": self.attacker.pubkey_hex, "none": None}[pin]
        return verify_receipt(r, referee_pub=pub, allowlist_path=self.allowlist)

    def close(self) -> None:
        Path(self.allowlist).unlink(missing_ok=True)


def _honest_bytes(sb: Sandbox) -> set[bytes]:
    return {canonicalize(sb.receipt), canonicalize(sb.donor)}


INSIDER_ACCEPTED_LABEL = "needs key protection (out of scope for the verifier)"


# Code-written notes on insider forgeries the verifier accepts (reviewed by hand on Oct 27 2026). These are reported,
# not fixed here: the upstream verifier is pre-existing and is not modified by this repo.
INSIDER_NOTES = {
    "final_time_after_end": "inner-check gap: result.final_t_ms is not required to fall inside match.started_ms..ended_ms",
    "result_splice_donor": "inner-check gap: donor result.final_t_ms lies outside this match's window and is not rejected",
    "challenge_latency_edit": "inner-check gap: challenge result.hid_sha256 is only format-checked (the receipt carries no HID bytes, by design) and latency_ms 0 is in range",
    "referee_key_kind_upgrade": "inner-check gap: referee.key_kind is free text; only 'tpm' is flagged as an unverified claim",
    "duplicate_role_and_pubkey_swap": "inner-check gap: player pubkeys are not bound to their checkpoint chains (only the referee countersignature is checked), so two players' keys can be swapped",
    "reorder_challenges": "benign: same challenges in a different list order",
}
DEFAULT_INSIDER_NOTE = "key holder can sign any content: expected"


def insider_sign(sb: Sandbox, r: dict) -> dict:
    """Insider who holds the TEST signing keys: re-sign the receipt envelope (every player whose pubkey is an honest
    TEST key, then the referee). Per-checkpoint countersignatures and challenge tokens are NOT re-forged, so the
    inner checks run on their own."""
    import copy

    r = copy.deepcopy(r)
    if not isinstance(r.get("signatures"), dict):
        r["signatures"] = {}
    if not isinstance(r["signatures"].get("players"), dict):
        r["signatures"]["players"] = {}
    for p in r.get("players") or []:
        k = sb.player_keys.get(str((p or {}).get("pubkey", "")).lower()) if isinstance(p, dict) else None
        if k and isinstance(p.get("role"), str):
            r = sign_player(r, p["role"], k)
    return sign_referee(r, sb.referee)


def run_insider(sb: Sandbox, a: dict[str, Any]) -> dict[str, Any]:
    try:
        mutated = insider_sign(sb, apply_ops(sb.receipt, a.get("ops") or [], sb.donor))
    except (MutationError, KeyError, TypeError, ValueError, AttributeError) as e:
        return {"outcome": "invalid_mutation", "accepted": False, "status": None, "reasons": [f"harness:{e}"]}
    v = sb.verify(mutated, "honest")
    if canonicalize(mutated) in _honest_bytes(sb):
        return {"outcome": "no_tamper_identical_to_honest", "accepted": False, "status": v["status"],
                "reasons": ["canonical_bytes_identical_to_an_honest_receipt"]}
    accepted = v["status"] == "VERIFIED"
    row = {"outcome": "ACCEPTED" if accepted else "rejected", "accepted": accepted, "status": v["status"],
           "reasons": _compact(v["errors"] + v["partial"])}
    if accepted:
        row["label"] = INSIDER_ACCEPTED_LABEL
        row["note"] = INSIDER_NOTES.get(a.get("id"), DEFAULT_INSIDER_NOTE)
    return row


def run_attack(sb: Sandbox, a: dict[str, Any]) -> dict[str, Any]:
    desc, hits = safe_text(a.get("description"))
    row: dict[str, Any] = {"id": a.get("id"), "category": a.get("category"), "description": desc,
                           "resign": a.get("resign", "none"), "pin": a.get("pin", "honest")}
    if hits:
        row["wording_filter"] = hits
    try:
        if row["pin"] not in PINS:
            raise MutationError(f"unknown pin: {row['pin']}")
        mutated = resign(apply_ops(sb.receipt, a.get("ops") or [], sb.donor), row["resign"], sb.attacker,
                         sb.attacker_players)
    except (MutationError, KeyError, TypeError, ValueError) as e:
        row.update(outcome="invalid_mutation", accepted=False, status=None, reasons=[f"harness:{e}"])
        return row
    v = sb.verify(mutated, row["pin"])
    if canonicalize(mutated) in _honest_bytes(sb):
        # Byte-identical (after JCS) to an honest receipt: nothing was tampered. Reported, never hidden.
        row.update(outcome="no_tamper_identical_to_honest", accepted=False, status=v["status"],
                   reasons=["canonical_bytes_identical_to_an_honest_receipt"])
        return row
    accepted = v["status"] == "VERIFIED"
    row.update(outcome="ACCEPTED" if accepted else "rejected", accepted=accepted, status=v["status"],
               reasons=_compact(v["errors"] + v["partial"]))
    return row


def _compact(reasons: list[str], limit: int = 6) -> list[str]:
    """Collapse per-checkpoint repeats (``home:cp[3]:x`` -> ``home:cp[*]:x``), keep order, cap the list."""
    out: list[str] = []
    for x in reasons:
        x = re.sub(r"cp\[\d+\]", "cp[*]", x)
        if x not in out:
            out.append(x)
    return out[:limit]


def run(attacks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    doc = load_attacks() if attacks is None else {"attacks": attacks}
    sb = Sandbox()
    try:
        base = sb.verify(sb.receipt)
        if base["status"] != "VERIFIED":
            raise RuntimeError(f"baseline must be VERIFIED, got {base['status']}")
        rows = []
        for a in doc["attacks"]:
            row = run_attack(sb, a)
            row["insider"] = run_insider(sb, a)
            rows.append(row)
    finally:
        sb.close()
    tested = [r for r in rows if r["outcome"] in ("rejected", "ACCEPTED")]
    acc = [r for r in tested if r["accepted"]]
    ins = [r["insider"] for r in rows if r["insider"]["outcome"] in ("rejected", "ACCEPTED")]
    ins_acc = [r for r in rows if r["insider"]["accepted"]]
    return {
        "schema": "qortime-redteam-report/v1",
        "verifier": "qor_receipt.receipt.verify_receipt (pre-existing, pinned qortime@0e87ec3, unmodified)",
        "keys": "fresh in-memory TEST keys per run; TEST allowlist in a temp file; no real keys or live referee",
        "baseline": {"status": base["status"], "match": "qor_receipt.demo synthetic dual match (no real players)"},
        "generator": doc.get("generator"),
        "attacks_total": len(rows), "attacks_tested": len(tested), "accepted": len(acc),
        "invalid": sum(r["outcome"] == "invalid_mutation" for r in rows),
        "no_tamper": sum(r["outcome"] == "no_tamper_identical_to_honest" for r in rows),
        "headline": f"Outside attacker: {len(tested)} attacks · {len(acc)} accepted",
        "insider_tested": len(ins), "insider_accepted": len(ins_acc),
        "insider_accepted_ids": [r["id"] for r in ins_acc],
        "headline_insider": f"Insider with signing keys: {len(ins)} attacks · {len(ins_acc)} accepted",
        "insider_note": ("Insider pass: the tampered receipt is re-signed with the TEST referee and TEST player keys; "
                         "checkpoint countersignatures and challenge tokens are not re-forged. An accepted insider "
                         "forgery means " + INSIDER_ACCEPTED_LABEL + ", not a verifier bug."),
        "rows": rows,
    }


def outcome_table(report: dict[str, Any]) -> list[tuple]:
    """Key-independent view used to check reproducibility. The referee service orders challenges by random id, so
    which role sits at ``challenges.0`` varies per run; role prefixes are normalised for that reason only."""
    n = lambda rs: tuple(sorted({re.sub(r"^(home|away):", "<role>:", x) for x in rs}))
    return [(r["id"], r["outcome"], r["status"], n(r["reasons"]), r["insider"]["outcome"], r["insider"]["status"],
             n(r["insider"]["reasons"])) for r in report["rows"]]
