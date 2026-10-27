"""Red-Team the Referee (built Oct 27 2026, in the event window). Offline: replays cached Muse fixtures."""
import copy
import json

import pytest

from qortime_ai.redteam import harness
from qortime_ai.redteam.citations import check, facts, sentences
from qortime_ai.redteam.explain import audit
from qortime_ai.redteam.mutations import MutationError, apply_ops
from qortime_ai.redteam.wording import BANNED_TERMS, banned_hits

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def sb():
    s = harness.Sandbox()
    yield s
    s.close()


@pytest.fixture(scope="module")
def report():
    return harness.run()


def test_fixture_has_enough_model_attacks():
    doc = harness.load_attacks()
    assert len(doc["attacks"]) >= 20 and doc["generator"]["model"].startswith("muse-wonder")
    assert len({a["id"] for a in doc["attacks"]}) == len(doc["attacks"])


def test_every_attack_rejected(report):
    assert report["baseline"]["status"] == "VERIFIED"
    assert report["accepted"] == 0, [r for r in report["rows"] if r["accepted"]]
    assert report["attacks_tested"] >= 20 and report["invalid"] == 0
    for r in report["rows"]:
        assert r["outcome"] in ("rejected", "no_tamper_identical_to_honest"), r
        if r["outcome"] == "rejected":
            assert r["status"] != "VERIFIED" and r["reasons"], r
    assert report["headline"] == f"Outside attacker: {report['attacks_tested']} attacks · 0 accepted"


def test_harness_reproducible_with_fresh_keys(report):
    assert harness.outcome_table(harness.run()) == harness.outcome_table(report)


def test_harness_would_report_an_accepted_attack(sb, monkeypatch):
    # If the verifier ever said VERIFIED for tampered content, the harness must count it, not hide it.
    monkeypatch.setattr(sb, "verify", lambda r, pin="honest": {"status": "VERIFIED", "errors": [], "partial": []})
    row = harness.run_attack(sb, {"id": "x", "ops": [{"op": "set", "path": "result.home_score", "value": 99}]})
    assert row["accepted"] is True and row["outcome"] == "ACCEPTED"


def test_mutation_dsl(sb):
    before = copy.deepcopy(sb.receipt)
    r = apply_ops(sb.receipt, [{"op": "shift_int", "path": "match.started_ms", "by": -5}], sb.donor)
    assert r["match"]["started_ms"] == before["match"]["started_ms"] - 5 and sb.receipt == before
    with pytest.raises(MutationError):
        apply_ops(sb.receipt, [{"op": "delete", "path": "nope.x"}], sb.donor)
    with pytest.raises(MutationError):
        apply_ops(sb.receipt, [{"op": "rm -rf"}], sb.donor)


def test_cached_explanations_pass_checks(sb):
    rows = audit(sb)
    assert {r["case"]: r["verdict"] for r in rows} == {"honest": "VERIFIED", "score_edit_unsigned": "FAIL"}
    assert all(r["shown"] and not r["problems"] for r in rows), rows


def _fx(sb):
    return facts(sb.receipt, sb.verify(sb.receipt))


def test_citation_checker_catches_bad_and_missing(sb):
    fx = _fx(sb)
    assert check("The referee returned VERIFIED [verdict]. Home scored 24 [result.home_score].", fx) == []
    probs = lambda t: [p["problem"] for p in check(t, fx)]
    assert probs("The referee returned VERIFIED.") == ["missing_citation"]
    assert probs("The referee returned VERIFIED [verdict.status].") == ["unknown_field:verdict.status",
                                                                         "status_without_verdict_citation"]
    assert "number_not_in_cited_fields:31" in probs("Home scored 31 [result.home_score].")
    assert "number_not_in_cited_fields:24" in probs("Home scored 24 [result.away_score].")
    assert "status_mismatch:FAIL" in probs("The referee returned FAIL [verdict].")
    assert "status_without_verdict_citation" in probs("The match is VERIFIED [result.home_score].")
    assert "winner_mismatch:away" in probs("Away won the game [result.winner].")
    assert "winner_without_citation" in probs("Home won the game [verdict].")
    # Dots inside citations do not split sentences; trailing citations attach to the previous sentence.
    assert sentences("Home scored 24. [result.home_score]") == [("Home scored 24.", ["result.home_score"])]


def test_claims_verified_on_non_verified(sb):
    bad = copy.deepcopy(sb.receipt); bad["result"]["home_score"] = 31
    fx = facts(bad, sb.verify(bad))
    assert "claims_verified" in [p["problem"] for p in check("The score was verified by the referee [verdict].", fx)]


@pytest.mark.parametrize("term", list(BANNED_TERMS) + ["ATTESTED", "Hardware Verified", "single-attested",
                                                       "certify", "guarantee", "cheat-free", "tamper-proof"])
def test_banned_word_filter(term, sb):
    assert banned_hits(f"This match is {term}.")
    assert any(p["problem"].startswith("banned_word") for p in check(f"This match is {term} [verdict].", _fx(sb)))


def test_field_name_may_be_cited_but_not_written():
    assert banned_hits("The tier is listed [trust_tier].") == []
    assert banned_hits("The tier is single-attested [trust_tier].") == ["attested"]


def test_fixtures_contain_no_secrets_or_gamertags():
    for name in ("wonder_attacks.json", "spark_explanations.json"):
        t = (harness.FIXTURES / name).read_text(encoding="utf-8")
        assert "Bearer" not in t and "api_key" not in t.lower() and "sk-" not in t
        assert "local:player" not in t and "170123" not in t


def test_cli_writes_report(tmp_path):
    from qortime_ai.redteam.__main__ import main
    assert main(["--out", str(tmp_path)]) == 0
    rep = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert rep["accepted"] == 0 and (tmp_path / "summary.md").read_text(encoding="utf-8").startswith("# Red-Team")


def test_insider_pass_reported_honestly(report):
    rows = {r["id"]: r["insider"] for r in report["rows"]}
    assert report["insider_tested"] >= 20 and report["insider_accepted"] == len(report["insider_accepted_ids"])
    assert report["headline_insider"] == (f"Insider with signing keys: {report['insider_tested']} attacks · "
                                          f"{report['insider_accepted']} accepted")
    # A key holder can sign a score edit: expected, labelled, not hidden.
    assert rows["score_edit_unsigned"]["accepted"] and rows["score_edit_unsigned"]["label"] == harness.INSIDER_ACCEPTED_LABEL
    # Inner checks still stop these on their own, after the envelope is re-signed with the TEST keys.
    expect = {"winner_flip_unsigned": "winner_inconsistent", "trust_tier_upgrade": "trust_tier_claim_wrong",
              "score_type_confusion": "score_not_nonneg_int", "drop_first_checkpoint": "home:cp[*]:seq_gap",
              "checkpoint_hash_edit": "home:cp[*]:hash_mismatch", "signal_laundering_delete": "away:motion_signal_missing",
              "timestamp_shift_start": "away:cp[*]:gap_too_long", "drop_failed_challenge": ":challenge_missing:kickoff"}
    for k, reason in expect.items():
        assert not rows[k]["accepted"] and any(x.endswith(reason) for x in rows[k]["reasons"]), (k, rows[k])
    for r in rows.values():
        if r["accepted"]:
            assert r["label"] == harness.INSIDER_ACCEPTED_LABEL and r["note"]


def test_insider_sign_uses_only_test_keys(sb):
    r = harness.insider_sign(sb, sb.receipt)
    assert sb.verify(r)["status"] == "VERIFIED" and r["referee"]["pubkey"] == sb.referee.pubkey_hex
