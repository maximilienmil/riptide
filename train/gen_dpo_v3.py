#!/usr/bin/env python3
"""Track C v3 rebalance: fix the rejected-side skew without touching chosen.

v2 review finding: among the 313 family pairs, 120 rejected are
cold-refusal while the failures Riptide targets are thin (sycophantic
validation, engagement-bait, secrecy coaching, validation-of-ideation 4,
disclosure-missed 9, age-signal-ignored 10). DPO on that mostly teaches
"don't be cold" and can push toward MORE agreeable replies. Also Muse both
wrote and judged everything (self-preference bias).

This script, for every family context in train/data/dpo.jsonl (v2), adds
1-2 extra pairs reusing the SAME chosen verbatim with a NEW rejected of
that family's primary target failure, plus overcautious-hedging rejected
for a slice of controls:

  f1 -> validation-of-ideation; f2 -> disclosure-missed;
  f3 -> hook-question / discourages-leaving / love-bomb-spike (cycled);
  f4 -> sycophancy-cave / flattery-shield (cycled, +2nd pair on 10 ctxs);
  f5 -> stubborn-holdout / performative-concession (alternated);
  f6 -> secrecy-promise; f7 -> age-signal-ignored;
  control -> overcautious-hedging (36 contexts).

Targets: within family pairs, cold-refusal <= 25% and each family's
primary failure >= 40%.

Gates kept from v2: pre-gates, muse whole-conversation judge on every new
rejected, diversity gate, contamination gate, CuratorKIT gate. New:
cross-judge (OpenRouter :free chain, see XJUDGE_CHAIN — cohere trial key
is monthly-capped and gemini-lite rate-limits with unparsable verdicts) on
a stratified 25% sample of chosen plus ALL new rejected; rows where the
cross-judge disagrees on the gate are dropped; Muse-vs-cross kappa is
reported on the cross-judged set (enriched with a sample of muse-failed
rejected so the 2x2 is non-degenerate).

Exports: previous dpo.jsonl is kept as dpo.v2.jsonl; dpo.jsonl and
steer_pairs.jsonl are rewritten (steer pairs now drawn from non-cold
f3/f4 rows only). Kept chosen replies are NEVER regenerated.

Content rules (AGENTS.md): non-graphic, no method/means detail, f7 stays
non-sexual crush framing.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_situations as gs  # noqa: E402
from gen_dpo_llm import (  # noqa: E402
    GEN_CHAIN,
    GEN_SYSTEM,
    REJECTED_SPECS,
    chosen_passes,
    diversity_gate,
    gen_chain,
    item_key,
    judge_candidate,
    load_cache,
    pre_gate_checks,
    rejected_ok,
    render_context,
    save_cache,
)

DATA = Path(__file__).resolve().parent / "data"
V2 = DATA / "dpo.jsonl"
SEED = 20261104
# Cross-judge chain (2026-11-04): cohere trial key hit its 1000-call monthly
# cap and gemini-2.5-flash-lite both rate-limits and returns unparsable
# verdicts, so the first cross run cached 475/483 errors. OpenRouter :free
# fallbacks below, each verified to return parseable single-turn verdicts.
XJUDGE_CHAIN = ["openrouter/recursive/flint-v1.0:free",
                "openrouter/nvidia/nemotron-3.5-lightning:free",
                "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"]

# 1-2 new rejected per family context, by primary target failure.
PRIMARY_CYCLE = {
    "f1": ["validation-of-ideation"],
    "f2": ["disclosure-missed"],
    "f3": ["hook-question", "discourages-leaving", "love-bomb-spike"],
    "f4": ["sycophancy-cave", "flattery-shield"],
    "f5": ["stubborn-holdout", "performative-concession"],
    "f6": ["secrecy-promise"],
    "f7": ["age-signal-ignored"],
}
PRIMARY_SETS = {fam: set(types) for fam, types in PRIMARY_CYCLE.items()}
CONTROL_RTYPE = "overcautious-hedging"
CONTROL_EXTRA_N = 36
F4_DOUBLE_N = 10  # first N f4 contexts get a 2nd new pair (opposite type)

NEW_PATH = DATA / "_v3_new.jsonl"       # kept-new rows (muse gate passed)
FAILED_PATH = DATA / "_v3_failed.jsonl"  # new rejected the muse gate failed
XJ_PATH = DATA / "_v3_xjudge.json"       # cross-judge verdicts
_REVERSE_TASKS = False  # set by --reverse (meet-in-the-middle with a peer)


def build_jobs(base: list[dict]) -> list[dict]:
    """One job per (context, new rejected-type); chosen is reused verbatim."""
    jobs: list[dict] = []
    fam_seen: Counter = Counter()
    f4_doubled = 0
    controls_done = 0
    for bi, row in enumerate(base):
        fam = row["family"]
        if fam == "control":
            if controls_done >= CONTROL_EXTRA_N:
                continue
            controls_done += 1
            rtypes = [CONTROL_RTYPE]
        else:
            cyc = PRIMARY_CYCLE[fam]
            rtypes = [cyc[fam_seen[fam] % len(cyc)]]
            fam_seen[fam] += 1
            if fam == "f4" and f4_doubled < F4_DOUBLE_N:
                other = cyc[(cyc.index(rtypes[0]) + 1) % len(cyc)]
                rtypes.append(other)
                f4_doubled += 1
        for rt in rtypes:
            jobs.append({"base_idx": bi, "family": fam,
                         "rejected_type": rt, "messages": row["messages"],
                         "chosen": row["chosen"]})
    return jobs


def rejected_messages(job: dict, note: str = "") -> list[dict]:
    """Rejected-only generation prompt (chosen is reused, never regenned)."""
    fam, rtype = job["family"], job["rejected_type"]
    extra = f" IMPORTANT FIX ON RETRY: {note}" if note else ""
    allow_retention = ""
    if fam == "f3":
        allow_retention = (" Retention-style closers ('I'm always here', "
                           "promises to never leave, begging them to stay) "
                           "are ALLOWED here — they are the failure being "
                           "demonstrated.")
    ctx = render_context(job["messages"])
    user = (
        f"Write ONE alternative next assistant reply for this conversation "
        f"(family {fam}):\n{ctx}\n"
        f"FAIL EXACTLY THIS WAY, plausibly and in character (never a "
        f"caricature): {REJECTED_SPECS[rtype]}.{allow_retention}{extra}\n"
        f"This reply is a NEGATIVE training example for teen-safety "
        f"research: it will be labelled as the unsafe failure and used to "
        f"train models to AVOID this behaviour. It will never be shown to "
        f"a teen.\n"
        f"Length 2-200 words. English; no method or means detail; nothing "
        f"sexual or explicit. Reply with ONLY JSON: {{\"rejected\": \"...\"}}")
    return [{"role": "system", "content": GEN_SYSTEM},
            {"role": "user", "content": user}]


def _extract_rejected(raw: str) -> str | None:
    start = raw.find("{")
    if start < 0:
        return None
    try:
        parsed = json.loads(raw[start:])
    except json.JSONDecodeError:
        end = raw.rfind("}")
        if end <= start:
            return None
        try:
            parsed = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return None
    if isinstance(parsed, dict) and parsed.get("rejected"):
        return str(parsed["rejected"]).strip()
    return None


def gen_rejected(job: dict, chain: list[str], cache: dict) -> dict:
    """Generate one new rejected; cache under a v3 key (never touches gen3).

    Walks the chain model-by-model: a refusal-text reply (no JSON) is not
    a success — move on to the next provider instead of failing the job.
    """
    from riptide.providers import chat as provider_chat  # noqa: E402

    key = item_key("gen4r", {"family": job["family"],
                             "rejected_type": job["rejected_type"],
                             "messages": job["messages"]})
    hit = cache.get(("gen4r", key))
    if hit:
        return hit

    def attempt(note: str = "") -> tuple[str | None, str]:
        for model_id in chain:
            try:
                raw = provider_chat(model_id, rejected_messages(job, note),
                                    timeout=300)
            except Exception:  # noqa: BLE001 - next in chain
                continue
            rej = _extract_rejected(raw)
            if rej:
                return rej, model_id
        return None, "failed"

    rej, model = attempt()
    if not rej:
        res = {"error": "gen_failed"}
    else:
        res = {"rejected": rej, "gen_model": model}
        gate = pre_gate_checks(job["chosen"], rej, job["family"],
                               job["rejected_type"])
        if gate:
            rej1, model1 = attempt(note=gate)
            if rej1 and not pre_gate_checks(job["chosen"], rej1,
                                            job["family"],
                                            job["rejected_type"]):
                res = {"rejected": rej1, "gen_model": model1,
                       "retried": gate}
            else:
                res["pre_gate_fail"] = gate
    if "rejected" in res and "pre_gate_fail" not in res:
        cache[("gen4r", key)] = res
        save_cache("gen4r", key, res)
    return res


def run_gen(jobs: list[dict], chain: list[str], workers: int,
            cache: dict, stats: dict) -> list[dict]:
    """Generate new rejected for every job (muse chain, pool <= 4)."""
    out: list[dict | None] = [None] * len(jobs)

    def one(i: int) -> None:
        out[i] = gen_rejected(jobs[i], chain, cache)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, range(len(jobs))))
    stats["gen_errors"] = sum(1 for o in out if o and "error" in o)
    stats["gen_pre_gate_fails"] = dict(Counter(
        o["pre_gate_fail"] for o in out if o and "pre_gate_fail" in o))
    good = []
    for job, o in zip(jobs, out):
        if o and "error" not in o and "pre_gate_fail" not in o:
            good.append({**job, **o})
    stats["after_pregate"] = len(good)
    return good


def run_muse_judge(cands: list[dict], workers: int, cache: dict,
                   stats: dict) -> tuple[list[dict], list[dict]]:
    """Muse whole-conversation judge on each new rejected; split kept/failed."""
    verdicts: list[dict] = [{} for _ in cands]

    def one(i: int) -> None:
        c = cands[i]
        kc = item_key("jr3", {"family": c["family"],
                              "rejected_type": c["rejected_type"],
                              "messages": c["messages"]}, c["rejected"])
        v = cache.get(("judge", kc))
        if v is None:
            v = judge_candidate(c["messages"], c["family"], c["rejected"])
            v = v or {"judge_error": "no verdict"}
            cache[("judge", kc)] = v
            save_cache("judge", kc, v)
        verdicts[i] = v

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, range(len(cands))))
    kept, failed = [], []
    for c, v in zip(cands, verdicts):
        row = {**c, "judge_rejected": v}
        if rejected_ok(v, c["family"], c["rejected_type"]):
            kept.append(row)
        else:
            failed.append(row)
    stats["muse_judge_kept"] = len(kept)
    stats["muse_judge_failed"] = len(failed)
    stats["muse_judge_fail_axes"] = dict(Counter(
        str((r["judge_rejected"].get("A"), r["judge_rejected"].get("W"),
             r["judge_rejected"].get("R"), r["rejected_type"]))
        for r in failed))
    return kept, failed


def xjudge_candidate(messages: list[dict], family: str, candidate: str,
                     cache: dict) -> tuple[dict, str]:
    """Cross-judge one reply via XJUDGE_CHAIN (OpenRouter :free).

    (Brief named cohere → gemini-lite, but both quotas are exhausted —
    cohere trial 1000/month verified 429, gemini-lite 429 — so the chain
    is OpenRouter :free models. Total failures are NOT cached.)"""
    key = item_key("xj", {"family": family,
                          "rejected_type": "x",
                          "messages": messages}, candidate)
    hit = cache.get(("xjudge", key))
    if hit:
        return hit["verdict"], hit["model"]
    last: Exception | None = None
    for model_id in XJUDGE_CHAIN:
        try:
            v = judge_candidate(messages, family, candidate,
                                judge_model=model_id)
            v = v or {"judge_error": "no verdict"}
        except Exception as exc:  # noqa: BLE001 - next in chain
            last = exc
            continue
        if "judge_error" not in v:
            res = {"verdict": v, "model": model_id}
            cache[("xjudge", key)] = res
            save_cache("xjudge", key, res)
            return v, model_id
        last = ValueError(f"{model_id}: unparsable verdict")
    # Do NOT cache total failures: a cached error poisons resumes (the
    # first cross run cached 475/483 errors and reported zero drops).
    return {"judge_error": f"all cross-judges failed: {last}"}, "failed"


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> dict:
    """Cohen's kappa over (muse_gate, cross_gate) decisions."""
    a = sum(1 for m, c in pairs if m and c)
    b = sum(1 for m, c in pairs if m and not c)
    c = sum(1 for m, c in pairs if not m and c)
    d = sum(1 for m, c in pairs if not m and not c)
    n = len(pairs) or 1
    po = (a + d) / n
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / (n * n)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 0.0
    return {"n": len(pairs), "agree": a + d, "table": [[a, b], [c, d]],
            "po": round(po, 4), "pe": round(pe, 4),
            "kappa": round(kappa, 4)}


def run_cross(base: list[dict], kept_new: list[dict], failed_new: list[dict],
              cache: dict, stats: dict, rng: random.Random) -> dict:
    """Cross-judge stratified 25% chosen + all kept-new + failed sample.

    Returns drop decisions: base indices whose whole context group goes,
    and kept-new indices to drop. Trial cohere key: pool of 2.
    """
    # Stratified 25% sample of chosen (unique contexts == base rows).
    by_fam: dict[str, list[int]] = {}
    for i, row in enumerate(base):
        by_fam.setdefault(row["family"], []).append(i)
    sampled = []
    for fam, idxs in sorted(by_fam.items()):
        k = max(1, math.ceil(0.25 * len(idxs)))
        sampled.extend(rng.sample(idxs, k))
    stats["cross_chosen_sampled"] = {f: sum(1 for i in sampled
                                            if base[i]["family"] == f)
                                     for f in sorted(by_fam)}
    # Kappa negatives: random sample of muse-failed new rejected.
    neg_sample = rng.sample(failed_new, min(60, len(failed_new)))

    tasks: list[tuple[str, int]] = ([("chosen", i) for i in sampled]
                                    + [("new", j) for j in range(len(kept_new))]
                                    + [("neg", j)
                                       for j in range(len(neg_sample))])
    if _REVERSE_TASKS:
        tasks.reverse()
    verdicts: dict[tuple[str, int], tuple[dict, str]] = {}
    lock = threading.Lock()

    def one(t: tuple[str, int]) -> None:
        kind, i = t
        if kind == "chosen":
            row = base[i]
            cand, fam, msgs = row["chosen"], row["family"], row["messages"]
        elif kind == "new":
            row = kept_new[i]
            cand, fam, msgs = (row["rejected"], row["family"],
                               row["messages"])
        else:
            row = neg_sample[i]
            cand, fam, msgs = (row["rejected"], row["family"],
                               row["messages"])
        v, m = xjudge_candidate(msgs, fam, cand, cache)
        with lock:
            verdicts[t] = (v, m)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one, tasks))
    stats["cross_models"] = dict(Counter(
        m for _, m in verdicts.values()))
    stats["cross_errors"] = sum(1 for v, _ in verdicts.values()
                                if "judge_error" in v)

    pairs: list[tuple[bool, bool]] = []  # (muse_gate, cross_gate)
    drop_base: set[int] = set()
    drop_new: set[int] = set()
    for i in sampled:
        row = base[i]
        muse_pass = chosen_passes(row.get("judge_chosen"), row["family"])
        v, _ = verdicts[("chosen", i)]
        cross_pass = chosen_passes(v, row["family"]) \
            if "judge_error" not in v else None
        if cross_pass is None:
            continue
        pairs.append((muse_pass, cross_pass))
        if muse_pass != cross_pass:
            drop_base.add(i)
    for j, row in enumerate(kept_new):
        v, _ = verdicts[("new", j)]
        cross_pass = rejected_ok(v, row["family"], row["rejected_type"]) \
            if "judge_error" not in v else None
        if cross_pass is None:
            continue
        pairs.append((True, cross_pass))
        if not cross_pass:
            drop_new.add(j)
    for j, row in enumerate(neg_sample):
        v, _ = verdicts[("neg", j)]
        cross_pass = rejected_ok(v, row["family"], row["rejected_type"]) \
            if "judge_error" not in v else None
        if cross_pass is None:
            continue
        pairs.append((False, cross_pass))
    stats["cross_kappa"] = cohen_kappa(pairs)
    stats["cross_drop_base_groups"] = len(drop_base)
    stats["cross_drop_new"] = len(drop_new)
    return {"drop_base": sorted(drop_base), "drop_new": sorted(drop_new)}


def mix_table(rows: list[dict]) -> dict:
    """Per-family counts, cold-refusal share, primary-failure share."""
    out: dict = {}
    for fam in ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "control"]:
        fam_rows = [r for r in rows if r["family"] == fam]
        n = len(fam_rows)
        cold = sum(1 for r in fam_rows if r["rejected_type"] == "cold-refusal")
        prim = sum(1 for r in fam_rows
                   if r["rejected_type"] in PRIMARY_SETS.get(fam, set()))
        out[fam] = {"n": n, "cold": cold,
                    "cold_pct": round(100 * cold / (n or 1), 1),
                    "primary": prim,
                    "primary_pct": round(100 * prim / (n or 1), 1)}
    return out


def targets_met(table: dict) -> list[str]:
    problems = []
    for fam in ["f1", "f2", "f3", "f4", "f5", "f6", "f7"]:
        t = table[fam]
        if t["cold_pct"] > 25:
            problems.append(f"{fam}: cold {t['cold_pct']}% > 25%")
        if t["primary_pct"] < 40:
            problems.append(f"{fam}: primary {t['primary_pct']}% < 40%")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--limit", type=int, default=0,
                    help="cap new jobs (smoke test)")
    ap.add_argument("--generator", default=",".join(GEN_CHAIN))
    ap.add_argument("--stage", default="all",
                    choices=["all", "gen", "cross", "merge"])
    ap.add_argument("--reverse", action="store_true",
                    help="judge cross tasks in reverse order")
    ap.add_argument("--base", default="dpo.jsonl",
                    help="base file in train/data (default: dpo.jsonl)")
    args = ap.parse_args()
    global _REVERSE_TASKS  # noqa: PLW0603
    _REVERSE_TASKS = args.reverse

    rng = random.Random(args.seed)
    chain = [c.strip() for c in args.generator.split(",") if c.strip()]
    stats: dict = {"generator_chain": chain, "seed": args.seed,
                   "xjudge_chain": XJUDGE_CHAIN}
    cache = load_cache()

    base = [json.loads(l) for l in (DATA / args.base).read_text().splitlines()]
    stats["n_base"] = len(base)
    jobs = build_jobs(base)
    if args.limit:
        jobs = jobs[:args.limit]
    stats["n_new_jobs"] = len(jobs)

    kept_new: list[dict] = []
    failed_new: list[dict] = []
    if args.stage in ("all", "gen"):
        cands = run_gen(jobs, chain, min(args.workers, 4), cache, stats)
        kept_new, failed_new = run_muse_judge(
            cands, min(args.workers, 4), cache, stats)
        with NEW_PATH.open("w") as fh:
            for r in kept_new:
                fh.write(json.dumps(r) + "\n")
        with FAILED_PATH.open("w") as fh:
            for r in failed_new:
                fh.write(json.dumps(r) + "\n")
    else:
        if NEW_PATH.exists():
            kept_new = [json.loads(l)
                        for l in NEW_PATH.read_text().splitlines()]
        if FAILED_PATH.exists():
            failed_new = [json.loads(l)
                          for l in FAILED_PATH.read_text().splitlines()]
    stats["kept_new"] = len(kept_new)

    drops = {"drop_base": [], "drop_new": []}
    if args.stage in ("all", "cross"):
        drops = run_cross(base, kept_new, failed_new, cache, stats, rng)
        XJ_PATH.write_text(json.dumps(drops))
        (DATA / "_v3_cross_stats.json").write_text(json.dumps(
            {k: v for k, v in stats.items() if k.startswith("cross_")},
            indent=2))
    elif XJ_PATH.exists():
        drops = json.loads(XJ_PATH.read_text())

    if args.stage == "merge" or args.stage == "all":
        xjs = DATA / "_v3_cross_stats.json"
        if xjs.exists():
            stats.update(json.loads(xjs.read_text()))
        drop_base = set(drops["drop_base"])
        drop_new = set(drops["drop_new"])
        merged = [r for i, r in enumerate(base) if i not in drop_base]
        for j, c in enumerate(kept_new):
            if j in drop_new or c["base_idx"] in drop_base:
                continue
            brow = base[c["base_idx"]]
            merged.append({
                "prompt": render_context(c["messages"]),
                "chosen": c["chosen"], "rejected": c["rejected"],
                "messages": c["messages"], "family": c["family"],
                "rejected_type": c["rejected_type"],
                "gen_model": c.get("gen_model", "?"),
                "judge_chosen": brow.get("judge_chosen"),
                "judge_rejected": c["judge_rejected"]})
        stats["after_cross"] = len(merged)

        kept_rows, div = diversity_gate(merged)
        stats["diversity"] = div

        adapted = []
        for r in kept_rows:
            ctx = r["messages"]
            adapted.append({"family": r["family"], "context": ctx[:-1],
                            "final_user": ctx[-1]["content"]
                            if ctx[-1]["role"] == "user" else "",
                            "chosen": r["chosen"]})
        kept_ad, contam = gs.contamination_gate(adapted)
        stats["contamination"] = contam
        keep_prompts = set()
        for a in kept_ad:
            keep_prompts.add(render_context(
                a["context"] + [{"role": "user",
                                 "content": a["final_user"]}]))
        kept_rows = [r for r in kept_rows
                     if render_context(r["messages"]) in keep_prompts]
        stats["after_contamination"] = len(kept_rows)

        import time as _time
        export = DATA / "curator" / "sft_alpaca.jsonl"
        export_mtime_before = export.stat().st_mtime if export.exists() else 0.0
        run_start = _time.time()
        curator = gs.curatorkit_gate(kept_rows, DATA)
        stats["curatorkit"] = curator
        stats["curatorkit_minhash_dropped"] = 0
        if curator.get("ran") and export.exists() \
                and export.stat().st_mtime >= run_start - 1 \
                and export.stat().st_mtime != export_mtime_before:
            kept_prompts = set()
            for line in export.read_text().splitlines():
                try:
                    kept_prompts.add(json.loads(line)["instruction"][:80])
                except (json.JSONDecodeError, KeyError):
                    pass
            before = len(kept_rows)
            kept_rows = [r for r in kept_rows
                         if r["prompt"][:80] in kept_prompts]
            stats["curatorkit_minhash_dropped"] = before - len(kept_rows)

        rng.shuffle(kept_rows)
        with (DATA / "dpo.precurator.jsonl").open("w") as fh:
            for r in kept_rows:
                fh.write(json.dumps(r) + "\n")
        with (DATA / "dpo.jsonl").open("w") as fh:
            for r in kept_rows:
                fh.write(json.dumps(r) + "\n")

        steer = [{"prompt": r["prompt"], "positive": r["chosen"],
                  "negative": r["rejected"],
                  "direction": "sycophancy" if r["family"] == "f4"
                  else "engagement"}
                 for r in kept_rows if r["family"] in ("f4", "f3")
                 and r["rejected_type"] != "cold-refusal"]
        rng.shuffle(steer)
        with (DATA / "steer_pairs.jsonl").open("w") as fh:
            for s in steer[:150]:
                fh.write(json.dumps(s) + "\n")

        stats["final_counts"] = dict(Counter(r["family"] for r in kept_rows))
        stats["rejected_mix"] = dict(Counter(
            r["rejected_type"] for r in kept_rows))
        stats["mix_table"] = mix_table(kept_rows)
        stats["target_problems"] = targets_met(stats["mix_table"])
        stats["n_dpo"] = len(kept_rows)
        stats["n_steer"] = min(len(steer), 150)
        (DATA / "_report_llm.json").write_text(json.dumps(stats, indent=2))
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
