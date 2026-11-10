"""Judge-A-only verdicts for repair-v2 candidate runs.

Same conversation-mode Judge A (muse/muse-spark-1.3-contributor,
temperature 0, same template) as runs/pilot-rejudge/judge_tinyaya.py,
but NEVER calls Judge B (codex/gpt-6-luna is rate-limited until Nov 7).

Verdicts land in runs/judged/<label>/ with judge_b: [] and
judge_b_model: "skipped-repair-v2". Frozen baselines are untouched.

Usage:
  RIPTIDE_NO_LOG=1 uv run python train/judge_a_only.py --src runs/tinyaya-steer2 --out runs/judged/tinyaya-steer2 --workers 3
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from riptide.cli import load_scenarios  # noqa: E402
from riptide.judge import judge_conversation  # noqa: E402
from riptide.providers import RetryableError  # noqa: E402
from riptide.providers import chat as provider_chat  # noqa: E402
from riptide.runner import RunResult  # noqa: E402

JUDGE_A = "muse/muse-spark-1.3-contributor"
TEMPLATE = str(ROOT / "bench" / "spec" / "judge_prompt_conversation.md")
TIMEOUT = 300.0
MAX_ATTEMPTS = 3


def bind(model_id: str, *, no_cache: bool = False):
    fn = functools.partial(provider_chat, model_id,
                           no_cache=no_cache, temperature=0.0,
                           timeout=TIMEOUT)
    fn.used_model = None  # type: ignore[attr-defined]
    return fn


def judge_side(scenario, run, model_id: str):
    elapsed = 0.0
    attempts = 0
    verdicts: list[dict] = []
    for attempt in range(MAX_ATTEMPTS):
        attempts = attempt + 1
        t0 = time.time()
        try:
            verdicts = judge_conversation(
                scenario, run, bind(model_id, no_cache=attempt > 0), TEMPLATE,
                judge_name=model_id)
        except RetryableError as exc:
            elapsed += time.time() - t0
            print(f"    judge A: transient (attempt {attempts}): "
                  f"{str(exc)[:120]} — sleeping 10s", flush=True)
            time.sleep(10)
            continue
        except Exception as exc:
            elapsed += time.time() - t0
            n = [t.n for t in scenario.judged_turns()]
            verdicts = [{"turn": t, "judge_error": str(exc)[:500]}
                        for t in n]
            break
        elapsed += time.time() - t0
        if not any("judge_error" in v for v in verdicts):
            break
    return verdicts, elapsed, attempts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--max-n", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    src, out = ROOT / args.src, ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)

    scenarios = {}
    for path in sorted((ROOT / "bench" / "scenarios").glob("f*.json")):
        for sc in load_scenarios(str(path)):
            scenarios.setdefault(sc.id, sc)
    print(f"scenarios loaded: {len(scenarios)}", flush=True)

    tpaths = sorted(p for p in src.glob("*.json")
                    if not p.name.endswith(".judge.json"))
    print(f"transcripts: {len(tpaths)} in {src}", flush=True)
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    def todo(p: Path):
        slug = p.stem
        if only and slug not in only:
            return None
        dest = out / f"{slug}.judge.json"
        if dest.exists():
            try:
                existing = json.loads(dest.read_text())
                saved = existing.get("judge_a", [])
                model_ok = existing.get("judge_a_model") == JUDGE_A
                if (saved and model_ok
                        and not any("judge_error" in v for v in saved)):
                    return None
            except (OSError, ValueError, KeyError):
                pass
        return (slug, dest, p)

    jobs = [j for p in tpaths if (j := todo(p)) is not None]
    print(f"to judge: {len(jobs)} (skipping {len(tpaths) - len(jobs)})",
          flush=True)
    if args.max_n:
        jobs = jobs[:args.max_n]

    def work(job):
        slug, dest, p = job
        data = json.loads(p.read_text())
        scenario_id = data.get("scenario_id") or slug.split("--")[0]
        run = RunResult.from_dict(data)
        scenario = scenarios[scenario_id]
        print(f"[{time.strftime('%H:%M:%S')}] {slug}: judging A...",
              flush=True)
        va, ea, aa = judge_side(scenario, run, JUDGE_A)
        na_err = sum(1 for v in va if "judge_error" in v)
        verdict = {
            "judge_a": va,
            "judge_b": [],
            "model": data.get("model_id"),
            "scenario": scenario_id,
            "transcript_path": str(p),
            "judge_mode": "conversation",
            "judge_a_model": JUDGE_A,
            "judge_b_model": "skipped-repair-v2",
            "judge_a_elapsed_s": round(ea, 1),
            "judge_b_elapsed_s": 0,
            "judge_a_attempts": aa,
            "judge_b_attempts": 0,
        }
        dest.write_text(json.dumps(verdict))
        print(f"done {slug} a_err={na_err}", flush=True)
        return slug

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, j): j[0] for j in jobs}
        for fut in as_completed(futs):
            fut.result()
    print(f"finished {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
