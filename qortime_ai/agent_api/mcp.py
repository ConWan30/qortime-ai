"""Thin MCP (Streamable HTTP, JSON responses, stateless) endpoint over the agent verify API. Read-only tools.

Built Oct 28 2026, in-window. Implements initialize, ping, tools/list and tools/call; notifications get 202.
"""
from __future__ import annotations

import json
from typing import Any

from qortime_ai.agent_api.core import AGENT_RULE, FRAMING, BadRequest, Service

SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")
_RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}

TOOLS = [
    {"name": "list_matches", "title": "List QorTime matches",
     "description": "List published QorTime matches with the status shown on each page. Not a verification: call "
                    "verify_match before announcing or recording a result. " + AGENT_RULE,
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": _RO},
    {"name": "get_match", "title": "Get one QorTime match",
     "description": "Status, final score, signer key id, receipt hash, public-log entry, a one-line explanation and "
                    "the limits for one match (re-checked with the pinned verifier). " + AGENT_RULE,
     "inputSchema": {"type": "object", "required": ["match_id"], "additionalProperties": False,
                     "properties": {"match_id": {"type": "string", "pattern": "^[0-9]{6}$",
                                                 "description": "6-digit match id, e.g. 220105"}}},
     "annotations": _RO},
    {"name": "verify_match", "title": "Verify a QorTime match URL",
     "description": "Verify a https://qortime.com match page, receipt.json or verifier URL: signature check against "
                    "the pinned referee key plus the referee's public log. " + AGENT_RULE + " " + FRAMING,
     "inputSchema": {"type": "object", "required": ["url"], "additionalProperties": False,
                     "properties": {"url": {"type": "string", "description": "https://qortime.com/matches/<id>/"}}},
     "annotations": _RO},
]


def _ok(rid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid: Any, code: int, msg: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def handle(msg: Any, svc: Service, *, version: str) -> dict[str, Any] | None:
    """One JSON-RPC message -> response dict, or None for a notification."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _err(msg.get("id") if isinstance(msg, dict) else None, -32600, "invalid request")
    rid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if "id" not in msg:
        return None
    if method == "initialize":
        want = params.get("protocolVersion") if isinstance(params, dict) else None
        return _ok(rid, {"protocolVersion": want if want in SUPPORTED else SUPPORTED[0],
                         "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": {"name": "qortime-agent-verify", "title": "QorTime agent verify",
                                        "version": version},
                         "instructions": AGENT_RULE + " " + FRAMING})
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        if not isinstance(params, dict):
            return _err(rid, -32602, "invalid params")
        name, args = params.get("name"), params.get("arguments") or {}
        if not isinstance(args, dict):
            return _err(rid, -32602, "arguments must be an object")
        try:
            if name == "list_matches":
                data = svc.list_matches()
            elif name == "get_match":
                data = svc.get_match(str(args.get("match_id", "")))
            elif name == "verify_match":
                from qortime_ai.agent_api.core import match_id_from_url
                data = svc.verify(match_id_from_url(str(args.get("url", ""))))
            else:
                return _err(rid, -32602, f"unknown tool: {name}")
        except BadRequest as e:
            return _ok(rid, {"isError": True, "content": [{"type": "text", "text": f"rejected: {e}"}]})
        return _ok(rid, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                         "structuredContent": data, "isError": False})
    return _err(rid, -32601, f"method not found: {method}")
