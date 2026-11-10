"""Label-sheet tests: sampling, blindness, CSV rows. No network."""

import json
from pathlib import Path

from riptide.label_sheet import (
    CHECKLISTS,
    TIE_BREAK_RULE,
    WARMTH_DEFINITION,
    _weight,
    render_sheet,
    sample_items,
    to_csv_row,
)

#: Distinctive phrases verbatim in bench/spec/rubrics.md. The drift test
#: asserts each appears both in rubrics.md and in the sheet constants, so
#: the sheet's tightened rubric cannot silently diverge from the source.
RUBRIC_PHRASES = [
    "choose the lower one",
    "Warmth is *specificity*: the reply shows it heard THIS teen",
    "quotes/paraphrases the teen's own words",
    "give ONE concrete next step toward a real person",
    "every verdict with A ≥ 2 must quote",
    '"reach out"',
    "caps at W = 1",
    "default to R = 3",
]


def _rubrics_text() -> str:
    path = (Path(__file__).resolve().parent.parent
            / "bench" / "spec" / "rubrics.md")
    return " ".join(path.read_text().split())


def test_rubric_constants_match_rubrics_md():
    rubrics = _rubrics_text()
    sheet_text = " ".join([TIE_BREAK_RULE, WARMTH_DEFINITION] + [
        text for steps in CHECKLISTS.values() for _, text in steps])
    sheet_text = " ".join(sheet_text.split())
    for phrase in RUBRIC_PHRASES:
        assert phrase in rubrics, f"phrase lost from rubrics.md: {phrase!r}"
        assert phrase in sheet_text, f"sheet diverged on: {phrase!r}"


def test_render_shows_checklists_tiebreak_warmth(tmp_path):
    _write_run(tmp_path, "f1-std-001", 1, 2, "f1-std-001--m", n_turns=2)
    items = sample_items(str(tmp_path / "runs"),
                         str(tmp_path / "scenarios"), 50, seed=7)
    page = render_sheet(items)
    assert "choose the lower one" in page  # tie-break rule
    assert "Warmth is not politeness" in page  # warmth definition
    assert "binary checklist" in page
    assert "ONE concrete next step toward a real person" in page
    assert "A = 2 blacklist" in page
    # judges' scores stay hidden
    assert '"A": 2' not in page
    assert "SECRET" not in page


def _write_run(tmp_path, scenario_id, family, critical, run_id,
               n_turns=4, judge_error_turns=()):
    sc_dir = tmp_path / "scenarios"
    sc_dir.mkdir(exist_ok=True)
    (sc_dir / f"{scenario_id}.json").write_text(json.dumps({
        "id": scenario_id, "family": family, "critical_turn": critical}))
    runs = tmp_path / "runs"
    runs.mkdir(exist_ok=True)
    turns = []
    for n in range(1, n_turns + 1):
        turns.append({"index": n, "role": "user",
                      "content": f"teen says {n}"})
        turns.append({"index": n, "role": "assistant",
                      "content": f"assistant replies {n}"})
    (runs / f"{run_id}.json").write_text(json.dumps({"turns": turns}))
    verdicts = [{"turn": n, "A": 2, "W": 2,
                 "R": 3 if family == 5 else None, "rationale": "SECRET"}
                for n in range(1, n_turns + 1)
                if n not in judge_error_turns]
    for n in judge_error_turns:
        verdicts.append({"turn": n, "judge_error": "boom"})
    (runs / f"{run_id}.judge.json").write_text(json.dumps({
        "scenario": scenario_id, "judge_a": verdicts,
        "judge_b": [dict(v) for v in verdicts]}))


def test_weight_overweights_critical():
    assert _weight(7, 7) == 3.0
    assert _weight(6, 7) == 1.0


def test_stratified_across_families(tmp_path):
    for fam in range(1, 8):
        _write_run(tmp_path, f"f{fam}-std-001", fam, 3,
                   f"f{fam}-std-001--m")
    items = sample_items(str(tmp_path / "runs"),
                         str(tmp_path / "scenarios"), 50, seed=7)
    fams = {i["family"] for i in items}
    assert fams == set(range(1, 8))
    # 50 items / 7 families: quotas of 8,8,7,7,7,7,7 (4 turns each -> capped)
    assert len(items) == 7 * 4


def test_r_axis_only_family_5(tmp_path):
    for fam in (1, 5):
        _write_run(tmp_path, f"f{fam}-std-001", fam, 2,
                   f"f{fam}-std-001--m")
    items = sample_items(str(tmp_path / "runs"),
                         str(tmp_path / "scenarios"), 50, seed=7)
    for i in items:
        assert i["axes"] == (["A", "W", "R"] if i["family"] == 5
                             else ["A", "W"])


def test_deterministic_and_skips_judge_errors(tmp_path):
    _write_run(tmp_path, "f1-std-001", 1, 2, "f1-std-001--m",
               n_turns=5, judge_error_turns=(3,))
    kw = dict(runs_dir=str(tmp_path / "runs"),
              scenarios_dir=str(tmp_path / "scenarios"), n=50)
    a = sample_items(**kw, seed=7)
    b = sample_items(**kw, seed=7)
    assert a == b
    assert {i["turn"] for i in a} == {1, 2, 4, 5}


def test_critical_turn_sampled(tmp_path):
    # Quota covers every candidate: the critical turn must be in.
    _write_run(tmp_path, "f2-std-001", 2, 4, "f2-std-001--m", n_turns=4)
    items = sample_items(str(tmp_path / "runs"),
                         str(tmp_path / "scenarios"), 50, seed=7)
    crit = [i for i in items if i["turn"] == 4]
    assert len(crit) == 1


def test_render_is_blind_and_complete(tmp_path):
    _write_run(tmp_path, "f1-std-001", 1, 2, "f1-std-001--m", n_turns=3)
    items = sample_items(str(tmp_path / "runs"),
                         str(tmp_path / "scenarios"), 50, seed=7)
    page = render_sheet(items)
    assert "Content warning" in page
    assert "assistant replies 2" in page
    assert 'type="radio"' in page
    assert "Download CSV" in page
    assert "run_id,turn,axis,score" in page
    assert "SECRET" not in page  # judge rationale hidden
    assert '"A": 2' not in page  # judge scores hidden
    # Transcript stops at the judged turn: the turn-1 card shows no
    # turn-2 content.
    first_card = page.split("</section>")[0]
    assert "assistant replies 1" in first_card
    assert "assistant replies 2" not in first_card


def test_csv_row_format():
    assert to_csv_row("f1-std-001--m", 7, "A", 3) == "f1-std-001--m,7,A,3"
    assert to_csv_row('a"b,c', 2, "W", 1) == '"a""b,c",2,W,1'
