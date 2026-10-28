"""FastAPI app for the public, read-only agent verify API (built Oct 28 2026, in-window).

Run: ``uvicorn qortime_ai.agent_api.app:app --host 0.0.0.0 --port $PORT``
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from qortime_ai.agent_api import mcp
from qortime_ai.agent_api.core import AGENT_RULE, BadRequest, Service, UpstreamError, match_id_from_url
from qortime_ai.agent_api.openapi import spec

VERSION = "1.0.0"


class RateLimiter:
    """Sliding window per client IP. Defaults: 60 requests / 60 s overall, 20 / 60 s for verify-type calls."""

    def __init__(self, limit: int, window_s: float = 60.0, now=time.monotonic):
        self.limit, self.window_s, self.now = limit, window_s, now
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        t = self.now()
        with self.lock:
            q = self.hits[key]
            while q and t - q[0] >= self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window_s - (t - q[0])) + 1)
            q.append(t)
            if len(self.hits) > 10000:  # bound memory
                for k in [k for k, v in self.hits.items() if not v][:5000]:
                    del self.hits[k]
            return True, 0


def _client(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def create_app(svc: Service | None = None, *, rate: int | None = None, verify_rate: int | None = None) -> FastAPI:
    svc = svc or Service()
    app = FastAPI(title="QorTime agent verify API", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["*"], expose_headers=["Mcp-Session-Id", "Retry-After"])
    general = RateLimiter(rate or int(os.environ.get("AGENT_API_RATE_PER_MIN", "60")))
    heavy = RateLimiter(verify_rate or int(os.environ.get("AGENT_API_VERIFY_RATE_PER_MIN", "20")))

    @app.middleware("http")
    async def limit(request: Request, call_next):
        if request.method != "OPTIONS" and request.url.path.startswith("/agent/"):
            ip = _client(request)
            ok, wait = general.allow(ip)
            p = request.url.path
            if ok and (p.startswith("/agent/v1/verify") or p.startswith("/agent/v1/matches/") or p == "/agent/mcp"):
                ok, wait = heavy.allow(ip)
            if not ok:
                return JSONResponse({"error": "rate_limited", "rule": AGENT_RULE}, status_code=429,
                                    headers={"Retry-After": str(wait)})
        resp = await call_next(request)
        resp.headers.setdefault("Cache-Control", "public, max-age=60")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        return resp

    def bad(e: Exception, code: int = 400) -> JSONResponse:
        return JSONResponse({"error": str(e), "rule": AGENT_RULE}, status_code=code)

    @app.get("/")
    def root():
        return {"service": "QorTime agent verify API (read-only)", "openapi": "/agent/v1/openapi.json",
                "mcp": "/agent/mcp", "matches": "/agent/v1/matches", "rule": AGENT_RULE,
                "source": "https://github.com/ConWan30/qortime-ai"}

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/agent/v1/openapi.json")
    def openapi_json(request: Request):
        base = str(request.base_url).rstrip("/")
        if request.headers.get("x-forwarded-proto") == "https":
            base = base.replace("http://", "https://", 1)
        return spec(base)

    @app.get("/agent/v1/matches")
    def list_matches():
        return svc.list_matches()

    @app.get("/agent/v1/matches/{match_id}")
    def get_match(match_id: str):
        try:
            return svc.get_match(match_id)
        except BadRequest as e:
            return bad(e)

    @app.get("/agent/v1/verify")
    def verify(url: str = Query(..., max_length=2048)):
        try:
            mid = match_id_from_url(url)
        except BadRequest as e:
            return bad(e)
        return svc.verify(mid)

    @app.get("/agent/mcp")
    def mcp_get():
        return Response(status_code=405, headers={"Allow": "POST"})

    @app.post("/agent/mcp")
    async def mcp_post(request: Request):
        body = await request.body()
        if len(body) > 64 * 1024:
            return JSONResponse(mcp._err(None, -32600, "request too large"), status_code=413)
        try:
            import json
            msg = json.loads(body or b"null")
        except ValueError:
            return JSONResponse(mcp._err(None, -32700, "parse error"), status_code=400)
        if isinstance(msg, list):
            out = [r for r in (mcp.handle(m, svc, version=VERSION) for m in msg[:10]) if r is not None]
            return JSONResponse(out) if out else Response(status_code=202)
        r = mcp.handle(msg, svc, version=VERSION)
        return JSONResponse(r) if r is not None else Response(status_code=202)

    @app.exception_handler(UpstreamError)
    async def upstream(_req, e):
        return JSONResponse({"error": f"upstream_unavailable:{e}", "rule": AGENT_RULE}, status_code=502)

    return app


app = create_app()
