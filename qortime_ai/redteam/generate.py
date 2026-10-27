"""Live generation (operator only, costs Meta credits): refresh the cached fixtures the tests and CLI run on.

    META_API_KEY=... QAI_SPEND_LOG=/path/spend.jsonl python -m qortime_ai.redteam --generate

The key comes only from the environment and is never written anywhere. Each call is appended to QAI_SPEND_LOG.
"""
from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any

from qortime_ai.ai_ruling.muse import MuseClient
from qortime_ai.redteam import mutations
from qortime_ai.redteam.citations import DISPLAY, facts

WONDER, SPARK = "muse-wonder-1.0", "muse-spark-1.3"
PRICE = {WONDER: (4e-6, 20e-6), SPARK: (1.25e-6, 4.25e-6)}  # USD per token (in, out), as used in the Oct 27 probes


def _log(model: str, step: str, usage: dict[str, int]) -> float:
    pi, po = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    usd = pi * PRICE[model][0] + po * PRICE[model][1]
    path = os.environ.get("QAI_SPEND_LOG")
    if path:
        row = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "step": f"redteam oct27 {step}",
               "model": model, "http": 200, "prompt_tokens": pi, "completion_tokens": po, "usd_est": round(usd, 6)}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    return usd


def _json(text: str) -> Any:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(t[t.find("{"): t.rfind("}") + 1])


def skeleton(receipt: dict[str, Any]) -> dict[str, Any]:
    """Receipt with long lists cut to 2 items so the prompt stays small (structure and real paths are kept)."""
    def cut(v: Any) -> Any:
        if isinstance(v, list):
            return [cut(x) for x in v[:2]] + ([f"... {len(v) - 2} more"] if len(v) > 2 else [])
        if isinstance(v, dict):
            return {k: cut(x) for k, x in v.items()}
        return v
    return cut(receipt)


WONDER_SYS = ("You are a red-team agent attacking a match-receipt verifier you do not control. You never have the "
              "referee's private key; you may generate your own keys only through the 'resign' modes. Reply with JSON only.")


def wonder_attacks(receipt: dict[str, Any], n: int = 26) -> tuple[dict[str, Any], float]:
    user = (f"Propose {n} distinct, concrete tampering attacks against this signed receipt, as structured mutations in "
            f"this DSL:\n{mutations.__doc__}\nCover: forged/re-signed signatures, score and winner edits, match id swap, "
            "replay or splice from another match (donor), dropped/reordered fields and list items, timestamp splices, "
            "trust_tier / key_kind / delegation downgrades or upgrades, checkpoint chain edits, challenge evidence edits, "
            "signal laundering, pin tricks, type confusion (strings for ints, nulls), duplicate roles. Use only paths "
            "that exist in the receipt below (or deliberate new fields). Each attack: {\"id\" (snake_case, unique), "
            "\"category\", \"description\" (one plain sentence), \"expected_catch\" (which check should catch it), "
            "\"ops\", \"resign\", \"pin\"}. Return {\"attacks\": [...]}.\nRECEIPT (lists truncated):\n"
            + json.dumps(skeleton(receipt), separators=(",", ":")))
    c = MuseClient(model=WONDER, max_tokens=16000, reasoning_effort="low", timeout_s=300)
    rep = c.chat(WONDER_SYS, user)
    usd = _log(WONDER, f"wonder attack generation n={n}", rep.usage)
    doc = _json(rep.text)
    doc["generator"] = {"model": rep.model, "reasoning_effort": "low", "usage": rep.usage, "usd_est": round(usd, 6),
                        "generated": datetime.date.today().isoformat(),
                        "note": "cached model output; tests and the CLI replay it offline"}
    return doc, usd


SPARK_SYS = ("You explain a deterministic match referee's result in plain English for a player. You never decide or "
             "change the verdict; it is given. Write 3 to 5 short sentences. EVERY sentence must end with one or more "
             "citations in square brackets naming the FACT keys it relies on, e.g. 'The referee returned VERIFIED "
             "[verdict].' Only use keys from FACTS; only state numbers and values that appear in the cited keys. Never "
             "use the words attested, certified, guaranteed, hardware-verified, cheat-free, tamper-proof (you may cite "
             "the key [trust_tier] but never write its value). Say what is not proven: who held the controller. "
             "Plain text only.")


def spark_explain(receipt: dict[str, Any], verdict: dict[str, Any]) -> tuple[dict[str, Any], float]:
    fx = facts(receipt, verdict)
    user = f"STATUS (display word): {DISPLAY[verdict['status']]}\nFACTS:\n{json.dumps(fx, indent=1)}"
    c = MuseClient(model=SPARK, max_tokens=3000, reasoning_effort="low", timeout_s=120)
    rep = c.chat(SPARK_SYS, user)
    usd = _log(SPARK, f"spark cited explanation status={verdict['status']}", rep.usage)
    return {"facts": fx, "text": rep.text.strip(), "model": rep.model, "usage": rep.usage, "usd_est": round(usd, 6)}, usd
