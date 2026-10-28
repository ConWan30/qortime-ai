"""Meta Muse Voice Transcribe client (``muse-voice-transcribe-1.0``, ``POST /v1/asr/transcribe``). Standard library only.

* Direct to ``https://api.meta.ai/v1``: the opener has an empty ProxyHandler, so no HTTP(S)_PROXY is ever used.
* Key from env ``META_API_KEY`` / ``MODEL_API_KEY`` (via ``muse.api_key_from_env``). Never logged, never in a sidecar,
  never in an exception message.
* ``zdrOverride`` is left unset (API default). Data retention for this endpoint is UNCONFIRMED; see the doc.
* Timestamps are speech-segment (turn) start/end only. The API has no word-level timestamps, so nothing finer is trusted.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable

from qortime_ai.ai_ruling.muse import BASE_URL, MuseError, _V6FirstHTTPSHandler, _error_code, api_key_from_env

ASR_MODEL = "muse-voice-transcribe-1.0"
MAX_CHUNK_S = 540            # API limit is 10 min / 32 MB per request; 9 min chunks leave headroom
_SPECIAL = re.compile(r"<\|[^|>]{0,40}\|>")
# Direct opener: empty ProxyHandler = never relay through a proxy; IPv6-first like muse.py.
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}), _V6FirstHTTPSHandler())


class AsrError(MuseError):
    """Transcription failed. Never contains the key."""


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    text: str


def clean(text: str) -> str:
    """Drop model control tokens such as ``<|speaker_A|>`` and collapse whitespace."""
    return " ".join(_SPECIAL.sub(" ", text or "").split())


def _multipart(req: dict, wav: bytes) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    head = (f"--{b}\r\nContent-Disposition: form-data; name=\"request\"\r\nContent-Type: application/json\r\n\r\n"
            f"{json.dumps(req)}\r\n--{b}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"audio.wav\"\r\n"
            "Content-Type: audio/wav\r\n\r\n").encode()
    return head + wav + f"\r\n--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def _urllib_transport(url: str, key: str, req: dict, wav: bytes, timeout_s: float) -> tuple[int, Any]:
    body, ctype = _multipart(req, wav)
    r = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Accept": "application/json", "Content-Type": ctype})
    try:
        with _DIRECT.open(r, timeout=timeout_s) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, _error_code(e)
    except Exception as e:  # noqa: BLE001  any network failure = no transcript
        raise AsrError(f"network:{type(e).__name__}") from None


def split_wav(wav: bytes, max_s: int = MAX_CHUNK_S) -> list[tuple[int, bytes]]:
    """[(offset_ms, wav_bytes)] chunks of at most ``max_s`` seconds (same format as the input)."""
    with wave.open(BytesIO(wav)) as w:
        params, rate, n = w.getparams(), w.getframerate(), w.getnframes()
        per = max(1, int(max_s * rate))
        out = []
        for start in range(0, max(n, 1), per):
            w.setpos(start)
            frames = w.readframes(min(per, n - start))
            buf = BytesIO()
            with wave.open(buf, "wb") as o:
                o.setparams(params)
                o.writeframes(frames)
            out.append((int(start * 1000 / rate), buf.getvalue()))
        return out


class VoiceTranscriber:
    def __init__(self, *, api_key: str | None = None, model: str = ASR_MODEL, base_url: str = BASE_URL,
                 timeout_s: float = 180.0, transport: Callable | None = None) -> None:
        if model != ASR_MODEL:
            raise ValueError("only muse-voice-transcribe-1.0 is used here")
        self._key = api_key if api_key is not None else api_key_from_env()
        self.model, self.base_url, self.timeout_s = model, base_url.rstrip("/"), timeout_s
        self._transport = transport or _urllib_transport
        self.calls = 0

    def __repr__(self) -> str:
        return f"VoiceTranscriber(model={self.model!r}, key={'set' if self._key else 'missing'})"

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    def transcribe(self, wav: bytes) -> list[Segment]:
        """Speech segments for one WAV (mono 16-bit PCM, 16/24 kHz), chunked under the API limit. Raises AsrError."""
        if not self._key:
            raise AsrError("api_key_missing")
        req = {"model": self.model, "audioEncoding": "WAV", "mode": "ENDPOINTING", "languageBias": ["English"]}
        segs: list[Segment] = []
        for off, chunk in split_wav(wav):
            self.calls += 1
            status, d = self._transport(f"{self.base_url}/asr/transcribe", self._key, req, chunk, self.timeout_s)
            if status != 200 or not isinstance(d, dict) or "_error_code" in d:
                code = d.get("_error_code") if isinstance(d, dict) else None
                raise AsrError(f"http_{status}" + (f":{code}" if code else ""))
            turns = d.get("turns")
            if not isinstance(turns, list):
                raise AsrError("malformed_response")
            for t in turns:
                if not isinstance(t, dict):
                    continue
                text = clean(str(t.get("transcript") or ""))
                s, e = t.get("startMs"), t.get("endMs")
                if text and isinstance(s, int) and isinstance(e, int) and e >= s:
                    segs.append(Segment(off + s, off + e, text))
        return segs


__all__ = ["ASR_MODEL", "AsrError", "Segment", "VoiceTranscriber", "clean", "split_wav"]
