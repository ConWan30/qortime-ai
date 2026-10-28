"""The numbers in docs/SCORE_BENCH.md come from examples/score_bench/muse_spark_bench.json (built Oct 28 2026, in-window)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = json.loads((ROOT / "examples/score_bench/muse_spark_bench.json").read_text())


def _correct(r):
    return r["muse_confident"] and (r["muse_away"], r["muse_home"]) == (r["truth_away"], r["truth_home"])


def _counts(rows):
    vis = [r for r in rows if r["score_visible"]]
    none = [r for r in rows if not r["score_visible"]]
    return {
        "visible": len(vis),
        "correct": sum(_correct(r) for r in vis),
        "no_score": len(none),
        "unconfident_on_no_score": sum(not r["muse_confident"] for r in none),
        "traps": sum(r["stats_overlay_trap"] for r in none),
        "confident_but_wrong": sum(r["muse_confident"] and not _correct(r) for r in rows),
    }


def test_dev_bench_is_73_of_73():
    dev = [r for r in BENCH["frames"] if r["group"] != "excluded_game"]
    assert _counts(dev) == {"visible": 73, "correct": 73, "no_score": 18, "unconfident_on_no_score": 18,
                            "traps": 8, "confident_but_wrong": 0}


def test_full_run_and_labels():
    assert len(BENCH["frames"]) == 134
    c = _counts(BENCH["frames"])
    assert (c["visible"], c["correct"], c["confident_but_wrong"]) == (111, 111, 0)
    assert BENCH["held_out"] is False
    assert BENCH["model"] == "muse-spark-1.3"
    assert "never trained or fine-tuned" in BENCH["note"]


def test_doc_states_it_plainly():
    doc = (ROOT / "docs/SCORE_BENCH.md").read_text()
    assert "not a held-out test" in doc
    assert "never trained or fine-tuned Muse" in doc
    assert "73" in doc and "2 of 2" in doc
