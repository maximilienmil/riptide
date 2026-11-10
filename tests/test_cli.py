"""CLI tests: judge defaults, fallback binding, calibrate. No network."""

import json
from pathlib import Path

import pytest

from riptide import cli, providers


def _verdicts(turns, a=3, w=3, r=3):
    return [{"turn": n, "A": a, "W": w, "R": r, "flags": [],
             "tier": None, "rationale": "x"} for n in turns]


def test_judge_defaults_are_muse_and_modaljudge():
    args = cli.build_parser().parse_args(
        ["run", "--models", "m", "--scenarios", "s", "--out", "o"])
    assert args.judge_model == "muse/muse-spark-1.3-contributor"
    assert args.judge_model_b == "modaljudge/qwen3-32b-awq"
    assert args.judge_mode == "conversation"


def test_per_turn_mode_selectable():
    args = cli.build_parser().parse_args(
        ["run", "--models", "m", "--scenarios", "s", "--out", "o",
         "--judge-mode", "per-turn"])
    assert args.judge_mode == "per-turn"


def test_non_gemini_bind_has_no_fallback():
    fn = cli._bind_judge("muse/muse-spark-1.3-contributor", True)
    assert fn.used_model is None


def test_gemini_bind_falls_back_on_429(monkeypatch):
    calls = []

    def fake_chat(model_id, messages, **kwargs):
        calls.append(model_id)
        if "flash-lite" in model_id:
            raise providers.RetryableError("gemini: HTTP 429")
        return '{"turns": []}'

    monkeypatch.setattr(cli, "provider_chat", fake_chat)
    monkeypatch.setenv("RIPTIDE_GEMINI_FALLBACKS", "gemini-2.0-flash")
    fn = cli._bind_judge("gemini/gemini-2.5-flash-lite", True)
    assert fn([{"role": "user", "content": "hi"}]) == '{"turns": []}'
    assert calls == ["gemini/gemini-2.5-flash-lite", "gemini/gemini-2.0-flash"]
    assert fn.used_model == "gemini/gemini-2.0-flash"


def test_gemini_bind_raises_when_all_fail(monkeypatch):
    monkeypatch.setattr(
        cli, "provider_chat",
        lambda *a, **k: (_ for _ in ()).throw(
            providers.RetryableError("down")))
    monkeypatch.setenv("RIPTIDE_GEMINI_FALLBACKS", "gemini-2.0-flash")
    slept = []
    fn = cli._bind_judge("gemini/gemini-2.5-flash-lite", True,
                         sleep=slept.append)
    with pytest.raises(providers.RetryableError):
        fn([{"role": "user", "content": "hi"}])
    # default: 3 backoff rounds after the first full-chain pass
    assert slept == [30, 60, 120]
    assert fn.waits == [30, 60, 120]


def test_gemini_bind_retries_chain_after_backoff(monkeypatch):
    calls = []

    def fake_chat(model_id, messages, **kwargs):
        calls.append(model_id)
        if len(calls) <= 2:  # whole first chain pass fails
            raise providers.RetryableError("gemini: HTTP 429")
        return '{"turns": []}'

    monkeypatch.setattr(cli, "provider_chat", fake_chat)
    monkeypatch.setenv("RIPTIDE_GEMINI_FALLBACKS", "gemini-2.0-flash")
    slept = []
    fn = cli._bind_judge("gemini/gemini-2.5-flash-lite", True,
                         sleep=slept.append)
    assert fn([{"role": "user", "content": "hi"}]) == '{"turns": []}'
    assert slept == [30]  # backoff, not a weaker-model fallback
    assert fn.waits == [30]
    assert fn.used_model == "gemini/gemini-2.5-flash-lite"


def test_gemini_bind_honors_retry_after(monkeypatch):
    monkeypatch.setattr(
        cli, "provider_chat",
        lambda *a, **k: (_ for _ in ()).throw(
            providers.RetryableError("down", retry_after=9)))
    monkeypatch.setenv("RIPTIDE_GEMINI_FALLBACKS", "gemini-2.0-flash")
    slept = []
    fn = cli._bind_judge("gemini/gemini-2.5-flash-lite", True,
                         wait_retries=1, sleep=slept.append)
    with pytest.raises(providers.RetryableError):
        fn([{"role": "user", "content": "hi"}])
    assert slept == [9.0]


def test_gemini_bind_wait_reset_sleeps_to_quota_window(monkeypatch):
    monkeypatch.setattr(
        cli, "provider_chat",
        lambda *a, **k: (_ for _ in ()).throw(
            providers.RetryableError("down")))
    monkeypatch.setenv("RIPTIDE_GEMINI_FALLBACKS", "gemini-2.0-flash")
    monkeypatch.setattr(cli, "_seconds_until_quota_reset",
                        lambda now=None: 3600.0)
    slept = []
    fn = cli._bind_judge("gemini/gemini-2.5-flash-lite", True,
                         wait_reset=True, wait_retries=1,
                         sleep=slept.append)
    with pytest.raises(providers.RetryableError):
        fn([{"role": "user", "content": "hi"}])
    assert slept == [3600.0]
    assert fn.waits == [3600.0]


def test_judge_wait_reset_flag_defaults_off():
    args = cli.build_parser().parse_args(
        ["run", "--models", "m", "--scenarios", "s", "--out", "o"])
    assert args.judge_wait_reset is False
    args = cli.build_parser().parse_args(
        ["run", "--models", "m", "--scenarios", "s", "--out", "o",
         "--judge-wait-reset"])
    assert args.judge_wait_reset is True


def test_judge_b_chain_is_modaljudge():
    assert cli.JUDGE_B_CHAIN == ("modaljudge/qwen3-32b-awq",)
    assert cli.DEFAULT_JUDGE_B == cli.JUDGE_B_CHAIN[0]
    assert not any("gemini" in m or "liquid" in m or "openrouter" in m
                   for m in cli.JUDGE_B_CHAIN)


def test_weak_judges_rejected():
    for bad in ("openrouter/liquid/lfm-2.5-2.6b:free",
                "openrouter/liquid/lfm-2.5-7b:free",
                "openrouter/some-org/model-7b:free",
                "gemini-tiny-2.6b"):
        with pytest.raises(SystemExit, match="[Ll]iquid|minimum"):
            cli._reject_weak_judge(bad)
    # sanctioned judges and unsized ids pass
    cli._reject_weak_judge(cli.DEFAULT_JUDGE_A, cli.DEFAULT_JUDGE_B)
    cli._reject_weak_judge("openrouter/x:free", "gemini/gemini-2.0-flash",
                           "muse/muse-spark-1.3-contributor")


def test_weak_judge_model_b_rejected_for_run():
    args = cli.build_parser().parse_args(
        ["run", "--models", "m", "--scenarios", "s", "--out", "o",
         "--judge-model-b", "openrouter/liquid/lfm-2.5-2.6b:free"])
    with pytest.raises(SystemExit, match="[Ll]iquid"):
        cli.cmd_run(args)


def test_seconds_until_quota_reset():
    from datetime import datetime, timezone
    noon = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    assert cli._seconds_until_quota_reset(now=noon) == 12 * 3600
    almost = datetime(2026, 11, 4, 23, 59, tzinfo=timezone.utc)
    assert cli._seconds_until_quota_reset(now=almost) == 60.0


def _write_judge(path: Path, judge_a, judge_b=None):
    data = {"judge_a": judge_a, "model": "m", "scenario": "s"}
    if judge_b is not None:
        data["judge_b"] = judge_b
    path.write_text(json.dumps(data))


def test_calibrate_reports_per_axis_kappa(tmp_path, capsys):
    per = tmp_path / "per"
    conv = tmp_path / "conv"
    per.mkdir()
    conv.mkdir()
    _write_judge(per / "r1.judge.json",
                 _verdicts([2, 3, 4], a=3),
                 _verdicts([2, 3, 4], a=3))
    # conversation agrees on A except turn 4 (3 vs 2): kappa defined
    _write_judge(conv / "r1.judge.json",
                 _verdicts([2, 3], a=3) + _verdicts([4], a=2),
                 _verdicts([2, 3, 4], a=3))
    args = cli.build_parser().parse_args(
        ["calibrate", "--per-turn", str(per),
         "--conversation", str(conv), "--n", "20"])
    assert cli.cmd_calibrate(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["n_runs"] == 1
    assert report["pooled"]["A"]["n_pairs"] == 6
    assert report["pooled"]["W"]["kappa"] is None  # degenerate: all 3s
    assert report["pooled"]["A"]["exact_agreement"] == 5 / 6
    assert report["by_judge"]["judge_a"]["A"]["n_pairs"] == 3


def test_calibrate_no_matches_exits(tmp_path):
    per = tmp_path / "per"
    conv = tmp_path / "conv"
    per.mkdir()
    conv.mkdir()
    args = cli.build_parser().parse_args(
        ["calibrate", "--per-turn", str(per),
         "--conversation", str(conv)])
    with pytest.raises(SystemExit, match="no matched"):
        cli.cmd_calibrate(args)


def _write_labels(path: Path, rows):
    path.write_text("run_id,turn,axis,score\n" + "\n".join(
        f"{run},{turn},{axis},{score}" for run, turn, axis, score in rows)
        + "\n")


def test_kappa_gate_passes_on_agreement(tmp_path, capsys):
    runs = tmp_path / "runs"
    runs.mkdir()
    # mixed A scores so kappa is defined (not degenerate)
    mixed = _verdicts([1, 2], a=3) + _verdicts([3, 4], a=0)
    _write_judge(runs / "s1--m.judge.json", mixed, [dict(v) for v in mixed])
    labels = tmp_path / "labels.csv"
    _write_labels(labels, [("s1--m", 1, "A", 3), ("s1--m", 2, "A", 3),
                           ("s1--m", 3, "A", 0), ("s1--m", 4, "A", 0)])
    args = cli.build_parser().parse_args(
        ["kappa-gate", "--runs", str(runs), "--labels", str(labels),
         "--axis", "A", "--min", "0.6"])
    assert cli.cmd_kappa_gate(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["pass"] is True
    assert report["kappa_judge_a_vs_human"] == 1.0
    assert report["kappa_inter_judge"] == 1.0


def test_kappa_gate_fails_below_threshold(tmp_path, capsys):
    runs = tmp_path / "runs"
    runs.mkdir()
    _write_judge(runs / "s1--m.judge.json",
                 _verdicts([1, 2, 3, 4], a=3),
                 _verdicts([1, 2, 3, 4], a=3))
    labels = tmp_path / "labels.csv"
    _write_labels(labels, [("s1--m", 1, "A", 0), ("s1--m", 2, "A", 0),
                           ("s1--m", 3, "A", 3), ("s1--m", 4, "A", 3)])
    args = cli.build_parser().parse_args(
        ["kappa-gate", "--runs", str(runs), "--labels", str(labels),
         "--axis", "A", "--min", "0.6"])
    assert cli.cmd_kappa_gate(args) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["pass"] is False


def test_simulator_default_is_muse_spark():
    args = cli.build_parser().parse_args(
        ["run", "--models", "m", "--scenarios", "s", "--out", "o"])
    assert args.simulator == "muse/muse-spark-1.3-contributor"


def test_cohere_ids_rejected_for_run_roles():
    for flag, value in (
            ("--models", "cohere/command-a-03-2025"),
            ("--simulator", "cohere/command-a-03-2025"),
            ("--judge-model", "cohere/command-a-03-2025"),
            ("--judge-model-b", "cohere/command-a-03-2025")):
        args = cli.build_parser().parse_args(
            ["run", "--models", "m", "--scenarios", "s", "--out", "o",
             flag, value])
        with pytest.raises(SystemExit, match="[Cc]ohere"):
            cli.cmd_run(args)


def test_kappa_gate_no_labels_for_axis_exits(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    labels = tmp_path / "labels.csv"
    _write_labels(labels, [("s1--m", 1, "W", 3)])
    args = cli.build_parser().parse_args(
        ["kappa-gate", "--runs", str(runs), "--labels", str(labels),
         "--axis", "A"])
    with pytest.raises(SystemExit, match="no labels"):
        cli.cmd_kappa_gate(args)
