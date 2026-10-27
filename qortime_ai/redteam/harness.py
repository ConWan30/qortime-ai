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
        self.receipt, _ = run_match(client, clock, "dual")
        clock.t += 3_600_000
        self.donor, _ = run_match(client, clock, "dual")
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
        rows = [run_attack(sb, a) for a in doc["attacks"]]
    finally:
        sb.close()
    tested = [r for r in rows if r["outcome"] in ("rejected", "ACCEPTED")]
    acc = [r for r in tested if r["accepted"]]
    return {
        "schema": "qortime-redteam-report/v1",
        "verifier": "qor_receipt.receipt.verify_receipt (pre-existing, pinned qortime@0e87ec3, unmodified)",
        "keys": "fresh in-memory TEST keys per run; TEST allowlist in a temp file; no real keys or live referee",
        "baseline": {"status": base["status"], "match": "qor_receipt.demo synthetic dual match (no real players)"},
        "generator": doc.get("generator"),
        "attacks_total": len(rows), "attacks_tested": len(tested), "accepted": len(acc),
        "invalid": sum(r["outcome"] == "invalid_mutation" for r in rows),
        "no_tamper": sum(r["outcome"] == "no_tamper_identical_to_honest" for r in rows),
        "headline": f"{len(tested)} attacks · {len(acc)} accepted",
        "rows": rows,
    }


def outcome_table(report: dict[str, Any]) -> list[tuple]:
    """Key-independent view used to check reproducibility."""
    return [(r["id"], r["outcome"], r["status"], tuple(r["reasons"])) for r in report["rows"]]
