"""Core logic of the agent verify API: fetch public match data, re-run the pinned verifier, check the public log.

Pure functions plus a small cache. Network access goes through one injectable ``Fetcher`` so tests run offline and
so the only URLs ever fetched are ones this module builds itself (https://qortime.com/matches/<6 digits>/... and the
referee's public log). A user-supplied URL is only parsed for a match id, never fetched (no SSRF).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from qor_receipt.keys import kid
from qor_receipt.receipt import verify_receipt
from qor_receipt.translog import body_sha256, entry_hash, verify_head, verify_inclusion

SITE = "https://qortime.com"
REFEREE_LOG = "https://qortime-referee-production.up.railway.app/v1/log/inclusion/"
# The official QorTime online referee key (qortime-online-s2, delegation serial 2 from root qortime-v1). Same pin as
# the README's verifier links. The verifier also checks the delegation against the pre-existing allowlist.
PINNED_REFEREE_PUB = "b283cffb9279f2f90859268c64ef21861ef7e5d9fc773bdb8061af0e80624889"
PUBLISHED_MATCHES = ("170123", "220105")
ALLOWED_HOSTS = frozenset({"qortime.com", "www.qortime.com"})
MAX_BYTES = 4 * 1024 * 1024
CACHE_TTL_S = 300.0
ID_RE = re.compile(r"^[0-9]{6}$")
_PATH_RE = re.compile(r"^/matches/([0-9]{6})(?:/(?:|index\.html|receipt\.json|match\.json))?$")

AGENT_RULE = ("An agent must only announce or record a result as VERIFIED when verified is true; otherwise tell the "
              "user it is not verified and why.")
FRAMING = "Your agent can't make a match VERIFIED. Only the referee's signed receipt can."

# Copied from the README's "Honesty rules and limits" (same meaning, shortened).
LIMITS = [
    "QorTime does not prove who held the controller and does not catch collusion.",
    "A VERIFIED receipt does not show that a particular person played; it shows that the official referee signed this "
    "result after its checks passed.",
    "Two referee-verified matches is a small sample (n = 2), not a measured accuracy.",
    "Both published matches are Madden NFL 27 on PS5, one player's own matches, single-sided (only one side recorded, "
    "no two-player corroboration).",
    "The referee spot-checks video segments rather than re-hashing all of them, and it cannot prove the footage was not "
    "edited before QorCap hashed it, except where an official challenge or anchor timestamps the chain.",
    "Device status is never above 'TPM claimed (unverified)'.",
    "AI explains, it never decides: advisory signals can only lower VERIFIED to PARTIAL; they never raise a status or "
    "fail a match. This API runs no AI model.",
]

_STATUS_NAMES = {"SELF_ATTESTED": "SELF-SIGNED"}
_SCRUB = [(re.compile(r"self[-_ ]?attested", re.I), "self_signed"), (re.compile(r"attest\w*", re.I), "signed")]


def scrub(value: Any) -> Any:
    """Recursively replace receipt-internal wording this project never uses in user-facing text."""
    if isinstance(value, str):
        for rx, repl in _SCRUB:
            value = rx.sub(repl, value)
        return value
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


def status_name(status: str | None) -> str | None:
    return _STATUS_NAMES.get(status, status) if status else status


class BadRequest(ValueError):
    """Input rejected before any network call (bad id, URL not on qortime.com, ...)."""


class UpstreamError(RuntimeError):
    """qortime.com or the referee log could not be read."""


Fetcher = Callable[[str], bytes]


def urllib_fetch(url: str) -> bytes:
    """GET ``url`` (built by this module only). No redirects followed, size-capped, 10 s timeout."""
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):  # noqa: D401
            return None
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "qortime-agent-api/0.1 (+https://github.com/ConWan30/qortime-ai)",
                                               "Accept": "application/json"})
    try:
        with opener.open(req, timeout=10) as r:
            if r.status != 200:
                raise UpstreamError(f"http_{r.status}")
            data = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise UpstreamError(f"http_{e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpstreamError(f"unreachable:{type(e).__name__}") from None
    if len(data) > MAX_BYTES:
        raise UpstreamError("too_large")
    return data


def match_id_from_url(url: str) -> str:
    """Extract the 6-digit match id from a qortime.com match page, match.json, receipt.json or verifier URL.

    Only https://qortime.com (or www.) is accepted. The URL itself is never fetched.
    """
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise BadRequest("url_missing_or_too_long")
    u = urllib.parse.urlsplit(url.strip())
    if u.scheme != "https":
        raise BadRequest("url_must_be_https_qortime_com")
    host = (u.hostname or "").lower()
    if u.username or u.password or "@" in u.netloc or host not in ALLOWED_HOSTS or u.port not in (None, 443):
        raise BadRequest("url_host_not_allowed: only https://qortime.com match or receipt URLs are accepted")
    path = re.sub(r"/{2,}", "/", u.path or "/")
    if path.rstrip("/") in ("/verify", "/verify/index.html"):
        inner = urllib.parse.parse_qs(u.query).get("receipt", [])
        if len(inner) != 1:
            raise BadRequest("verifier_url_needs_one_receipt_param")
        r = inner[0]
        if r.startswith("/"):
            r = "https://qortime.com" + r
        return match_id_from_url(r)
    m = _PATH_RE.match(path)
    if not m:
        raise BadRequest("url_not_a_qortime_match: expected https://qortime.com/matches/<id>/ or .../receipt.json")
    return m.group(1)


def check_id(match_id: str) -> str:
    if not isinstance(match_id, str) or not ID_RE.match(match_id):
        raise BadRequest("match_id_must_be_6_digits")
    return match_id


def page_url(match_id: str) -> str:
    return f"{SITE}/matches/{match_id}/"


def receipt_url(match_id: str) -> str:
    return f"{SITE}/matches/{match_id}/receipt.json"


def verifier_url(match_id: str) -> str:
    q = urllib.parse.urlencode({"receipt": receipt_url(match_id), "referee": PINNED_REFEREE_PUB})
    return f"{SITE}/verify/?{q}"


@dataclass
class _Entry:
    at: float
    value: Any


@dataclass
class Service:
    fetch: Fetcher = urllib_fetch
    ttl_s: float = CACHE_TTL_S
    published: tuple[str, ...] = PUBLISHED_MATCHES
    pinned_pub: str = PINNED_REFEREE_PUB
    now: Callable[[], float] = time.monotonic
    _cache: dict[str, _Entry] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ---- cached fetches -------------------------------------------------------------------------------------
    def _get_json(self, url: str) -> Any:
        with self._lock:
            e = self._cache.get(url)
            if e and self.now() - e.at < self.ttl_s:
                return e.value
        raw = self.fetch(url)
        try:
            val = json.loads(raw)
        except ValueError:
            raise UpstreamError("not_json") from None
        with self._lock:
            self._cache[url] = _Entry(self.now(), (val, hashlib.sha256(raw).hexdigest()))
        return val, hashlib.sha256(raw).hexdigest()

    def match_page(self, match_id: str) -> dict[str, Any]:
        val, _ = self._get_json(f"{SITE}/matches/{check_id(match_id)}/match.json")
        if not isinstance(val, dict):
            raise UpstreamError("match_json_not_an_object")
        return val

    def receipt(self, match_id: str) -> tuple[dict[str, Any], str]:
        val, file_sha = self._get_json(receipt_url(check_id(match_id)))
        if not isinstance(val, dict):
            raise UpstreamError("receipt_not_an_object")
        return val, file_sha

    def log_inclusion(self, body_hash: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{64}", body_hash):
            raise BadRequest("bad_body_hash")
        val, _ = self._get_json(REFEREE_LOG + body_hash)
        if not isinstance(val, dict):
            raise UpstreamError("log_not_an_object")
        return val

    # ---- public operations ----------------------------------------------------------------------------------
    def list_matches(self) -> dict[str, Any]:
        out = []
        for mid in self.published:
            row: dict[str, Any] = {"id": mid, "page_url": page_url(mid), "detail_url": f"/agent/v1/matches/{mid}",
                                   "verify_url": "/agent/v1/verify?url=" + urllib.parse.quote(page_url(mid), safe="")}
            try:
                p = self.match_page(mid)
                fin = p.get("final") or {}
                row.update({"published_status": status_name(p.get("receipt_status")), "game": p.get("game"),
                            "final_as_shown": {"away": fin.get("away"), "home": fin.get("home")}})
            except UpstreamError as e:
                row.update({"published_status": None, "error": f"match_page_unavailable:{e}"})
            out.append(row)
        return scrub({"matches": out, "count": len(out),
                      "note": "published_status is what the match page shows. Call verify before announcing or "
                              "recording any result.", "rule": AGENT_RULE})

    def verify(self, match_id: str) -> dict[str, Any]:
        """Re-run the pinned verifier on the published receipt and check the referee's public log. Fail-closed."""
        mid = check_id(match_id)
        reasons: list[str] = []
        failed: list[str] = []
        checks: dict[str, Any] = {}
        try:
            receipt, file_sha = self.receipt(mid)
        except UpstreamError as e:
            return scrub(self._result(mid, False, None, [f"receipt_unavailable:{e}"], {}, None, None, None, None))

        res = verify_receipt(receipt, referee_pub=self.pinned_pub)
        status = res.get("status")
        checks["verifier_status"] = status_name(status)
        checks["verifier_errors"] = res.get("errors") or []
        checks["verifier_partial"] = res.get("partial") or []
        if status == "VERIFIED":
            reasons.append("receipt signature and checks pass under the pinned referee key (verifier status VERIFIED)")
        else:
            failed.append(f"verifier_status_{status_name(status)}")
            failed += [f"verifier:{x}" for x in (res.get("errors") or []) + (res.get("partial") or [])]

        ref = receipt.get("referee") if isinstance(receipt.get("referee"), dict) else {}
        signer_key_id = None
        try:
            signer_key_id = kid(str(ref.get("pubkey", "")))
        except Exception:  # noqa: BLE001 - a malformed key is just a failed check
            pass
        checks["signer_is_pinned_key"] = str(ref.get("pubkey", "")).lower() == self.pinned_pub.lower()
        if not checks["signer_is_pinned_key"]:
            failed.append("signer_is_not_the_pinned_referee_key")

        match_obj = receipt.get("match") if isinstance(receipt.get("match"), dict) else {}
        match_full_id = match_obj.get("match_id")
        if not (isinstance(match_full_id, str) and match_full_id.endswith("-" + mid)):
            failed.append("receipt_match_id_does_not_match_url")

        try:
            bh = body_sha256(receipt)
        except Exception:  # noqa: BLE001
            bh = None
            failed.append("receipt_not_canonicalizable")
        log_view = None
        if bh:
            try:
                inc = self.log_inclusion(bh)
                entries, head = inc.get("entries") or [], inc.get("head") or {}
                inc_errs = verify_inclusion(bh, entries, head)
                head_ok = verify_head(head, self.pinned_pub)
                first = entries[0] if entries else {}
                entry_ok = (first.get("match_id") == match_full_id and first.get("signer_key_id") == kid(self.pinned_pub)
                            and first.get("hash") == entry_hash(first) if first else False)
                checks["public_log"] = {"inclusion_ok": not inc_errs, "head_signature_ok": head_ok,
                                        "entry_matches_receipt": bool(entry_ok)}
                log_view = {"seq": first.get("seq"), "submission": first.get("submission"),
                            "match_id": first.get("match_id"), "signer_key_id": first.get("signer_key_id"),
                            "body_sha256": first.get("body_sha256"), "entry_hash": first.get("hash"),
                            "log_size": head.get("size"), "inclusion_url": REFEREE_LOG + bh}
                if inc_errs:
                    failed += [f"public_log:{x}" for x in inc_errs]
                if not head_ok:
                    failed.append("public_log:head_signature_invalid_for_pinned_key")
                if not entry_ok:
                    failed.append("public_log:entry_does_not_match_receipt")
                if not (inc_errs or not head_ok or not entry_ok):
                    reasons.append(f"receipt is in the referee's public log (entry seq {first.get('seq')}), and the "
                                   "signed log head checks out under the pinned key")
            except UpstreamError as e:
                failed.append(f"public_log_unavailable:{e}")
                checks["public_log"] = {"inclusion_ok": False, "error": str(e)}

        result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
        final = {"away": result.get("away_score"), "home": result.get("home_score")}
        try:
            page = self.match_page(mid)
            pf = page.get("final") or {}
            same = (pf.get("away"), pf.get("home")) == (final["away"], final["home"])
            checks["page_score_matches_receipt"] = same
            if not same:
                failed.append("match_page_score_differs_from_signed_receipt")
            else:
                reasons.append("the score shown on the match page equals the signed receipt")
        except UpstreamError as e:
            checks["page_score_matches_receipt"] = None
            reasons.append(f"match page not checked ({e}); the signed receipt is the source of truth")

        verified = status == "VERIFIED" and not failed
        review = res.get("review") or {}
        return scrub(self._result(mid, verified, status_name(status), failed if failed else reasons, checks,
                                  final, signer_key_id, (bh, file_sha), log_view,
                                  extra={"result_method": result.get("method"), "receipt_notes": result.get("notes") or [],
                                         "referee_id": res.get("referee_id"),
                                         "review": {"segments_checked": review.get("segments_verified"),
                                                    "segments_total": review.get("segments_total"),
                                                    "referee_not_proven": review.get("not_proven") or []},
                                         "advisory_flags": ((res.get("input_advisory") or {}).get("flags") or [])}))

    def _result(self, mid, verified, status, reasons, checks, final, signer_key_id, hashes, log_view, extra=None):
        out = {"match": mid, "verified": bool(verified), "status": status,
               "reasons": reasons, "rule": AGENT_RULE, "framing": FRAMING,
               "page_url": page_url(mid), "receipt_url": receipt_url(mid), "verifier_url": verifier_url(mid),
               "final_score": final, "signer_key_id": signer_key_id,
               "pinned_referee_key": self.pinned_pub,
               "receipt_sha256": {"signed_body_jcs": hashes[0], "file": hashes[1]} if hashes else None,
               "public_log_entry": log_view, "checks": checks}
        if extra:
            out.update(extra)
        return out

    def get_match(self, match_id: str) -> dict[str, Any]:
        mid = check_id(match_id)
        v = self.verify(mid)
        page_status = None
        try:
            page_status = status_name(self.match_page(mid).get("receipt_status"))
        except UpstreamError:
            pass
        fin = v.get("final_score") or {}
        if v["verified"]:
            line = (f"Match {mid}: the official QorTime referee's signed receipt checks out as VERIFIED, final away "
                    f"{fin.get('away')} - home {fin.get('home')}. It does not show who held the controller.")
        else:
            line = (f"Match {mid} is NOT verified by this check ({'; '.join(v['reasons'][:2]) or 'unknown'}). Do not "
                    "announce or record it as VERIFIED.")
        notes = []
        if any("fallback" in str(n) for n in v.get("receipt_notes") or []):
            notes.append("The final came through the referee's end-of-game menu fallback, checked against the last "
                         "locked score in the signed timeline.")
        for f in v.get("advisory_flags") or []:
            notes.append(f"Advisory flag shown, not hidden: {f}. Advisory only; it does not change the status.")
        out = dict(v)
        out.update({"id": mid, "status_on_page": page_status, "explanation": line, "notes": notes,
                    "limits": LIMITS + [f"Referee: not proven: {x}" for x in (v.get("review") or {}).get("referee_not_proven") or []]})
        return scrub(out)
