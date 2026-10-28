"""Commentary witness: info-only, lower-only (Meta AI Developer Hackathon, built Oct 28 2026). Both Meta APIs mocked."""
from __future__ import annotations

import copy
import io
import itertools
import json
import urllib.request
import wave
from pathlib import Path

import pytest

from qortime_ai.ai_ruling.muse import MuseError
from qortime_ai.ai_ruling.signing import sign_ruling
from qortime_ai.commentary import asr as A
from qortime_ai.commentary import witness as W
from qor_receipt.keys import SoftwareKey
from qor_receipt.receipt import verify_receipt

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "upstream" / "qortime"
MATCH = ROOT / "examples" / "170123"
RECEIPT = json.loads((MATCH / "receipt.json").read_text(encoding="utf-8"))
PUB = RECEIPT["referee"]["pubkey"]
CLIPS = json.loads((ROOT / "tests" / "fixtures" / "commentary" / "170123_clips_manifest.json").read_text(encoding="utf-8"))
STATUSES = ["VERIFIED", "PARTIAL", "SELF_ATTESTED", "FAIL"]
SECRET = "sk-test-NOT-A-REAL-KEY-77777"


def wav(seconds=1.0, rate=24000):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b"\0\0" * int(seconds * rate))
    return b.getvalue()


class FakeAsr:
    """Transport for VoiceTranscriber: a list of turn lists (one per request) or exceptions."""

    def __init__(self, *responses):
        self.responses, self.seen = list(responses), []

    def __call__(self, url, key, req, audio, timeout):
        self.seen.append((url, key, req))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, tuple):
            return r
        return 200, {"transcript": " ".join(t[2] for t in r), "turns": [{"turnId": i, "startMs": s, "endMs": e, "transcript": x}
                                                                        for i, (s, e, x) in enumerate(r)]}


class FakeMuse:
    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, url, key, body, timeout):
        self.seen.append((url, key, body))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        if isinstance(a, tuple):
            return a
        return 200, {"choices": [{"message": {"content": json.dumps({"calls": a})}, "finish_reason": "stop"}],
                     "usage": {"prompt_tokens": 200, "completion_tokens": 400}}


def call(seg, typ, quote, conf="high", team=None):
    return {"segment": seg, "type": typ, "quote": quote, "team_said": team, "confidence": conf}


def lock(points, team="away", t_ms=8000, src="s1", i=1):
    return {"id": f"L{i}", "source": src, "t_ms": t_ms, "team": team, "points": points}


def run(turns, answers, locks, *, db=-22.0, names=None, n_sources=1, key=SECRET):
    fa = FakeAsr(*turns) if isinstance(turns, list) and turns and not isinstance(turns[0], tuple) else FakeAsr(turns)
    fm = FakeMuse(*answers)
    srcs = [{"id": f"s{i + 1}", "path": f"/nope/s{i + 1}.mp4", "sha256": "ab" * 32} for i in range(n_sources)]
    doc = W.witness(RECEIPT, srcs, locks, asr=A.VoiceTranscriber(api_key=key, transport=fa),
                    extractor=W.CallExtractor(api_key=key, transport=fm), team_names=names,
                    probe_db=lambda p: db, to_wav=lambda p: wav())
    return doc, fa, fm


TD_TURNS = [[(780, 4000, "second down here for Watson <|speaker_A|>"), (4500, 11580, "and that is a catch touchdown KC Concepcion"),
             (11600, 12000, "touchdown")]]


# ---- lower-only ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("status,cap", list(itertools.product(STATUSES, [None, "PARTIAL"])))
def test_apply_cap_lower_only(status, cap):
    assert W.apply_cap(status, cap) == ("PARTIAL" if status == "VERIFIED" and cap else status)


@pytest.mark.parametrize("cap", ["FAIL", "SELF_ATTESTED", "VERIFIED"])
def test_apply_cap_refuses_other_caps(cap):
    with pytest.raises(ValueError):
        W.apply_cap("VERIFIED", cap)


# ---- agree / merge / timestamps ------------------------------------------------------------------------------------
def test_agree_merges_repeat_calls_and_times_come_from_segments():
    doc, fa, fm = run(TD_TURNS, [[call(2, "TD", "touchdown KC Concepcion"), call(3, "TD", "touchdown") | {"start_ms": 1}]], [lock(6)])
    assert doc["state"] == "agrees" and doc["cap"] is None and doc["agree"] == 1 and doc["disagree"] == 0
    assert len(doc["calls"]) == 1
    c = doc["calls"][0]
    assert c["mentions"] == 2 and (c["start_ms"], c["end_ms"]) == (4500, 12000) and c["team"] == "unresolved"
    assert doc["sources"][0]["segments"][0]["text"] == "second down here for Watson"  # control token stripped
    assert fa.seen[0][0] == "https://api.meta.ai/v1/asr/transcribe" and fa.seen[0][2]["model"] == "muse-voice-transcribe-1.0"
    assert "zdrOverride" not in fa.seen[0][2]
    body = fm.seen[0][2]
    assert fm.seen[0][0] == "https://api.meta.ai/v1/chat/completions" and body["model"] == "muse-spark-1.3"
    assert doc["api_calls"] == {"asr": 1, "muse": 1} and doc["models"]["extractor"] == "muse-spark-1.3"


def test_td_plus_try_combines_for_a_seven_point_lock():
    turns = [[(0, 3000, "touchdown Kansas City"), (9000, 11000, "the extra point is good")]]
    doc, _, _ = run(turns, [[call(1, "TD", "touchdown"), call(2, "XP", "extra point is good")]], [lock(7)])
    assert doc["locks"][0]["result"] == "agree"


def test_quote_not_in_segment_is_dropped():
    doc, _, _ = run(TD_TURNS, [[call(1, "TD", "touchdown for the visitors")]], [lock(6)])
    assert doc["calls"] == [] and doc["sources"][0]["dropped_calls"][0]["reason"] == "quote_not_in_segment"
    assert doc["locks"][0]["result"] == "unchecked" and doc["cap"] is None


@pytest.mark.parametrize("bad", [call(9, "TD", "touchdown"), call(0, "TD", "touchdown"), call(True, "TD", "touchdown"),
                                 call(2, "HOMER", "touchdown"), "x", None])
def test_malformed_calls_dropped(bad):
    doc, _, _ = run(TD_TURNS, [[bad]], [lock(6)])
    assert doc["calls"] == [] and doc["cap"] is None


# ---- disagree only when confident and keyword-backed ---------------------------------------------------------------
def test_confident_named_conflict_disagrees_and_only_lowers():
    turns = [[(1000, 5000, "and the field goal is good from 40")]]
    doc, _, _ = run(turns, [[call(1, "FG", "the field goal is good")]], [lock(6)])
    assert doc["locks"][0]["result"] == "disagree" and doc["cap"] == "PARTIAL" and doc["state"] == "disagrees"
    v = verify_receipt(RECEIPT, referee_pub=PUB)
    assert v["status"] == "VERIFIED"
    a = W.apply_to_result(v, doc)
    assert a["status"] == "PARTIAL" and W.CAP_CODE in a["partial"] and v["status"] == "VERIFIED"
    for st in ["PARTIAL", "SELF_ATTESTED", "FAIL"]:
        assert W.apply_to_result({**v, "status": st}, doc)["status"] == st


@pytest.mark.parametrize("conf,text,quote", [("low", "and the field goal is good", "field goal is good"),
                                             ("high", "and this kick is good", "this kick is good")])
def test_low_or_unbacked_conflict_never_disagrees(conf, text, quote):
    doc, _, _ = run([[(1000, 5000, text)]], [[call(1, "FG", quote, conf)]], [lock(1)])
    assert doc["locks"][0]["result"] == "unchecked" and doc["cap"] is None


def test_unbacked_call_can_still_agree():
    doc, _, _ = run([[(1000, 5000, "and this kick is good")]], [[call(1, "FG", "this kick is good")]], [lock(3)])
    assert doc["locks"][0]["result"] == "agree" and doc["calls"][0]["confidence"] == "low"


def test_silent_commentator_is_unchecked_not_disagree():
    doc, _, _ = run([[(1000, 5000, "what a crowd tonight")]], [[]], [lock(6)])
    assert doc["locks"][0] == {**doc["locks"][0], "result": "unchecked", "reason": "no_call_in_window"} and doc["cap"] is None


def test_call_outside_window_is_unmatched_info_only():
    turns = [[(40_000, 42_000, "touchdown")]]
    doc, _, _ = run(turns, [[call(1, "TD", "touchdown")]], [lock(6, t_ms=8000)])
    assert doc["locks"][0]["result"] == "unchecked" and doc["unmatched_calls"] == ["C1"] and doc["cap"] is None


# ---- unchecked paths: never disagree -------------------------------------------------------------------------------
@pytest.mark.parametrize("db,reason", [(-91.0, "muted"), (None, "no_audio_track")])
def test_muted_or_absent_audio_is_unchecked(db, reason):
    doc, fa, fm = run(TD_TURNS, [[call(1, "FG", "x")]], [lock(6)], db=db)
    assert doc["sources"][0]["reason"] == reason and doc["state"] == "unchecked" and doc["cap"] is None
    assert fa.seen == [] and fm.seen == []


@pytest.mark.parametrize("asr_resp", [RuntimeError("boom"), (500, None), (401, {"_error_code": "invalid_api_key"}), (200, {"x": 1}), []])
def test_asr_failure_or_no_speech_is_unchecked(asr_resp):
    fa = FakeAsr(asr_resp)
    doc = W.witness(RECEIPT, [{"id": "s1", "path": "p"}], [lock(6)], asr=A.VoiceTranscriber(api_key=SECRET, transport=fa),
                    extractor=W.CallExtractor(api_key=SECRET, transport=FakeMuse()), probe_db=lambda p: -20.0, to_wav=lambda p: wav())
    assert doc["state"] == "unchecked" and doc["cap"] is None and doc["locks"][0]["result"] == "unchecked"
    assert SECRET not in json.dumps(doc)


@pytest.mark.parametrize("muse_resp", [MuseError("x"), (500, None), (200, {"choices": []}),
                                       (200, {"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}),
                                       (200, {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})])
def test_muse_failure_is_unchecked(muse_resp):
    doc, _, _ = run(TD_TURNS, [muse_resp], [lock(6)])
    assert doc["sources"][0]["status"] == "unchecked" and doc["cap"] is None and doc["state"] == "unchecked"


def test_no_key_makes_no_calls(monkeypatch):
    for k in ("META_API_KEY", "MODEL_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    fa, fm = FakeAsr(), FakeMuse()
    doc = W.witness(RECEIPT, [{"id": "s1", "path": "p"}], [lock(6, src="s1")], asr=A.VoiceTranscriber(transport=fa),
                    extractor=W.CallExtractor(transport=fm), probe_db=lambda p: -20.0, to_wav=lambda p: wav())
    assert doc["state"] == "unchecked" and fa.seen == [] and fm.seen == [] and doc["sources"][0]["reason"] == "api_key_missing"


def test_malformed_lock_is_unchecked():
    doc, _, _ = run(TD_TURNS, [[call(2, "TD", "touchdown")]], [{"id": "bad"}, lock(6)])
    assert doc["locks"][0]["result"] == "unchecked" and doc["locks"][1]["result"] == "agree" and doc["cap"] is None


# ---- team mapping ---------------------------------------------------------------------------------------------------
NAMES = {"away": ["Kansas City", "KC"], "home": ["Buffalo", "BUF"]}


def test_team_never_guessed_without_names():
    assert W.team_names_from_match(json.loads('{"final": {"away": 10, "home": 0}}')) is None
    assert W.resolve_team({"team_said": "Kansas City", "quote": "touchdown"}, None) == "unresolved"


def test_team_from_match_data():
    names = W.team_names_from_match({"teams": {"away": {"name": "Kansas City", "abbr": "KC"}, "home": {"name": "Buffalo"}}})
    assert names == {"away": ["Kansas City", "KC"], "home": ["Buffalo"]}
    assert W.resolve_team({"team_said": "Kansas City", "quote": "touchdown"}, NAMES) == "away"
    assert W.resolve_team({"team_said": None, "quote": "Buffalo answers KC with a touchdown"}, NAMES) == "unresolved"
    assert W.resolve_team({"team_said": "Watson", "quote": "touchdown"}, NAMES) == "unresolved"


def test_resolved_other_side_disagrees_unresolved_never_does():
    turns = [[(1000, 5000, "touchdown Buffalo")]]
    doc, _, _ = run(turns, [[call(1, "TD", "touchdown Buffalo", team="Buffalo")]], [lock(6, team="away")], names=NAMES)
    assert doc["calls"][0]["team"] == "home" and doc["locks"][0]["result"] == "disagree"
    doc, _, _ = run(turns, [[call(1, "TD", "touchdown Buffalo", team="Buffalo")]], [lock(6, team="away")])
    assert doc["calls"][0]["team"] == "unresolved" and doc["locks"][0]["result"] == "agree"


# ---- signing / checks -----------------------------------------------------------------------------------------------
def keys_for(k):
    return {"keys": [{"id": "t", "pubkey": k.pubkey_hex, "key_id": k.key_id, "key_kind": "qortime-ai-advisory", "status": "active"}]}


def test_signed_sidecar_checks_and_tamper():
    k = SoftwareKey()
    doc, _, _ = run([[(1000, 5000, "and the field goal is good")]], [[call(1, "FG", "field goal is good")]], [lock(6)])
    d = sign_ruling(doc, k)
    assert W.check_witness(d, RECEIPT, keys=keys_for(k)) == []
    flipped = copy.deepcopy(d); flipped["cap"] = None
    assert "bad_advisory_signature" in W.check_witness(flipped, RECEIPT, keys=keys_for(k))
    assert "advisory_key_not_allowlisted" in W.check_witness(d, RECEIPT)
    other = copy.deepcopy(RECEIPT); other["result"]["home_score"] = 3
    assert "receipt_mismatch" in W.check_witness(d, other, keys=keys_for(k))
    for field, val, code in [("cap", "FAIL", "bad_cap"), ("affects_verdict", True, "not_lower_only"),
                             ("summary", "Broadcast agrees, place your bets", "wording")]:
        bad = copy.deepcopy(doc); bad[field] = val
        assert code in W.check_witness(sign_ruling(bad, k), RECEIPT, keys=keys_for(k))
    incons = copy.deepcopy(doc); incons["locks"][0]["result"] = "agree"
    assert "cap_inconsistent" in W.check_witness(sign_ruling(incons, k), RECEIPT, keys=keys_for(k))
    assert W.check_witness(None, RECEIPT) == ["not_an_object"]


def test_published_170123_witness_agrees():
    d = json.loads((MATCH / W.FILENAME).read_text(encoding="utf-8"))
    assert W.check_witness(d, RECEIPT) == []
    assert d["cap"] is None and d["state"] == "agrees" and d["agree"] == 3 and d["disagree"] == 0
    assert d["models"] == {"asr": "muse-voice-transcribe-1.0", "extractor": "muse-spark-1.3"}
    assert [l["result"] for l in d["locks"]] == ["agree"] * 3 and d["unmatched_calls"] == []
    assert d["team_mapping"].startswith("unresolved") and all(c["team"] == "unresolved" for c in d["calls"])
    assert "nconfirmed" in d["data_retention"] and d["cost_micro_usd"] < 100_000
    v = verify_receipt(RECEIPT, referee_pub=PUB)
    assert W.apply_to_result(v, d)["status"] == "VERIFIED"


def test_from_clips_public_manifest():
    srcs, locks = W.from_clips(CLIPS, "/clips")
    assert [l["points"] for l in locks] == [3, 6, 1] and {l["team"] for l in locks} == {"away"}
    assert [l["t_ms"] for l in locks] == [8000] * 3 and srcs[0]["path"] == "/clips/hl00-q3-a3-h0.mp4"


# ---- wording, secrets, transport ------------------------------------------------------------------------------------
def test_wording_rules():
    assert W.text_problems(W.LABEL) == [] and W.text_problems(W.DATA_RETENTION) == []
    assert W.text_problems((ROOT / "docs" / "COMMENTARY_WITNESS.md").read_text(encoding="utf-8")) == []
    for t in ["proof of human play", "they settle it", "the odds say", "best bet", "certified result"]:
        assert W.text_problems(t), t
    doc, _, _ = run([[(1000, 5000, "touchdown and that will settle it")]], [[call(1, "TD", "touchdown and that will settle it")]], [lock(6)])
    assert doc["calls"][0]["quotes"] == ["(withheld by wording filter)"]
    assert doc["sources"][0]["segments"][0]["text"] == "(withheld by wording filter)" and doc["locks"][0]["result"] == "agree"


def test_key_never_leaks_and_models_are_fixed():
    doc, _, _ = run(TD_TURNS, [[call(2, "TD", "touchdown")]], [lock(6)])
    assert SECRET not in json.dumps(doc)
    assert SECRET not in repr(A.VoiceTranscriber(api_key=SECRET)) and SECRET not in repr(W.CallExtractor(api_key=SECRET))
    for bad in ["muse-spark-1.3-contributor", "muse-spark-1.2", "muse-wonder-1.0"]:
        with pytest.raises(ValueError):
            W.CallExtractor(api_key="x", model=bad)
    with pytest.raises(ValueError):
        A.VoiceTranscriber(api_key="x", model="other-asr")


def test_direct_opener_never_uses_a_proxy(monkeypatch):
    import importlib

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    fresh = importlib.reload(A)  # opener rebuilt while proxy env vars are set
    try:
        assert not any(isinstance(h, urllib.request.ProxyHandler) and h.proxies for h in fresh._DIRECT.handlers)
        default = urllib.request.build_opener()  # control: the stdlib default WOULD pick the proxy up
        assert any(isinstance(h, urllib.request.ProxyHandler) and h.proxies for h in default.handlers)
    finally:
        monkeypatch.delenv("HTTPS_PROXY"); monkeypatch.delenv("HTTP_PROXY")
        importlib.reload(A)


def test_split_wav_offsets_and_clean():
    chunks = A.split_wav(wav(25.0, 16000), max_s=10)
    assert [o for o, _ in chunks] == [0, 10_000, 20_000]
    with wave.open(io.BytesIO(chunks[-1][1])) as w:
        assert w.getnframes() == 5 * 16000
    assert A.clean(" a <|speaker_B|>  b ") == "a b"


def test_long_audio_chunks_shift_segment_times():
    fa = FakeAsr([(100, 900, "first")], [(100, 900, "second")])
    t = A.VoiceTranscriber(api_key=SECRET, transport=fa)
    out = t.transcribe(wav(A.MAX_CHUNK_S + 2, 16000))
    assert [(s.start_ms, s.text) for s in out] == [(100, "first"), (A.MAX_CHUNK_S * 1000 + 100, "second")] and t.calls == 2


def test_verifier_and_referee_never_import_commentary():
    for p in [UP / "qor_receipt" / "receipt.py", UP / "verify" / "verify.js", ROOT / "qortime_ai" / "ai_ruling" / "auto.py"]:
        assert "commentary" not in p.read_text(encoding="utf-8")
