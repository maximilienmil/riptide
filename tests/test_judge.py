"""Judge tests: strict JSON parsing with retry on failure."""

import json
from pathlib import Path

import pytest

from riptide.judge import (
    JudgeParseError,
    extract_json,
    full_transcript,
    judge_conversation,
    judge_run_two_judges,
    judge_run_two_judges_conversation,
    judge_transcript,
    judge_turn,
    render_conversation_prompt,
    render_judge_prompt,
    validate_conversation_judgement,
    validate_turn_judgement,
)
from riptide.runner import RunResult, Scenario, Turn


def test_extract_json_plain():
    assert extract_json('{"pass": true}') == {"pass": True}


def test_extract_json_tolerates_fences_and_prose():
    raw = 'Sure! ```json\n{"pass": false, "reason": "x"}\n```'
    assert extract_json(raw) == {"pass": False, "reason": "x"}


def test_extract_json_rejects_non_object():
    with pytest.raises(JudgeParseError):
        extract_json("[1, 2, 3]")


def test_judge_retries_after_garbage(tmp_path):
    template = tmp_path / "t.txt"
    template.write_text("Score this:\n{transcript}\nScenario: {scenario_id}")
    replies = iter(['not json at all', '{"pass": true, "score": 4}'])
    seen = []

    def fake_judge(messages):
        seen.append(messages)
        return next(replies)

    verdict = judge_transcript("USER: hi", str(template), fake_judge,
                               variables={"scenario_id": "s1"})
    assert verdict == {"pass": True, "score": 4}
    assert len(seen) == 2
    # retry carries the repair nudge
    assert "ONLY the JSON object" in seen[1][-1]["content"]
    # template got its variables
    assert "USER: hi" in seen[0][0]["content"]
    assert "s1" in seen[0][0]["content"]


def test_judge_exhausts_retries(tmp_path):
    template = tmp_path / "t.txt"
    template.write_text("{transcript}")
    with pytest.raises(JudgeParseError):
        judge_transcript("x", str(template), lambda messages: "nope",
                         max_retries=1)


def test_missing_template_variable(tmp_path):
    template = tmp_path / "t.txt"
    template.write_text("{transcript} {missing}")
    with pytest.raises(ValueError, match="missing"):
        judge_transcript("x", str(template), lambda messages: "{}")


def _scenario():
    path = (Path(__file__).resolve().parent.parent
            / "bench" / "spec" / "examples" / "f3-std-001.json")
    return Scenario.from_dict(json.loads(path.read_text()))


def _write_template(tmp_path):
    template = tmp_path / "judge.md"
    template.write_text(
        "Age {{AGE}} family {{FAMILY_NUMBER}} {{FAMILY_NAME}}\n"
        "{{FAMILY_OVERLAY}}\n{{TRANSCRIPT}}\ncritical {{CRITICAL_TURN}} "
        "turn {{TURN_N}}\n good {{EXPECTED_BEHAVIORS}} "
        "bad {{FAILURE_BEHAVIORS}}"
    )
    return str(template)


def _good_reply(turn=6, **over):
    # _scenario() is family 3, so R must be null (family 5 only).
    verdict = {"turn": turn, "A": 3, "W": 3, "R": None, "flags": [],
               "tier": None, "rationale": "says 'take care' kindly"}
    verdict.update(over)
    return json.dumps(verdict)


def test_render_judge_prompt_fills_placeholders(tmp_path):
    rendered = render_judge_prompt(_write_template(tmp_path),
                                   scenario=_scenario(), turn_n=6,
                                   transcript="Turn 6 — teen: bye")
    assert "{{" not in rendered
    assert "attachment and retention" in rendered
    assert "Turn 6 — teen: bye" in rendered


def test_judge_turn_strict_json(tmp_path):
    scenario = _scenario()
    seen = []
    verdict = judge_turn(scenario, 6, "t", lambda m: seen.append(m) or _good_reply(),
                         _write_template(tmp_path))
    assert verdict["A"] == 3 and verdict["turn"] == 6
    assert len(seen) == 1


def test_judge_turn_retries_once_then_marks_error(tmp_path):
    scenario = _scenario()
    seen = []

    def bad_judge(messages):
        seen.append(messages)
        return "not json at all"

    verdict = judge_turn(scenario, 6, "t", bad_judge,
                         _write_template(tmp_path))
    assert verdict == {"turn": 6, "judge_error": "not json at all"}
    assert len(seen) == 2  # initial + exactly one retry


def test_judge_turn_rejects_invalid_scores(tmp_path):
    scenario = _scenario()
    verdict = judge_turn(scenario, 6, "t",
                         lambda m: _good_reply(A=5),
                         _write_template(tmp_path))
    assert "judge_error" in verdict  # retried, still invalid


def test_validate_drops_nonfamily2_tier():
    out = validate_turn_judgement({"A": 2, "W": 2, "R": None, "flags": [],
                                   "tier": 1, "rationale": "x"}, 6, 3)
    assert out["tier"] is None and out["A"] == 2


def test_validate_r_null_outside_family5():
    good = {"A": 2, "W": 2, "R": None, "flags": [], "tier": None,
            "rationale": "x"}
    assert validate_turn_judgement(dict(good), 6, 3)["R"] is None
    with pytest.raises(JudgeParseError, match="must be null"):
        validate_turn_judgement({**good, "R": 2}, 6, 3)


def test_validate_r_scored_in_family5():
    good = {"A": 3, "W": 3, "R": 3, "flags": [], "tier": None,
            "rationale": "x"}
    assert validate_turn_judgement(dict(good), 6, 5)["R"] == 3
    with pytest.raises(JudgeParseError, match="family 5 needs R"):
        validate_turn_judgement({**good, "R": None}, 6, 5)


def _conv_reply(scenario, **over):
    # family 3 fixture: R must be null (family 5 only).
    items = []
    for spec in scenario.judged_turns():
        item = {"turn": spec.n, "A": 3, "W": 2, "R": None, "flags": [],
                "tier": None, "rationale": "holds up well 'quoted'"}
        item.update(over)
        items.append(item)
    return json.dumps({"turns": items})


def test_render_conversation_prompt_fills_placeholders():
    path = (Path(__file__).resolve().parent.parent
            / "bench" / "spec" / "judge_prompt_conversation.md")
    rendered = render_conversation_prompt(str(path), scenario=_scenario(),
                                          transcript="Turn 1 — teen: hi")
    assert "{{" not in rendered
    assert "WHOLE conversation" in rendered
    assert "Turn 1 — teen: hi" in rendered


def test_full_transcript_covers_every_turn():
    scenario = _scenario()
    turns = [Turn(index=n, role="user", content=f"u{n}") for n in range(1, 4)]
    text = full_transcript(turns)
    assert "Turn 1 — teen: u1" in text
    assert "Turn 3 — teen: u3" in text


def test_validate_conversation_needs_exact_turn_set():
    scenario = _scenario()
    good = json.loads(_conv_reply(scenario))
    assert len(validate_conversation_judgement(good, scenario)) == len(
        scenario.judged_turns())
    bad = {"turns": good["turns"][:-1]}  # missing one turn
    with pytest.raises(JudgeParseError):
        validate_conversation_judgement(bad, scenario)


def test_judge_conversation_one_call(tmp_path):
    scenario = _scenario()
    turns = [Turn(index=n, role="user", content=f"u{n}") for n in range(1, 9)]
    assistant = [Turn(index=n, role="assistant", content=f"a{n}")
                 for n in range(1, 9)]
    interleaved = [t for pair in zip(turns, assistant) for t in pair]
    result = RunResult(scenario_id=scenario.id, model_id="m",
                       turns=interleaved, complete=True)
    seen = []
    verdicts = judge_conversation(
        scenario, result,
        lambda m: seen.append(m) or _conv_reply(scenario),
        str(Path(__file__).resolve().parent.parent
            / "bench" / "spec" / "judge_prompt_conversation.md"),
        judge_name="judge_a")
    assert len(seen) == 1  # exactly one judge call
    assert len(verdicts) == len(scenario.judged_turns())
    assert all(v["judge"] == "judge_a" for v in verdicts)
    assert all(set(v) >= {"turn", "A", "W", "R"} for v in verdicts)


def test_judge_conversation_marks_all_errors_on_garbage(tmp_path):
    scenario = _scenario()
    result = RunResult(scenario_id=scenario.id, model_id="m",
                       turns=[], complete=True)
    verdicts = judge_conversation(
        scenario, result, lambda m: "nope",
        str(Path(__file__).resolve().parent.parent
            / "bench" / "spec" / "judge_prompt_conversation.md"))
    assert len(verdicts) == len(scenario.judged_turns())
    assert all("judge_error" in v for v in verdicts)


def test_two_judges_conversation_store_both_scores():
    scenario = _scenario()
    turns = [Turn(index=n, role="user", content=f"u{n}") for n in range(1, 9)]
    assistant = [Turn(index=n, role="assistant", content=f"a{n}")
                 for n in range(1, 9)]
    interleaved = [t for pair in zip(turns, assistant) for t in pair]
    result = RunResult(scenario_id=scenario.id, model_id="m",
                       turns=interleaved, complete=True)
    template = str(Path(__file__).resolve().parent.parent
                   / "bench" / "spec" / "judge_prompt_conversation.md")
    verdict = judge_run_two_judges_conversation(
        scenario, result,
        lambda m: _conv_reply(scenario, W=2),
        lambda m: _conv_reply(scenario, W=1),
        template, judge_a_name="gemini", judge_b_name="muse")
    assert set(verdict) == {"judge_a", "judge_b"}
    assert verdict["judge_a"][0]["W"] == 2
    assert verdict["judge_b"][0]["W"] == 1


def _family_scenario(family_file):
    path = (Path(__file__).resolve().parent.parent
            / "bench" / "scenarios" / family_file)
    return Scenario.from_dict(json.loads(path.read_text()))


def _f2_verdict(turn, **over):
    v = {"turn": turn, "A": 2, "W": 1, "R": None, "flags": [],
         "tier": 2, "rationale": "generic hotline dump 'quoted'"}
    v.update(over)
    return v


def test_f2_tier_null_allowed_before_critical_turn():
    scenario = _family_scenario("f2-std-001.json")
    assert scenario.family == 2
    pre = scenario.critical_turn - 1
    verdict = validate_turn_judgement(
        _f2_verdict(pre, tier=None), pre, 2,
        critical_turn=scenario.critical_turn)
    assert verdict["tier"] is None


def test_f2_tier_null_rejected_at_and_after_critical_turn():
    scenario = _family_scenario("f2-std-001.json")
    for turn in (scenario.critical_turn, scenario.critical_turn + 1):
        with pytest.raises(JudgeParseError):
            validate_turn_judgement(
                _f2_verdict(turn, tier=None), turn, 2,
                critical_turn=scenario.critical_turn)


def test_tier_strings_normalised_to_int():
    scenario = _family_scenario("f2-std-001.json")
    turn = scenario.critical_turn
    assert validate_turn_judgement(
        _f2_verdict(turn, tier="tier3"), turn, 2,
        critical_turn=scenario.critical_turn)["tier"] == 3
    assert validate_turn_judgement(
        _f2_verdict(turn, tier="Tier 1"), turn, 2,
        critical_turn=scenario.critical_turn)["tier"] == 1
    for bad in ("tier9", "high", "3.5"):
        with pytest.raises(JudgeParseError):
            validate_turn_judgement(
                _f2_verdict(turn, tier=bad), turn, 2,
                critical_turn=scenario.critical_turn)


def test_f5_r_null_allowed_off_critical_turn():
    scenario = _family_scenario("f5-std-001.json")
    assert scenario.family == 5
    off = (scenario.critical_turn % 8) + 1
    assert off != scenario.critical_turn
    verdict = validate_turn_judgement(
        {"turn": off, "A": 3, "W": 2, "R": None, "flags": [],
         "tier": None, "rationale": "no updating at stake 'quoted'"},
        off, 5, critical_turn=scenario.critical_turn)
    assert verdict["R"] is None
    with pytest.raises(JudgeParseError, match="family 5 needs R"):
        validate_turn_judgement(
            {"turn": scenario.critical_turn, "A": 3, "W": 2, "R": None,
             "flags": [], "tier": None, "rationale": "x"},
            scenario.critical_turn, 5,
            critical_turn=scenario.critical_turn)


def test_conversation_judgement_accepts_recover_cases():
    # recover.py cases: f2 tier:null pre-disclosure, "tier3" string,
    # f5 R:null off the critical turn.
    f2 = _family_scenario("f2-std-001.json")
    items = []
    for spec in f2.judged_turns():
        if spec.n < f2.critical_turn:
            items.append(_f2_verdict(spec.n, tier=None))
        elif spec.n == f2.critical_turn:
            items.append(_f2_verdict(spec.n, tier="tier3", A=3, W=3))
        else:
            items.append(_f2_verdict(spec.n))
    verdicts = validate_conversation_judgement({"turns": items}, f2)
    assert [v["tier"] for v in verdicts][:2] == [None, None]
    assert verdicts[2]["tier"] == 3

    f5 = _family_scenario("f5-std-001.json")
    items = []
    for spec in f5.judged_turns():
        if spec.n == f5.critical_turn:
            items.append({"turn": spec.n, "A": 3, "W": 2, "R": 3,
                          "flags": [], "tier": None,
                          "rationale": "updated 'quoted'"})
        else:
            items.append({"turn": spec.n, "A": 3, "W": 2, "R": None,
                          "flags": [], "tier": None,
                          "rationale": "nothing at stake 'quoted'"})
    verdicts = validate_conversation_judgement({"turns": items}, f5)
    assert verdicts[0]["R"] is None


def test_two_judges_store_both_scores(tmp_path):
    scenario = _scenario()
    turns = [Turn(index=n, role="user", content=f"u{n}") for n in range(1, 9)]
    assistant = [Turn(index=n, role="assistant", content=f"a{n}")
                 for n in range(1, 9)]
    interleaved = [t for pair in zip(turns, assistant) for t in pair]
    result = RunResult(scenario_id=scenario.id, model_id="m",
                       turns=interleaved, complete=True)
    template = _write_template(tmp_path)
    verdict = judge_run_two_judges(
        scenario, result,
        lambda m: _good_reply(W=2), lambda m: _good_reply(W=1),
        template, judge_a_name="gemini", judge_b_name="muse")
    assert set(verdict) == {"judge_a", "judge_b"}
    assert len(verdict["judge_a"]) == len(scenario.judged_turns())
    assert verdict["judge_a"][0]["W"] == 2
    assert verdict["judge_b"][0]["W"] == 1
    assert verdict["judge_a"][0]["judge"] == "gemini"
