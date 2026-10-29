[← Docs](README.md)

# Agent verify API: let any AI agent check a QorTime match

**Built Wed Oct 28 2026, during the Meta Global AI Developer Hackathon week (Oct 26 – Nov 4 2026).**
Code: [`qortime_ai/agent_api/`](../qortime_ai/agent_api/) · tests: [`tests/test_agent_api.py`](../tests/test_agent_api.py) ·
deploy: [`deploy/agent-api/Dockerfile`](../deploy/agent-api/Dockerfile).

> **Your agent can't make a match VERIFIED. Only the referee's signed receipt can.**
>
> Rule for every agent: **an agent must only announce or record a result as VERIFIED when `verified` is true;
> otherwise tell the user it is not verified and why.**

A public, read-only API. Any agent that supports OpenAPI or MCP connectors can call it, and so can bots and scripts.
It lists QorTime's published matches and re-checks one. It re-runs the **pre-existing** deterministic verifier
(`qor_receipt.receipt.verify_receipt`, pinned at `ConWan30/qortime@0e87ec3`) on the published receipt against the
pinned official referee key, then checks the referee's public transparency log. It runs **no AI model** and decides
nothing; it reports what the verifier returns.

**Live base URL:** `https://agent-api-production-0e55.up.railway.app`

| Endpoint | What it returns |
|---|---|
| `GET /agent/v1/matches` | Published matches (170123, 220105): status shown on the page, final as shown, page URL, links |
| `GET /agent/v1/matches/{id}` | Re-checked status, final score, signer key id, receipt SHA-256, public-log entry, page URL, one-line explanation, notes, `limits` |
| `GET /agent/v1/verify?url=<qortime.com URL>` | `verified` true/false, `status`, `reasons`, per-check detail |
| `GET /agent/v1/openapi.json` | OpenAPI 3.1 spec, descriptions written for AI agents, with the VERIFIED-only rule |
| `POST /agent/mcp` | MCP (Streamable HTTP, stateless, JSON responses): tools `list_matches`, `get_match`, `verify_match` (all read-only) |

GET only (the MCP endpoint is POST because MCP requires it, and is read-only too). No auth, CORS open (`*`),
rate-limited per client IP (60 requests/min overall, 20/min for verify-type calls; `429` + `Retry-After`).
Upstream reads are cached for 5 minutes, so the referee and qortime.com see at most a few requests per match.

## What `verified: true` means
All of these hold, otherwise `verified` is `false` and `reasons` lists what failed:
1. The pre-existing verifier returns `VERIFIED` for the published receipt with the referee key pinned to
   `b283cffb…4889` (`qortime-online-s2`, delegation serial 2 from root `qortime-v1`), including its delegation and
   allowlist checks.
2. The receipt's referee key is that pinned key.
3. The receipt's signed body (SHA-256 of JCS without `signatures`) is in the referee's public log
   (`/v1/log/inclusion/<hash>`), the hash chain from that entry to the head checks out, the log head is signed by the
   pinned key, and the entry names the same match and signer.
4. The score on the match page equals the signed receipt.

Fail-closed: if qortime.com or the public log can't be read, `verified` is `false`.

## No SSRF
`/verify` accepts only `https://qortime.com` (or `www.`) URLs: a match page, its `receipt.json` / `match.json`, or a
`qortime.com/verify/?receipt=…` link. The API only **extracts the 6-digit match id** and then fetches URLs it builds
itself (`https://qortime.com/matches/<id>/receipt.json`, `match.json`, and the referee's public-log inclusion URL).
The URL you send is never fetched. Redirects are not followed; responses are capped at 4 MB. Other schemes, hosts,
ports, user-info tricks and path traversal get `400` (tests cover each).

## Using it from an agent
- **Custom connector from OpenAPI:** give the agent `https://agent-api-production-0e55.up.railway.app/agent/v1/openapi.json`.
- **MCP connector:** URL `https://agent-api-production-0e55.up.railway.app/agent/mcp` (no auth).
- **Plain HTTPS:** `curl "https://agent-api-production-0e55.up.railway.app/agent/v1/verify?url=https://qortime.com/matches/220105/"`

What an agent may say, depending on the answer:

| Answer | Say | Don't say |
|---|---|---|
| `verified: true` | "Match 220105 is VERIFIED by the QorTime referee's signed receipt: away 7 – home 21." Then the `limits`, e.g. it does not show who held the controller. The agent may record or announce it, with the limits. | That it shows who played, that a human played, or that the AI decided it |
| `verified: false` | "This match is not verified," plus the `reasons` | Anything that treats it as VERIFIED, including PARTIAL or SELF-SIGNED |

## Sample (`GET /agent/v1/verify?url=https://qortime.com/matches/220105/`, abridged)
```json
{
  "match": "220105", "verified": true, "status": "VERIFIED",
  "reasons": [
    "receipt signature and checks pass under the pinned referee key (verifier status VERIFIED)",
    "receipt is in the referee's public log (entry seq 4), and the signed log head checks out under the pinned key",
    "the score shown on the match page equals the signed receipt"
  ],
  "rule": "An agent must only announce or record a result as VERIFIED when verified is true; otherwise tell the user it is not verified and why.",
  "final_score": {"away": 7, "home": 21},
  "signer_key_id": "4fc237e4c6a24cf6",
  "receipt_sha256": {"signed_body_jcs": "8a3a6d60e498c607fef79e013afab333b760fb7c9e58e16fa9912683c98cb71b", "file": "c35f4fd7…"},
  "public_log_entry": {"seq": 4, "submission": "1d424dc2836f1a8c", "match_id": "local-20261027-220105", "signer_key_id": "4fc237e4c6a24cf6"},
  "advisory_flags": ["alignment_not_above_chance"]
}
```

## Limits
- It checks what the receipt and the public log say. It does **not** show who held the controller or that a
  particular person played, and it does not catch collusion. Every `/matches/{id}` answer carries a `limits` array
  copied from the README's honesty rules plus the referee's own "not proven" list from the receipt.
- Two published matches is a small sample (n = 2). Both are Madden NFL 27 on PS5, single-sided.
- The verifier is pinned at the pre-event commit. A key revocation published later in the qortime repo would not
  be seen by this pinned copy (the public-log head check still requires the pinned key).
- The published-match list is fixed in code (`PUBLISHED_MATCHES`); new matches need a code change.
- The rate limiter and cache are in memory, per instance.

## Deploy (Railway)
Project `qortime-ai`, service `agent-api`, built from `deploy/agent-api/Dockerfile` (repo root as build context),
healthcheck `/healthz`, no variables or secrets needed. Optional: `AGENT_API_RATE_PER_MIN`,
`AGENT_API_VERIFY_RATE_PER_MIN`. Run locally:
```bash
pip install -e '.[agent-api]'
uvicorn qortime_ai.agent_api.app:app --port 8080
```
It never writes to the referee and never submits anything to it; it only reads the public log.
