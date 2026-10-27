"""Replay the cached Muse Spark explanations against freshly computed facts (offline, deterministic)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qortime_ai.redteam.citations import check, facts
from qortime_ai.redteam.harness import FIXTURES, Sandbox
from qortime_ai.redteam.mutations import apply_ops
from qortime_ai.redteam.wording import safe_text

EXPLANATIONS_PATH = FIXTURES / "spark_explanations.json"
# Fixed cases (not model-chosen): the honest receipt, and an unsigned score edit.
CASES = {"honest": [], "score_edit_unsigned": [{"op": "set", "path": "result.home_score", "value": 31}]}


def case_inputs(sb: Sandbox) -> dict[str, tuple[dict, dict]]:
    out = {}
    for name, ops in CASES.items():
        r = apply_ops(sb.receipt, ops, sb.donor)
        out[name] = (r, sb.verify(r))
    return out


def audit(sb: Sandbox, path: str | Path | None = None) -> list[dict[str, Any]]:
    cached = json.loads(Path(path or EXPLANATIONS_PATH).read_text(encoding="utf-8"))["cases"]
    rows = []
    for name, (r, v) in case_inputs(sb).items():
        c = cached[name]
        fx = facts(r, v)
        probs = check(c["text"], fx)
        if c["facts"] != fx:
            probs.insert(0, {"sentence": None, "problem": "stale_fixture_facts_changed"})
        shown, _ = safe_text(c["text"])
        rows.append({"case": name, "verdict": v["status"], "model": c.get("model"),
                     "shown": not probs, "text": shown if not probs else None, "problems": probs})
    return rows
