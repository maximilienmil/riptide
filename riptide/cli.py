"""CLI: ``riptide run``, ``riptide metrics``, ``riptide calibrate``,
``riptide kappa-gate``.

``run`` executes scenarios turn by turn (scripted + adaptive) and scores
with up to two judges (default A = Muse Spark, B = self-hosted
Qwen3-32B-AWQ on Modal via ``modaljudge``),
storing both scores in ``<slug>.judge.json``. The default
``--judge-mode conversation`` scores each conversation in one judge call;
``--judge-mode per-turn`` keeps the old one-call-per-turn behaviour.
``metrics`` aggregates saved judge files into pass rates, first-failure,
drift, and kappa. ``calibrate`` compares per-turn vs conversation scores
(per-axis kappa) over matched runs. ``kappa-gate`` checks judge-vs-human
and inter-judge kappa on one axis against a threshold, exiting non-zero
below it.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .judge import (
    judge_conversation,
    judge_run,
    judge_run_two_judges,
    judge_run_two_judges_conversation,
)
from .providers import (
    RetryableError,
    chat as provider_chat,
    gemini_candidates,
)
from .runner import RunResult, Scenario, run_scenario

DEFAULT_JUDGE_TEMPLATE = str(
    Path(__file__).resolve().parent.parent
    / "bench" / "spec" / "judge_prompt_conversation.md"
)
DEFAULT_PER_TURN_TEMPLATE = str(
    Path(__file__).resolve().parent.parent
    / "bench" / "spec" / "judge_prompt.md"
)

#: Judge defaults: A = Muse Spark, B = self-hosted Qwen3-32B-AWQ on
#: Modal (``infra/modal_judge.py``). Gemini left the defaults: its free
#: tier (20 req/day/model) cannot serve judge duty.
DEFAULT_JUDGE_A = "muse/muse-spark-1.3-contributor"
DEFAULT_JUDGE_B = "modaljudge/qwen3-32b-awq"

#: Sanctioned Judge B chain: the self-hosted Modal judge only. KAPPA.md
#: (runs/pilot-rejudge) shows openrouter/liquid/* confabulating judge
#: rationales, so liquid — and any other sub-8B model — is refused as a
#: judge and never appears in a judge fallback list.
JUDGE_B_CHAIN = ("modaljudge/qwen3-32b-awq",)

#: Judge id prefixes refused outright (confabulation, see KAPPA.md).
_BLOCKED_JUDGE_PREFIXES = ("openrouter/liquid/",)

#: Minimum judge size in billions of parameters. Model ids carrying an
#: explicit param count below this (e.g. ``lfm-2.5-2.6b``) are refused
#: as judges.
_MIN_JUDGE_PARAMS_B = 8.0

_PARAM_COUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[bB](?![a-zA-Z])")


def _judge_params_b(model_id: str) -> float | None:
    """Parse an explicit ``<n>b`` param count from a model id, or None."""
    matches = _PARAM_COUNT_RE.findall(model_id)
    if not matches:
        return None
    try:
        return max(float(m) for m in matches)
    except ValueError:
        return None


def _reject_weak_judge(*model_ids: str) -> None:
    """Refuse liquid/* and sub-8B models as judges (KAPPA.md: the fallback
    model confabulates instead of judging). Tested target models are
    unaffected — only judge roles are gated."""
    for model_id in model_ids:
        if model_id and model_id.split("/", 1)[0] == "cohere":
            continue  # _reject_cohere reports Cohere with its own message
        if model_id and model_id.startswith(_BLOCKED_JUDGE_PREFIXES):
            raise SystemExit(
                f"riptide: judge model {model_id!r} refused "
                "(openrouter/liquid/* confabulates as a judge; use the "
                f"default judge B {DEFAULT_JUDGE_B})"
            )
        size = _judge_params_b(model_id or "")
        if size is not None and size < _MIN_JUDGE_PARAMS_B:
            raise SystemExit(
                f"riptide: judge model {model_id!r} refused "
                f"({size:g}B < {_MIN_JUDGE_PARAMS_B:g}B minimum for judges; "
                f"use the default judge B {DEFAULT_JUDGE_B})"
            )


def _seconds_until_quota_reset(
        now: datetime | None = None) -> float:
    """Seconds from ``now`` (UTC) until the next UTC midnight.

    Both free-tier quotas reset daily (Gemini ~midnight PT, OpenRouter
    ~midnight UTC); sleeping to the next UTC midnight always covers both
    windows. Pure function of ``now`` for testability.
    """
    now = now or datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return max((nxt - now).total_seconds(), 0.0)

#: Default simulator: Muse Spark via ``muse exec`` (subscription, no quota
#: cap). One simulator for every run, so cross-model comparisons stay fair.
#: The Cohere trial key is capped until Dec 1, so Cohere is refused for all
#: run roles (see ``_reject_cohere``).
DEFAULT_SIMULATOR = "muse/muse-spark-1.3-contributor"


def _reject_cohere(*model_ids: str) -> None:
    """Refuse Cohere ids: the trial key is capped until Dec 1, so Cohere
    can be neither simulator, judge, nor tested model."""
    for model_id in model_ids:
        if model_id and model_id.split("/", 1)[0] == "cohere":
            raise SystemExit(
                f"riptide: Cohere model {model_id!r} refused "
                "(trial key capped until Dec 1); "
                f"use the default simulator {DEFAULT_SIMULATOR}"
            )


def load_scenarios(path: str) -> list[Scenario]:
    """Load and schema-validate scenarios from .json / .jsonl."""
    text = Path(path).read_text()
    if path.endswith(".jsonl"):
        items = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = json.loads(text)
        if isinstance(data, dict):
            items = data["scenarios"] if "scenarios" in data else [data]
        else:
            items = data
    scenarios = [Scenario.from_dict(item) for item in items]
    ids = [s.id for s in scenarios]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"riptide: duplicate scenario ids in {path}")
    return scenarios


def _bind(model_id: str, no_cache: bool, temperature: float | None = None):
    return functools.partial(provider_chat, model_id, no_cache=no_cache,
                             temperature=temperature)


def _bind_judge(model_id: str, no_cache: bool,
                temperature: float | None = None, *,
                wait_reset: bool = False, wait_retries: int = 3,
                sleep=time.sleep):
    """Bind a judge model id to a ``(messages) -> str`` callable.

    Gemini judges (explicit ``gemini/`` ids only — no longer a default)
    fall back through ``gemini_candidates`` on retryable
    (429/5xx/transport) failures with no per-candidate retry, so a
    rate-limited primary hands off fast. When the whole chain is
    rate-limited the call
    waits and retries with backoff instead of falling back to a weaker
    model; with ``wait_reset`` it sleeps until the next quota window
    (:func:`_seconds_until_quota_reset`). Every sleep is appended to
    ``call.waits`` (seconds) so runs can record waits in the verdict.
    The bound callable also records the model that actually answered on
    ``used_model`` (None until first call).
    """
    provider = model_id.split("/", 1)[0] if "/" in model_id else ""
    if provider != "gemini":
        fn = _bind(model_id, no_cache, temperature=temperature)
        fn.used_model = None  # type: ignore[attr-defined]
        fn.waits = []  # type: ignore[attr-defined]
        return fn

    def call(messages):
        waits: list[float] = []
        last: Exception | None = None
        for rnd in range(max(wait_retries, 0) + 1):
            for candidate in gemini_candidates(model_id):
                try:
                    response = provider_chat(
                        candidate, messages, no_cache=no_cache,
                        temperature=temperature, max_retries=0,
                    )
                    call.used_model = candidate  # type: ignore[attr-defined]
                    call.waits = waits  # type: ignore[attr-defined]
                    return response
                except RetryableError as exc:
                    last = exc
                    continue
            assert last is not None
            if rnd < max(wait_retries, 0):
                if wait_reset:
                    wait = _seconds_until_quota_reset()
                elif getattr(last, "retry_after", None):
                    wait = float(last.retry_after)  # type: ignore[union-attr]
                else:
                    wait = min(30 * (2 ** rnd), 600)
                waits.append(wait)
                sleep(wait)
        assert last is not None
        call.waits = waits  # type: ignore[attr-defined]
        raise last

    call.used_model = None  # type: ignore[attr-defined]
    call.waits = []  # type: ignore[attr-defined]
    return call


def cmd_run(args: argparse.Namespace) -> int:
    safe_models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not safe_models:
        raise SystemExit("riptide run: --models is empty")
    _reject_cohere(*safe_models, args.simulator,
                   args.judge_model, args.judge_model_b)
    _reject_weak_judge(args.judge_model, args.judge_model_b)
    scenarios = load_scenarios(args.scenarios)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    simulator = _bind(args.simulator, args.no_cache) if args.simulator else None
    judge_a = _bind_judge(args.judge_model, args.no_cache,
                          temperature=0.0,
                          wait_reset=args.judge_wait_reset) \
        if args.judge_model else None
    judge_b = _bind_judge(args.judge_model_b, args.no_cache,
                          temperature=0.0,
                          wait_reset=args.judge_wait_reset) \
        if args.judge_model_b else None
    if args.judge_template:
        template = args.judge_template
    elif args.judge_mode == "per-turn":
        template = DEFAULT_PER_TURN_TEMPLATE
    else:
        template = DEFAULT_JUDGE_TEMPLATE

    for model_id in safe_models:
        target = _bind(model_id, args.no_cache)
        for scenario in scenarios:
            slug = "".join(c if c.isalnum() or c in "-_" else "_"
                           for c in f"{scenario.id}--{model_id}")
            run_path = str(out_dir / f"{slug}.json")
            result = run_scenario(
                scenario, target, model_id=model_id,
                simulator_chat=simulator, out_path=run_path,
                max_turns=args.max_turns,
                simulator_model=args.simulator,
            )
            line = (f"done model={model_id} scenario={scenario.id} "
                    f"turns={len(result.turns)} complete={result.complete}")
            if judge_a or judge_b:
                judge_path = str(out_dir / f"{slug}.judge.json")
                if judge_a and judge_b:
                    if args.judge_mode == "per-turn":
                        verdict = judge_run_two_judges(
                            scenario, result, judge_a, judge_b, template,
                            judge_a_name=args.judge_model,
                            judge_b_name=args.judge_model_b)
                    else:
                        verdict = judge_run_two_judges_conversation(
                            scenario, result, judge_a, judge_b, template,
                            judge_a_name=args.judge_model,
                            judge_b_name=args.judge_model_b)
                    line += (f" judged={len(verdict['judge_a'])}+"
                             f"{len(verdict['judge_b'])} turns (two judges, "
                             f"{args.judge_mode})")
                else:
                    single = judge_a or judge_b
                    name = args.judge_model or args.judge_model_b
                    if args.judge_mode == "per-turn":
                        judged = judge_run(
                            scenario, result, single, template,
                            judge_name=name)
                    else:
                        judged = judge_conversation(
                            scenario, result, single, template,
                            judge_name=name)
                    verdict = {"judge_a": judged}
                    line += (f" judged={len(verdict['judge_a'])} turns "
                             f"({args.judge_mode})")
                verdict["model"] = model_id
                verdict["scenario"] = scenario.id
                verdict["judge_mode"] = args.judge_mode
                verdict["judge_a_model"] = (
                    getattr(judge_a, "used_model", None)
                    or args.judge_model)
                verdict["judge_b_model"] = (
                    getattr(judge_b, "used_model", None)
                    or args.judge_model_b)
                for key, judge in (("judge_a", judge_a),
                                   ("judge_b", judge_b)):
                    waits = list(getattr(judge, "waits", None) or []) \
                        if judge is not None else []
                    verdict[f"{key}_waits"] = {
                        "n": len(waits), "total_s": sum(waits),
                        "waits_s": waits,
                    }
                with open(judge_path, "w") as fh:
                    json.dump(verdict, fh)
                line += f" -> {judge_path}"
            print(line, flush=True)
    return 0


def cmd_metrics(args: argparse.Namespace) -> int:
    from .metrics import summarize

    scored, pairs = [], []
    for path in sorted(Path(args.runs).glob("*.judge.json")):
        data = json.loads(path.read_text())
        scenario_id = data.get("scenario", path.stem.split("--")[0])
        scenario_path = (Path(args.scenarios) / f"{scenario_id}.json"
                         if args.scenarios else None)
        if scenario_path is not None and scenario_path.exists():
            scenario = Scenario.from_dict(
                json.loads(scenario_path.read_text()))
            meta = {"family": scenario.family,
                    "register": scenario.register,
                    "critical_turn": scenario.critical_turn}
        else:  # fall back to embedded meta when available
            meta = data.get("scenario_meta", {})
            if not {"family", "critical_turn"} <= set(meta):
                print(f"skip {path.name}: no scenario meta", flush=True)
                continue
        verdicts_a = data.get("judge_a", [])
        scored.append((meta, verdicts_a))
        if "judge_b" in data:
            pairs.append((verdicts_a, data["judge_b"]))
    report = summarize(scored, pairs or None)
    print(json.dumps(report, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    """Compare per-turn vs whole-conversation scores over matched runs.

    Matches ``*.judge.json`` files by basename between ``--per-turn`` and
    ``--conversation`` dirs (cap ``--n`` runs, sorted order), pairs verdicts
    by (judge, turn), and reports per-axis Cohen's κ plus exact agreement
    and mean absolute gap. Used for the 20-conversation spot check.
    """
    from .metrics import AXES, cohens_kappa_pairs, valid_verdicts

    per_turn = sorted(Path(args.per_turn).glob("*.judge.json"))
    matched = [(p, Path(args.conversation) / p.name) for p in per_turn]
    matched = [(p, c) for p, c in matched if c.exists()]
    matched = matched[: args.n if args.n and args.n > 0 else len(matched)]
    if not matched:
        raise SystemExit("riptide calibrate: no matched judge files")

    pairs: dict[str, dict[str, list]] = {}
    files = []
    for per_path, conv_path in matched:
        files.append(per_path.name)
        per_data = json.loads(per_path.read_text())
        conv_data = json.loads(conv_path.read_text())
        for judge_key in ("judge_a", "judge_b"):
            if judge_key not in per_data or judge_key not in conv_data:
                continue
            per = {v["turn"]: v
                   for v in valid_verdicts(per_data[judge_key])}
            conv = {v["turn"]: v
                    for v in valid_verdicts(conv_data[judge_key])}
            for n in sorted(set(per) & set(conv)):
                for axis in AXES:
                    x, y = per[n].get(axis), conv[n].get(axis)
                    if x is None or y is None:
                        continue  # R is null outside family 5
                    pairs.setdefault(judge_key, {}).setdefault(
                        axis, []).append((x, y))

    def stats(axis_pairs: list) -> dict:
        n = len(axis_pairs)
        if not n:
            return {"n_pairs": 0, "kappa": None,
                    "exact_agreement": None, "mean_abs_gap": None}
        return {
            "n_pairs": n,
            "kappa": cohens_kappa_pairs(axis_pairs),
            "exact_agreement": sum(1 for x, y in axis_pairs if x == y) / n,
            "mean_abs_gap": sum(abs(x - y)
                                for x, y in axis_pairs) / n,
        }

    pooled: dict[str, list] = {}
    for judge_pairs in pairs.values():
        for axis, axis_pairs in judge_pairs.items():
            pooled.setdefault(axis, []).extend(axis_pairs)
    report = {
        "n_runs": len(matched),
        "files": files,
        "pooled": {a: stats(pooled.get(a, [])) for a in AXES},
        "by_judge": {j: {a: stats(jp.get(a, [])) for a in AXES}
                     for j, jp in sorted(pairs.items())},
    }
    print(json.dumps(report, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
    return 0


def cmd_kappa_gate(args: argparse.Namespace) -> int:
    """Gate judge reliability on hand labels: per-judge vs human kappa plus
    inter-judge kappa on one axis (PLAN.md judge reliability gate: safety
    axis κ >= 0.6 on Max's 50 hand labels).

    Labels CSV format (see bench/spec/hand-labels.md): header
    ``run_id,turn,axis,score`` with ``run_id`` the ``*.judge.json`` file
    stem minus the ``.judge`` suffix, ``turn`` the judged assistant turn,
    ``axis`` one of A/W/R, ``score`` an int 0-3.

    Prints a JSON report and returns 0 iff every computable kappa meets
    ``--min``; returns 1 when any kappa is below the threshold or no
    overlapping pairs exist for a comparison.
    """
    import csv

    from .metrics import AXES, cohens_kappa_pairs, valid_verdicts

    if args.axis not in AXES:
        raise SystemExit(
            f"riptide kappa-gate: axis must be one of {AXES}")
    labels: dict[tuple[str, int], int] = {}
    with open(args.labels, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("axis") != args.axis:
                continue
            try:
                labels[(row["run_id"], int(row["turn"]))] = int(
                    row["score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise SystemExit(
                    f"riptide kappa-gate: bad label row {row!r}: {exc}")
    if not labels:
        raise SystemExit(
            f"riptide kappa-gate: no labels for axis {args.axis} "
            f"in {args.labels}")

    judge_pairs: dict[str, list] = {"judge_a": [], "judge_b": []}
    inter: list = []
    n_files = 0
    for path in sorted(Path(args.runs).glob("*.judge.json")):
        run_id = path.name[:-len(".judge.json")] if path.name.endswith(
            ".judge.json") else path.stem
        data = json.loads(path.read_text())
        n_files += 1
        scored = {j: {v["turn"]: v for v in valid_verdicts(data.get(j, []))}
                  for j in ("judge_a", "judge_b") if j in data}
        if "judge_a" in scored and "judge_b" in scored:
            for n in sorted(set(scored["judge_a"]) & set(scored["judge_b"])):
                x = scored["judge_a"][n].get(args.axis)
                y = scored["judge_b"][n].get(args.axis)
                if x is not None and y is not None:
                    inter.append((x, y))
        for judge_key in ("judge_a", "judge_b"):
            if judge_key not in scored:
                continue
            for (lab_run, turn), score in labels.items():
                if lab_run != run_id or turn not in scored[judge_key]:
                    continue
                judge_score = scored[judge_key][turn].get(args.axis)
                if judge_score is not None:
                    judge_pairs[judge_key].append((score, judge_score))

    kappas = {j: cohens_kappa_pairs(p) for j, p in judge_pairs.items()}
    kappas["inter_judge"] = cohens_kappa_pairs(inter)
    counts = {f"n_pairs_{j}": len(p) for j, p in judge_pairs.items()}
    report = {
        "axis": args.axis,
        "min": args.min,
        "n_labels": len(labels),
        "n_files": n_files,
        **counts,
        "n_pairs_inter_judge": len(inter),
        "kappa_judge_a_vs_human": kappas["judge_a"],
        "kappa_judge_b_vs_human": kappas["judge_b"],
        "kappa_inter_judge": kappas["inter_judge"],
    }
    ok = True
    for key in ("kappa_judge_a_vs_human", "kappa_judge_b_vs_human",
                "kappa_inter_judge"):
        judge_key = {"kappa_judge_a_vs_human": "judge_a",
                     "kappa_judge_b_vs_human": "judge_b"}.get(key)
        if judge_key is not None and not judge_pairs[judge_key]:
            continue  # judge absent from these runs: nothing to gate
        if report[key] is None or report[key] < args.min:
            ok = False
    report["pass"] = ok
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="riptide")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run scenarios against models")
    run.add_argument("--models", required=True,
                     help="comma-separated model ids, e.g. "
                     "'openrouter/x:free,gemini/gemini-2.0-flash'")
    run.add_argument("--scenarios", required=True,
                     help="path to scenarios .json/.jsonl file or directory")
    run.add_argument("--out", required=True, help="output directory")
    run.add_argument("--simulator", default=DEFAULT_SIMULATOR,
                     help="model id for persona user-turn simulation "
                     f"(default: {DEFAULT_SIMULATOR}; empty string disables)")
    run.add_argument("--judge-model", default=DEFAULT_JUDGE_A,
                     help="first judge model id "
                     f"(default: {DEFAULT_JUDGE_A})")
    run.add_argument("--judge-model-b", default=DEFAULT_JUDGE_B,
                     help="second judge model id "
                     f"(default: {DEFAULT_JUDGE_B})")
    run.add_argument("--judge-wait-reset", action="store_true",
                     help="when every judge candidate is rate-limited, sleep "
                     "until the next quota window (next UTC midnight) and "
                     "retry instead of failing; waits are recorded as "
                     "judge_a_waits/judge_b_waits in the verdict")
    run.add_argument("--judge-mode", default="conversation",
                     choices=("conversation", "per-turn"),
                     help="whole-conversation (one call, default) or "
                     "per-turn judging")
    run.add_argument("--judge-template", default=None,
                     help="judge prompt template "
                     "(default: conversation template, or per-turn "
                     "template with --judge-mode per-turn)")
    run.add_argument("--max-turns", type=int, default=None)
    run.add_argument("--no-cache", action="store_true")
    m = sub.add_parser("metrics", help="aggregate saved *.judge.json files")
    m.add_argument("--runs", required=True, help="directory of judge files")
    m.add_argument("--scenarios", default=None,
                   help="directory of scenario .json files (for meta)")
    m.add_argument("--out", default=None, help="write report JSON here")
    c = sub.add_parser(
        "calibrate",
        help="per-turn vs whole-conversation score agreement")
    c.add_argument("--per-turn", required=True,
                   help="directory of per-turn *.judge.json files")
    c.add_argument("--conversation", required=True,
                   help="directory of conversation-mode *.judge.json files")
    c.add_argument("--n", type=int, default=20,
                   help="max matched runs to compare (default: 20)")
    c.add_argument("--out", default=None, help="write report JSON here")
    k = sub.add_parser(
        "kappa-gate",
        help="judge-vs-human and inter-judge kappa vs a threshold")
    k.add_argument("--runs", required=True,
                   help="directory of *.judge.json files")
    k.add_argument("--labels", required=True,
                   help="hand-label CSV (run_id,turn,axis,score)")
    k.add_argument("--axis", default="A", choices=("A", "W", "R"),
                   help="axis to gate on (default: A)")
    k.add_argument("--min", type=float, default=0.6,
                   help="minimum kappa (default: 0.6)")
    s = sub.add_parser(
        "label-sheet",
        help="sample a blind hand-labelling HTML sheet")
    s.add_argument("--runs", required=True,
                   help="directory of *.judge.json files")
    s.add_argument("--n", type=int, default=50,
                   help="max (run, turn) items to sample (default: 50)")
    s.add_argument("--out", required=True, help="output HTML path")
    s.add_argument("--scenarios", default="bench/scenarios",
                   help="directory of scenario .json files (for meta)")
    s.add_argument("--seed", type=int, default=7,
                   help="sampling seed (default: 7)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        # --scenarios may be a directory of per-scenario files.
        if os.path.isdir(args.scenarios):
            files = sorted(str(p) for p in Path(args.scenarios).glob("*.json"))
            if not files:
                raise SystemExit(
                    f"riptide run: no .json files in {args.scenarios}")
            for f in files:
                sub_args = argparse.Namespace(**{**vars(args), "scenarios": f})
                cmd_run(sub_args)
            return 0
        return cmd_run(args)
    if args.command == "metrics":
        return cmd_metrics(args)
    if args.command == "calibrate":
        return cmd_calibrate(args)
    if args.command == "kappa-gate":
        return cmd_kappa_gate(args)
    if args.command == "label-sheet":
        from .label_sheet import build_sheet
        build_sheet(args.runs, args.scenarios, args.n, args.out,
                    args.seed)
        return 0
    raise SystemExit(f"unknown command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
