"""Structured receipt mutations (the attack DSL Muse Wonder writes in).

An attack is JSON::

    {"id": "score_edit", "category": "edit", "description": "...", "expected_catch": "...",
     "ops": [{"op": "set", "path": "result.home_score", "value": 31}],
     "resign": "none", "pin": "honest"}

ops (applied in order, paths are dot-separated, list indexes are integers, ``-1`` = last):
  set {path, value}            replace or add a field
  delete {path}                remove a field / list item
  swap {path, with}            exchange two values
  shift_int {path, by}         add an integer (timestamps, scores)
  reverse {path}               reverse a list
  move {path, to}              move a list item from index ``path`` to index ``to`` (same list)
  copy_from_donor {path}       copy the value at ``path`` from a second honest receipt (another match, same referee)
  replace_with_donor {}        the whole receipt becomes the donor (pure replay)
resign: none | attacker_sig_only | attacker_identity | attacker_identity_and_players
pin (what the verifying user pins): honest | attacker | none
"""
from __future__ import annotations

import copy
from typing import Any

from qor_receipt.receipt import sign_player, sign_referee
from qor_receipt.keys import SoftwareKey

OPS = {"set", "delete", "swap", "shift_int", "reverse", "move", "copy_from_donor", "replace_with_donor"}
RESIGN = {"none", "attacker_sig_only", "attacker_identity", "attacker_identity_and_players"}
PINS = {"honest", "attacker", "none"}


class MutationError(ValueError):
    pass


def _key(container: Any, part: str) -> Any:
    if isinstance(container, list):
        try:
            i = int(part)
        except ValueError:
            raise MutationError(f"list index expected: {part}") from None
        if not -len(container) <= i < len(container):
            raise MutationError(f"index out of range: {part}")
        return i
    if isinstance(container, dict):
        return part
    raise MutationError(f"cannot descend into {type(container).__name__}")


def _parent(doc: Any, path: str, *, create: bool = False) -> tuple[Any, Any]:
    parts = [p for p in str(path).split(".") if p != ""]
    if not parts:
        raise MutationError("empty path")
    cur = doc
    for p in parts[:-1]:
        k = _key(cur, p)
        if isinstance(cur, dict) and k not in cur:
            if not create:
                raise MutationError(f"missing: {path}")
            cur[k] = {}
        cur = cur[k]
    k = _key(cur, parts[-1])
    if isinstance(cur, dict) and k not in cur and not create:
        raise MutationError(f"missing: {path}")
    return cur, k


def get(doc: Any, path: str) -> Any:
    c, k = _parent(doc, path)
    return c[k]


def apply_ops(receipt: dict, ops: list[dict], donor: dict) -> dict:
    r = copy.deepcopy(receipt)
    for op in ops:
        kind = op.get("op")
        if kind not in OPS:
            raise MutationError(f"unknown op: {kind}")
        if kind == "replace_with_donor":
            r = copy.deepcopy(donor)
        elif kind == "set":
            c, k = _parent(r, op["path"], create=True)
            c[k] = copy.deepcopy(op.get("value"))
        elif kind == "delete":
            c, k = _parent(r, op["path"])
            del c[k]
        elif kind == "swap":
            c1, k1 = _parent(r, op["path"])
            c2, k2 = _parent(r, op["with"])
            c1[k1], c2[k2] = c2[k2], c1[k1]
        elif kind == "shift_int":
            c, k = _parent(r, op["path"])
            if not isinstance(c[k], int) or isinstance(c[k], bool):
                raise MutationError(f"not an int: {op['path']}")
            c[k] += int(op["by"])
        elif kind == "reverse":
            c, k = _parent(r, op["path"])
            if not isinstance(c[k], list):
                raise MutationError(f"not a list: {op['path']}")
            c[k] = list(reversed(c[k]))
        elif kind == "move":
            c, k = _parent(r, op["path"])
            if not isinstance(c, list):
                raise MutationError(f"move needs a list item: {op['path']}")
            item = c.pop(k)
            c.insert(int(op["to"]), item)
        elif kind == "copy_from_donor":
            dc, dk = _parent(donor, op["path"])
            c, k = _parent(r, op["path"], create=True)
            c[k] = copy.deepcopy(dc[dk])
    return r


def resign(r: dict, mode: str, attacker: SoftwareKey, attacker_players: dict[str, SoftwareKey]) -> dict:
    """Re-sign with attacker keys (the attacker never has the TEST referee's private key)."""
    if mode not in RESIGN:
        raise MutationError(f"unknown resign: {mode}")
    if mode == "none":
        return r
    r = copy.deepcopy(r)
    r.setdefault("signatures", {}).setdefault("players", {})
    if mode in ("attacker_identity", "attacker_identity_and_players"):
        r["referee"] = {**(r.get("referee") or {}), "pubkey": attacker.pubkey_hex, "key_id": attacker.key_id}
    if mode == "attacker_identity_and_players":
        for p in r.get("players") or []:
            k = attacker_players.setdefault(p.get("role"), SoftwareKey())
            p["pubkey"] = k.pubkey_hex
        for p in r.get("players") or []:
            r = sign_player(r, p["role"], attacker_players[p["role"]])
    return sign_referee(r, attacker)
