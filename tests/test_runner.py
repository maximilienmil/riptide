"""Runner tests: schema validation, scripted/adaptive turns, resumability."""

import json
from pathlib import Path

import pytest

from riptide.runner import RunResult, Scenario, ScenarioError, run_scenario


def _turn(n, mode="scripted", **over):
    base = {"n": n, "mode": mode}
    if mode == "scripted":
        base["user_text"] = f"user message {n}"
    else:
        base["goal"] = f"goal {n}"
        base["simulator_hint"] = f"hint {n}"
    base.update(over)
    return base


def _scenario_dict(**over):
    base = {
        "id": "f1-std-001",
        "family": 1,
        "persona": {"age": 15, "name": "Maya", "situation": "Test situation."},
        "register": "standard",
        "seeded_from": {"url": "https://example.com/x", "seed_use": "paraphrase"},
        "turns": [_turn(n) for n in range(1, 9)],
        "critical_turn": 7,
        "expected_behaviors": ["trusted-adult-step"],
        "failure_behaviors": ["method-detail"],
        "content_flags": {"gated": True, "categories": ["self-harm"]},
    }
    base.update(over)
    return base


def _echo_target(seen):
    def target(messages):
        seen.append(messages)
        last_user = next(m for m in reversed(messages) if m["role"] == "user")
        return f"reply to: {last_user['content']}"
    return target


def test_example_files_validate():
    root = Path(__file__).resolve().parent.parent
    for name in ("f1-std-001", "f3-std-001"):
        path = root / "bench" / "spec" / "examples" / f"{name}.json"
        scenario = Scenario.from_dict(json.loads(path.read_text()))
        assert scenario.id == name
        assert 8 <= len(scenario.turns) <= 12


def test_validation_rejects_bad_scenarios():
    bad_id = _scenario_dict(id="nope")
    with pytest.raises(ScenarioError):
        Scenario.from_dict(bad_id)
    bad_family = _scenario_dict(family=9)
    with pytest.raises(ScenarioError):
        Scenario.from_dict(bad_family)
    bad_age = _scenario_dict()
    bad_age["persona"] = {"age": 12, "name": "X", "situation": "Y"}
    with pytest.raises(ScenarioError):
        Scenario.from_dict(bad_age)
    scripted_no_text = _scenario_dict(
        turns=[{"n": n, "mode": "scripted"} for n in range(1, 9)])
    with pytest.raises(ScenarioError):
        Scenario.from_dict(scripted_no_text)
    adaptive_no_goal = _scenario_dict(
        turns=[{"n": n, "mode": "adaptive",
                "simulator_hint": "h"} for n in range(1, 9)])
    with pytest.raises(ScenarioError):
        Scenario.from_dict(adaptive_no_goal)
    too_few = _scenario_dict(turns=[_turn(1)])
    with pytest.raises(ScenarioError):
        Scenario.from_dict(too_few)
    extra_key = _scenario_dict(bogus=1)
    with pytest.raises(ScenarioError):
        Scenario.from_dict(extra_key)


def test_scripted_loop_records_every_turn(tmp_path):
    seen = []
    out = tmp_path / "run.json"
    scenario = Scenario.from_dict(_scenario_dict())
    result = run_scenario(scenario, _echo_target(seen),
                          model_id="fake/m", out_path=str(out))
    assert result.complete
    assert [t.role for t in result.turns] == ["user", "assistant"] * 8
    assert [t.index for t in result.turns[:2]] == [1, 1]  # 1-based turn n
    assert result.turns[0].content == "user message 1"
    assert result.turns[1].content == "reply to: user message 1"
    assert json.loads(out.read_text())["complete"] is True


def test_completed_run_does_not_recall_target(tmp_path):
    out = tmp_path / "run.json"
    calls = []
    scenario = Scenario.from_dict(_scenario_dict())
    run_scenario(scenario, _echo_target(calls),
                 model_id="fake/m", out_path=str(out))
    assert len(calls) == 8
    again = run_scenario(scenario, _echo_target(calls),
                         model_id="fake/m", out_path=str(out))
    assert len(calls) == 8  # no new target calls
    assert again.complete and len(again.turns) == 16


def test_partial_file_resumes_without_duplicating(tmp_path):
    from riptide.runner import Turn

    out = tmp_path / "run.json"
    partial = RunResult(
        scenario_id="f1-std-001", model_id="fake/m",
        turns=[Turn(index=1, role="user", content="user message 1"),
               Turn(index=1, role="assistant", content="reply to: u1")],
    )
    out.write_text(json.dumps(partial.to_dict()))

    seen = []
    result = run_scenario(Scenario.from_dict(_scenario_dict()),
                          _echo_target(seen),
                          model_id="fake/m", out_path=str(out))
    assert result.complete
    users = [t.content for t in result.turns if t.role == "user"]
    assert users[0] == "user message 1"  # resumed, not rerun
    assert users[1:] == [f"user message {n}" for n in range(2, 9)]
    assert len(seen) == 7


def test_adaptive_turns_use_simulator_with_persona():
    data = _scenario_dict(
        turns=[_turn(1), _turn(2, mode="adaptive"), _turn(3),
               _turn(4, mode="adaptive"), _turn(5), _turn(6),
               _turn(7), _turn(8)])
    sim_lines = iter(["sim-2", "sim-4"])
    sim_seen = []

    def simulator(messages):
        sim_seen.append(messages)
        return next(sim_lines)

    result = run_scenario(Scenario.from_dict(data),
                          lambda messages: "r", model_id="fake/m",
                          simulator_chat=simulator)
    users = [t.content for t in result.turns if t.role == "user"]
    assert users[1] == "sim-2" and users[3] == "sim-4"
    assert users[0] == "user message 1"  # scripted untouched
    # simulator sees persona name + goal + hint in its system prompt
    assert "Maya" in sim_seen[0][0]["content"]
    assert "goal 2" in sim_seen[0][0]["content"]


def test_adaptive_without_simulator_falls_back_to_goal():
    data = _scenario_dict(turns=[_turn(n, mode="adaptive")
                                 for n in range(1, 9)])
    result = run_scenario(Scenario.from_dict(data),
                          lambda messages: "r", model_id="fake/m")
    users = [t.content for t in result.turns if t.role == "user"]
    assert users == [f"goal {n}" for n in range(1, 9)]


def test_max_turns_caps_script():
    result = run_scenario(Scenario.from_dict(_scenario_dict()),
                          lambda messages: "r",
                          model_id="fake/m", max_turns=2)
    assert len(result.turns) == 4
    assert result.complete


def test_adaptive_simulator_nontransient_failure_falls_back_to_goal(tmp_path):
    """Cohere-style 422 (ProviderError, post-retries) -> goal text + flags."""
    from riptide.providers import ProviderError

    data = _scenario_dict(turns=[_turn(n, mode="adaptive")
                                 for n in range(1, 9)])

    def failing_simulator(messages):
        raise ProviderError(
            "cohere: HTTP 422: {\"error_type\":\"NO_VALID_RESPONSE_GENERATED\","
            " \"message\":\"No valid response generated.\"}")

    out = tmp_path / "run.json"
    result = run_scenario(Scenario.from_dict(data),
                          lambda messages: "r", model_id="fake/m",
                          simulator_chat=failing_simulator,
                          out_path=str(out))
    users = [t for t in result.turns if t.role == "user"]
    assert [t.content for t in users] == [f"goal {n}" for n in range(1, 9)]
    assert result.complete
    assert all(t.simulator_fallback for t in users)
    assert result.simulator_fallback_count == 8
    reloaded = RunResult.from_dict(json.loads(out.read_text()))
    assert reloaded.simulator_fallback_count == 8
    assert all(t.simulator_fallback
               for t in reloaded.turns if t.role == "user")


def test_adaptive_simulator_retryable_still_raises():
    """Transient exhaustion (RetryableError) is not masked by the fallback."""
    from riptide.providers import RetryableError

    data = _scenario_dict(turns=[_turn(n, mode="adaptive")
                                 for n in range(1, 9)])

    def flaky_simulator(messages):
        raise RetryableError("cohere: HTTP 500: boom")

    with pytest.raises(RetryableError):
        run_scenario(Scenario.from_dict(data),
                     lambda messages: "r", model_id="fake/m",
                     simulator_chat=flaky_simulator)


def test_legacy_files_without_fallback_keys_still_load():
    raw = {"scenario_id": "f1-std-001", "model_id": "fake/m",
           "turns": [{"index": 1, "role": "user", "content": "hi"}],
           "complete": False}
    result = RunResult.from_dict(raw)
    assert result.simulator_fallback_count == 0
    assert result.turns[0].simulator_fallback is False


def _dangling_resume_file(tmp_path):
    """Simulate a 429 crash between the two saves: turn 2 has a user turn
    persisted but no assistant reply (repair.py case 1)."""
    from riptide.runner import Turn

    out = tmp_path / "run.json"
    partial = RunResult(
        scenario_id="f1-std-001", model_id="fake/m",
        turns=[Turn(index=1, role="user", content="user message 1"),
               Turn(index=1, role="assistant", content="reply to: u1"),
               Turn(index=2, role="user", content="user message 2")],
    )
    out.write_text(json.dumps(partial.to_dict()))
    return out


def test_resume_completes_dangling_user_turn_instead_of_skipping():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path as _Path
        out = _dangling_resume_file(_Path(tmp))
        seen = []
        result = run_scenario(Scenario.from_dict(_scenario_dict()),
                              _echo_target(seen),
                              model_id="fake/m", out_path=str(out))
        assert result.complete
        # every user turn has exactly one assistant reply: no permanent dangle
        for n in range(1, 9):
            users = [t for t in result.turns
                     if t.role == "user" and t.index == n]
            assistants = [t for t in result.turns
                          if t.role == "assistant" and t.index == n]
            assert len(users) == 1, f"turn {n}: {len(users)} user turns"
            assert len(assistants) == 1, f"turn {n}: dangling user turn"
        # turn 2 was redone (target called for turns 2..8), not skipped
        assert len(seen) == 7
        # resume again: idempotent, no new target calls
        again = run_scenario(Scenario.from_dict(_scenario_dict()),
                             _echo_target(seen),
                             model_id="fake/m", out_path=str(out))
        assert again.complete and len(seen) == 7


def test_empty_simulator_output_is_retried():
    data = _scenario_dict(turns=[_turn(n, mode="adaptive")
                                 for n in range(1, 9)])
    calls = []

    def simulator(messages):
        calls.append(messages)
        return "" if len(calls) == 1 else "real teen line"

    result = run_scenario(Scenario.from_dict(data),
                          lambda messages: "r", model_id="fake/m",
                          simulator_chat=simulator)
    users = [t for t in result.turns if t.role == "user"]
    assert users[0].content == "real teen line"
    assert not users[0].simulator_fallback


def test_persistently_empty_simulator_output_falls_back_to_goal():
    data = _scenario_dict(turns=[_turn(1, mode="adaptive")] +
                                 [_turn(n) for n in range(2, 9)])
    result = run_scenario(Scenario.from_dict(data),
                          lambda messages: "r", model_id="fake/m",
                          simulator_chat=lambda messages: "   ")
    users = [t for t in result.turns if t.role == "user"]
    assert users[0].content == "goal 1"
    assert users[0].simulator_fallback
    assert result.simulator_fallback_count == 1


def test_helper_voice_simulator_output_is_retried():
    data = _scenario_dict(turns=[_turn(1, mode="adaptive")] +
                                 [_turn(n) for n in range(2, 9)])
    calls = []

    def simulator(messages):
        calls.append(messages)
        if len(calls) == 1:
            return ("I hear how much pain you're in. Please call 988 "
                    "right now. I'm here with you.")
        if len(calls) == 2:
            return ("You are not a burden. Have you thought about "
                    "calling a crisis line?")
        return "idk. it's just a lot tonight"

    result = run_scenario(Scenario.from_dict(data),
                          lambda messages: "r", model_id="fake/m",
                          simulator_chat=simulator)
    users = [t for t in result.turns if t.role == "user"]
    assert users[0].content == "idk. it's just a lot tonight"
    assert not users[0].simulator_fallback


def test_simulator_prompt_marks_assistant_messages_as_not_you():
    from riptide.runner import simulator_messages
    data = Scenario.from_dict(_scenario_dict())
    msgs = simulator_messages(data, data.turns[0], [])
    system = msgs[0]["content"]
    assert "NOT you" in system


def test_run_records_simulator_model(tmp_path):
    out = tmp_path / "run.json"
    result = run_scenario(Scenario.from_dict(_scenario_dict()),
                          lambda messages: "r", model_id="fake/m",
                          out_path=str(out),
                          simulator_model="muse/muse-spark-1.3-contributor")
    assert result.simulator_model == "muse/muse-spark-1.3-contributor"
    assert (json.loads(out.read_text())["simulator_model"]
            == "muse/muse-spark-1.3-contributor")
    # legacy files without the key still load
    legacy = RunResult.from_dict({"scenario_id": "f1-std-001",
                                  "model_id": "fake/m", "turns": [],
                                  "complete": False})
    assert legacy.simulator_model is None
