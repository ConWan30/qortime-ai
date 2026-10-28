"""OpenAPI 3.1 description of the agent verify API, written for AI agents (built Oct 28 2026, in-window)."""
from __future__ import annotations

from typing import Any

from qortime_ai.agent_api.core import AGENT_RULE, FRAMING, LIMITS, PINNED_REFEREE_PUB

INFO_DESCRIPTION = f"""Read-only API to check a QorTime video-game match result. QorTime's deterministic referee signs a
match receipt; this API re-runs the pre-existing verifier on the published receipt against the pinned official referee
key ({PINNED_REFEREE_PUB}) and checks that the receipt is in the referee's public transparency log.

RULE FOR AGENTS: {AGENT_RULE}

{FRAMING} This API runs no AI model and never decides a verdict; it reports what the pinned verifier returns.
Statuses: VERIFIED, PARTIAL, SELF-SIGNED, FAIL. Only VERIFIED with verified=true counts as verified.

Limits to pass on to the user: """ + " ".join(LIMITS) + """

Do not describe a result as proof of who played or held the controller. Use "records", "announces" or "unlocks on
VERIFIED" for what an agent may do with a verified result. Not affiliated with Meta, EA, the NFL, Sony or Activision."""

_ID = {"name": "match_id", "in": "path", "required": True, "description": "6-digit QorTime match id, e.g. 220105.",
       "schema": {"type": "string", "pattern": "^[0-9]{6}$", "examples": ["220105", "170123"]}}
_ERR = {"description": "Bad input (not a 6-digit id, or a URL that is not a https://qortime.com match or receipt URL).",
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}}
_RATE = {"description": "Rate limited. Wait and retry; see the Retry-After header.",
         "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}}


def spec(server_url: str | None = None) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "QorTime agent verify API", "version": "1.0.0", "description": INFO_DESCRIPTION,
                 "license": {"name": "PolyForm Noncommercial 1.0.0", "identifier": "PolyForm-Noncommercial-1.0.0"},
                 "contact": {"name": "QorTime", "email": "qoresence@mail.grokbot.com",
                             "url": "https://github.com/ConWan30/qortime-ai"}},
        "servers": [{"url": server_url or "/"}],
        "x-agent-rule": AGENT_RULE,
        "paths": {
            "/agent/v1/matches": {"get": {
                "operationId": "listMatches",
                "summary": "List the published QorTime matches",
                "description": "Lists published matches with the status shown on each match page and links. The "
                               "published status is NOT a verification: call verifyMatch before announcing or "
                               "recording any result. " + AGENT_RULE,
                "responses": {"200": {"description": "Published matches.", "content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/MatchList"}}}}, "429": _RATE}}},
            "/agent/v1/matches/{match_id}": {"get": {
                "operationId": "getMatch",
                "summary": "One match: status, final score, signer, receipt hash, public-log entry, limits",
                "description": "Re-runs the pinned verifier and the public-log check for this match and returns the "
                               "result with a one-line plain explanation and the limits the user should hear. "
                               + AGENT_RULE,
                "parameters": [_ID],
                "responses": {"200": {"description": "Match detail.", "content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/Match"}}}}, "400": _ERR, "429": _RATE}}},
            "/agent/v1/verify": {"get": {
                "operationId": "verifyMatch",
                "summary": "Verify a QorTime match from its page, receipt or verifier URL",
                "description": "Accepts only https://qortime.com URLs: a match page (https://qortime.com/matches/<id>/), "
                               "its receipt.json or match.json, or a qortime.com/verify/?receipt=... link. The API "
                               "extracts the match id and fetches the published receipt itself; it never fetches "
                               "the URL you send. It checks the receipt signature with the pre-existing verifier "
                               "against the pinned referee key and checks the referee's public log. verified is true "
                               "only if every check passes. " + AGENT_RULE,
                "parameters": [{"name": "url", "in": "query", "required": True,
                                "description": "A https://qortime.com match page, receipt.json, match.json or "
                                               "verifier URL.",
                                "schema": {"type": "string", "format": "uri",
                                           "examples": ["https://qortime.com/matches/220105/"]}}],
                "responses": {"200": {"description": "Verification result (verified may be false; read reasons).",
                                      "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Verify"}}}},
                              "400": _ERR, "429": _RATE}}},
            "/agent/v1/openapi.json": {"get": {"operationId": "getOpenApi", "summary": "This document",
                                                "responses": {"200": {"description": "OpenAPI 3.1 JSON."}}}},
        },
        "components": {"schemas": {
            "Error": {"type": "object", "required": ["error"], "properties": {
                "error": {"type": "string"}, "rule": {"type": "string"}}},
            "MatchList": {"type": "object", "properties": {
                "count": {"type": "integer"}, "rule": {"type": "string", "const": AGENT_RULE},
                "matches": {"type": "array", "items": {"type": "object", "properties": {
                    "id": {"type": "string"}, "page_url": {"type": "string"},
                    "published_status": {"type": ["string", "null"],
                                         "description": "Status shown on the match page. Not a verification."},
                    "final_as_shown": {"type": "object"}, "detail_url": {"type": "string"},
                    "verify_url": {"type": "string"}}}}}},
            "Verify": {"type": "object", "required": ["match", "verified", "reasons", "rule"], "properties": {
                "match": {"type": "string"},
                "verified": {"type": "boolean", "description": "True only if the pinned verifier returns VERIFIED, "
                             "the signer is the pinned referee key, the receipt is in the public log under a valid "
                             "signed head, and the page score equals the signed receipt. " + AGENT_RULE},
                "status": {"type": ["string", "null"], "enum": ["VERIFIED", "PARTIAL", "SELF-SIGNED", "FAIL", None]},
                "reasons": {"type": "array", "items": {"type": "string"},
                            "description": "Checks that passed when verified is true; the failures when it is false. "
                                           "Tell the user these when verified is false."},
                "rule": {"type": "string", "const": AGENT_RULE},
                "final_score": {"type": ["object", "null"], "properties": {"away": {"type": ["integer", "null"]},
                                                                            "home": {"type": ["integer", "null"]}}},
                "signer_key_id": {"type": ["string", "null"]},
                "receipt_sha256": {"type": ["object", "null"], "description": "signed_body_jcs = SHA-256 of the "
                                   "receipt's signed bytes (the value the public log records); file = SHA-256 of the "
                                   "published file."},
                "public_log_entry": {"type": ["object", "null"]},
                "checks": {"type": "object"}, "page_url": {"type": "string"}, "verifier_url": {"type": "string"}}},
            "Match": {"allOf": [{"$ref": "#/components/schemas/Verify"}, {"type": "object", "properties": {
                "id": {"type": "string"}, "status_on_page": {"type": ["string", "null"]},
                "explanation": {"type": "string", "description": "One plain sentence for the user."},
                "notes": {"type": "array", "items": {"type": "string"}},
                "limits": {"type": "array", "items": {"type": "string"},
                           "description": "What this result does not show. Pass these on."}}}]},
        }},
    }
