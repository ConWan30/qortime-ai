"""Agent verify API (qortime_ai/agent_api, built Oct 28 2026, in-window). Offline: a fake fetcher serves the public
170123 receipt (from the pinned upstream checkout), its match.json and its public-log inclusion proof (fixtures)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qortime_ai.agent_api import core
from qortime_ai.agent_api.app import create_app
from qortime_ai.agent_api.core import AGENT_RULE, BadRequest, Service, UpstreamError, match_id_from_url
from qortime_ai.ai_ruling.guardrail import BANNED, check_text
from qortime_ai.redteam.wording import banned_hits

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/agent_api"
RECEIPT_PATH = ROOT / "examples/170123/receipt.json"
pytestmark = pytest.mark.skipif(not RECEIPT_PATH.exists(), reason="run scripts/fetch_upstream.sh first")


def _site(receipt: dict | None = None, *, log: dict | None = None, page: dict | None = None):
    receipt = receipt if receipt is not None else json.loads(RECEIPT_PATH.read_text())
    log = log if log is not None else json.loads((FIX / "170123_log_inclusion.json").read_text())
    page = page if page is not None else json.loads((FIX / "170123_match.json").read_text())
    seen: list[str] = []

    def fetch(url: str) -> bytes:
        seen.append(url)
        if url == "https://qortime.com/matches/170123/receipt.json":
            return json.dumps(receipt).encode()
        if url == "https://qortime.com/matches/170123/match.json":
            return json.dumps(page).encode()
        if url.startswith(core.REFEREE_LOG):
            if url[len(core.REFEREE_LOG):] != log["entries"][0]["body_sha256"]:
                raise UpstreamError("http_404")
            return json.dumps(log).encode()
        raise UpstreamError("http_404")
    return fetch, seen


def _client(svc: Service, **kw) -> TestClient:
    return TestClient(create_app(svc, **kw))


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def _clean(o) -> list[str]:
    bad = []
    for s in _strings(o):
        bad += banned_hits(s)
        bad += [code for rx, code in BANNED if code in ("human_play_claim", "settle_language") and rx.search(s)]
    return bad


# ---- verify ---------------------------------------------------------------------------------------------------
def test_verify_real_receipt_is_true():
    fetch, seen = _site()
    r = _client(Service(fetch=fetch, published=("170123",))).get(
        "/agent/v1/verify", params={"url": "https://qortime.com/matches/170123/"})
    assert r.status_code == 200
    d = r.json()
    assert d["verified"] is True and d["status"] == "VERIFIED"
    assert d["checks"]["public_log"] == {"inclusion_ok": True, "head_signature_ok": True, "entry_matches_receipt": True}
    assert d["signer_key_id"] == "4fc237e4c6a24cf6" and d["final_score"] == {"away": 10, "home": 0}
    assert d["public_log_entry"]["seq"] == 1 and d["rule"] == AGENT_RULE
    assert set(seen) <= {"https://qortime.com/matches/170123/receipt.json", "https://qortime.com/matches/170123/match.json",
                         core.REFEREE_LOG + d["receipt_sha256"]["signed_body_jcs"]}
    assert _clean(d) == []


def test_tampered_receipt_fails():
    bad = json.loads(RECEIPT_PATH.read_text())
    bad["result"]["away_score"] = 3
    fetch, _ = _site(bad)
    d = _client(Service(fetch=fetch)).get("/agent/v1/verify", params={"url": "https://qortime.com/matches/170123/receipt.json"}).json()
    assert d["verified"] is False and d["status"] == "FAIL"
    assert any("bad_referee_signature" in x for x in d["reasons"])


def test_tampered_page_score_fails_closed():
    page = json.loads((FIX / "170123_match.json").read_text())
    page["final"] = {"away": 0, "home": 10}
    fetch, _ = _site(page=page)
    d = Service(fetch=fetch).verify("170123")
    assert d["verified"] is False and "match_page_score_differs_from_signed_receipt" in d["reasons"]


def test_forged_log_head_fails():
    log = json.loads((FIX / "170123_log_inclusion.json").read_text())
    log["head"]["size"] += 1
    fetch, _ = _site(log=log)
    d = Service(fetch=fetch).verify("170123")
    assert d["verified"] is False and d["status"] == "VERIFIED"  # the receipt is fine; the log check is not
    assert any(x.startswith("public_log:") for x in d["reasons"])


def test_log_unreachable_fails_closed():
    fetch, _ = _site()

    def no_log(url):
        if url.startswith(core.REFEREE_LOG):
            raise UpstreamError("unreachable:TimeoutError")
        return fetch(url)
    d = Service(fetch=no_log).verify("170123")
    assert d["verified"] is False and any("public_log_unavailable" in x for x in d["reasons"])


def test_receipt_unreachable_fails_closed():
    def down(url):
        raise UpstreamError("http_503")
    d = Service(fetch=down).verify("170123")
    assert d["verified"] is False and d["status"] is None


def test_wrong_pin_never_verifies():
    fetch, _ = _site()
    d = Service(fetch=fetch, pinned_pub="00" * 32).verify("170123")
    assert d["verified"] is False


# ---- SSRF / URL parsing ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("url,mid", [
    ("https://qortime.com/matches/170123/", "170123"),
    ("https://qortime.com/matches/220105", "220105"),
    ("https://www.qortime.com/matches/220105/receipt.json", "220105"),
    ("https://qortime.com/matches/220105/match.json", "220105"),
    ("https://qortime.com/verify/?receipt=https%3A%2F%2Fqortime.com%2Fmatches%2F170123%2Freceipt.json&referee=b283", "170123"),
    ("https://qortime.com/verify/?receipt=/matches/220105/receipt.json", "220105"),
])
def test_url_accepted(url, mid):
    assert match_id_from_url(url) == mid


@pytest.mark.parametrize("url", [
    "http://qortime.com/matches/170123/",
    "https://evil.example/matches/170123/receipt.json",
    "https://qortime.com.evil.example/matches/170123/",
    "https://qortime.com@169.254.169.254/matches/170123/",
    "https://user:pw@qortime.com/matches/170123/",
    "https://qortime.com:8443/matches/170123/",
    "https://169.254.169.254/latest/meta-data/",
    "https://localhost/matches/170123/",
    "https://qortime-referee-production.up.railway.app/v1/log/head",
    "file:///etc/passwd",
    "https://qortime.com/matches/../../etc/passwd",
    "https://qortime.com/matches/170123/../../admin",
    "https://qortime.com/matches/17012/",
    "https://qortime.com/verify/?receipt=https%3A%2F%2Fevil.example%2Fmatches%2F170123%2Freceipt.json",
    "",
])
def test_ssrf_rejected_without_fetching(url):
    calls = []
    c = _client(Service(fetch=lambda u: calls.append(u) or b"{}"))
    r = c.get("/agent/v1/verify", params={"url": url})
    assert r.status_code in (400, 422)
    assert calls == []
    with pytest.raises(BadRequest):
        match_id_from_url(url)


def test_bad_match_id_rejected():
    calls = []
    c = _client(Service(fetch=lambda u: calls.append(u) or b"{}"))
    assert c.get("/agent/v1/matches/abc").status_code == 400
    assert c.get("/agent/v1/matches/1701234").status_code == 400
    assert calls == []


# ---- matches --------------------------------------------------------------------------------------------------
def test_list_matches():
    fetch, _ = _site()
    d = _client(Service(fetch=fetch, published=("170123",))).get("/agent/v1/matches").json()
    assert d["count"] == 1 and d["rule"] == AGENT_RULE
    m = d["matches"][0]
    assert m["id"] == "170123" and m["published_status"] == "VERIFIED" and m["page_url"] == "https://qortime.com/matches/170123/"
    assert m["final_as_shown"] == {"away": 10, "home": 0}


def test_default_published_list():
    assert core.PUBLISHED_MATCHES == ("170123", "220105")


def test_get_match_detail_and_limits():
    fetch, _ = _site()
    r = _client(Service(fetch=fetch)).get("/agent/v1/matches/170123")
    d = r.json()
    assert r.status_code == 200 and d["verified"] is True and d["status"] == "VERIFIED"
    assert d["receipt_sha256"]["signed_body_jcs"] == "a69d866796d778dfaab409505b4d238a70d92bde458148de4cfc27fb778803c5"
    assert d["public_log_entry"]["match_id"] == "local-20261023-170123"
    assert "VERIFIED" in d["explanation"] and "who held the controller" in d["explanation"]
    assert any("who held the controller" in x for x in d["limits"])
    assert any("lower VERIFIED to PARTIAL" in x for x in d["limits"])
    assert _clean(d) == []


def test_not_verified_explanation_says_so():
    bad = json.loads(RECEIPT_PATH.read_text())
    bad["result"]["home_score"] = 7
    fetch, _ = _site(bad)
    d = Service(fetch=fetch).get_match("170123")
    assert d["verified"] is False and "NOT verified" in d["explanation"]
    assert _clean(d) == []


def test_self_signed_status_name_and_no_banned_words():
    # A receipt signed by an unknown referee key: the verifier says SELF_ATTESTED; the API shows SELF-SIGNED and
    # never emits the word itself.
    fetch, _ = _site()
    d = Service(fetch=fetch, pinned_pub="00" * 32).verify("170123")
    assert "attest" not in json.dumps(d).lower()
    assert core.status_name("SELF_ATTESTED") == "SELF-SIGNED"


# ---- spec, CORS, rate limit, MCP ------------------------------------------------------------------------------
def test_openapi_has_rule_and_paths():
    c = _client(Service(fetch=lambda u: b"{}"))
    s = c.get("/agent/v1/openapi.json").json()
    assert s["openapi"].startswith("3.1")
    assert set(s["paths"]) == {"/agent/v1/matches", "/agent/v1/matches/{match_id}", "/agent/v1/verify",
                               "/agent/v1/openapi.json"}
    text = json.dumps(s)
    assert "An agent must only announce or record a result as VERIFIED when verified is true; otherwise tell the user it is not verified and why." in text
    assert AGENT_RULE in s["info"]["description"] and s["x-agent-rule"] == AGENT_RULE
    for op in ("/agent/v1/matches", "/agent/v1/matches/{match_id}", "/agent/v1/verify"):
        assert AGENT_RULE in s["paths"][op]["get"]["description"]
    assert _clean(s) == []
    assert "post" not in json.dumps(s["paths"]).lower().replace("postgres", "")


def test_cors_open_and_get_only():
    fetch, _ = _site()
    c = _client(Service(fetch=fetch))
    r = c.get("/agent/v1/matches", headers={"Origin": "https://example.org"})
    assert r.headers["access-control-allow-origin"] == "*"
    assert c.post("/agent/v1/verify?url=https://qortime.com/matches/170123/").status_code == 405
    assert c.delete("/agent/v1/matches/170123").status_code == 405


def test_rate_limited():
    fetch, _ = _site()
    c = _client(Service(fetch=fetch), rate=3, verify_rate=2)
    codes = [c.get("/agent/v1/matches/170123").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = c.get("/agent/v1/matches")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_rate_limit_not_dodged_by_spoofed_forwarded_for():
    fetch, _ = _site()
    c = _client(Service(fetch=fetch), rate=2, verify_rate=2)
    codes = [c.get("/agent/v1/matches", headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"}).status_code
             for i in range(3)]
    assert codes == [200, 200, 429]


def test_cache_limits_upstream_calls():
    fetch, seen = _site()
    svc = Service(fetch=fetch)
    svc.verify("170123")
    n = len(seen)
    svc.verify("170123")
    svc.get_match("170123")
    assert len(seen) == n


def _rpc(c, method, params=None, rid=1):
    return c.post("/agent/mcp", json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}},
                  headers={"Accept": "application/json, text/event-stream"})


def test_mcp_tools():
    fetch, _ = _site()
    c = _client(Service(fetch=fetch, published=("170123",)))
    init = _rpc(c, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}).json()
    assert init["result"]["protocolVersion"] == "2025-06-18" and AGENT_RULE in init["result"]["instructions"]
    assert c.post("/agent/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    tools = _rpc(c, "tools/list").json()["result"]["tools"]
    assert {t["name"] for t in tools} == {"list_matches", "get_match", "verify_match"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    v = _rpc(c, "tools/call", {"name": "verify_match", "arguments": {"url": "https://qortime.com/matches/170123/"}}).json()
    assert v["result"]["structuredContent"]["verified"] is True
    g = _rpc(c, "tools/call", {"name": "get_match", "arguments": {"match_id": "170123"}}).json()
    assert g["result"]["structuredContent"]["status"] == "VERIFIED"
    s = _rpc(c, "tools/call", {"name": "verify_match", "arguments": {"url": "https://evil.example/x"}}).json()
    assert s["result"]["isError"] is True
    assert _rpc(c, "nope").json()["error"]["code"] == -32601
    assert c.get("/agent/mcp").status_code == 405
    assert _clean(tools) == []


# ---- guardrail lists ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["This is proof of human play.", "The agent will settle the bet.",
                                  "Wagers are settled automatically.", "It proves a human played."])
def test_new_banned_framing(text):
    assert banned_hits(text)
    assert any(rx.search(text) for rx, code in BANNED if code in ("human_play_claim", "settle_language"))


@pytest.mark.parametrize("text", ["Controller input advisory did not pass as human proof.", "This is proof of human input.",
                                  "The timing proves a human was there.", "A human-proof signal."])
def test_human_proof_framing_banned(text):
    assert banned_hits(text)
    assert any(rx.search(text) for rx, code in BANNED if code == "human_proof_claim")


def test_controller_timing_rewrite_passes_guardrail():
    t = ("VERIFIED\n\nThe controller-timing advisory was not above chance (435\u2030 vs 477\u2030). "
         "It is advisory only and does not show who played.")
    assert not banned_hits(t)
    assert check_text(t, "VERIFIED") == []


def test_new_banned_framing_allows_existing_honest_wording():
    assert not banned_hits("advisory evidence only, not proof of a human player")
    assert not banned_hits(AGENT_RULE)
