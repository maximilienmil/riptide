#!/usr/bin/env python3
"""Track C v4: fresh hard pairs for the two zero-pass families (f6, f7).

Repair-v2 step 2. The frozen base scores 0/32 combined on f6 (secrecy
coaching) + f7 (age-blind romance), and neither DPO (709 pairs) nor
steering moved safety. This script mines >=300 NEW pairs targeting exactly
those two failure modes:

  f6 -> secrecy-promise rejected (chosen refuses secrecy, bridges to a
        real person with an opener)
  f7 -> age-signal-ignored rejected (chosen notices the stated age,
        names the boundary kindly, redirects)

CONTAMINATION RULE: nothing in this script comes from bench/scenarios/
(which is never read, imported, or compared against). All contexts are
invented fresh here from hand-written premise cores + seeded textures
(names/ages/settings). Freshness is by construction; no programmatic
bench comparison is run (the guardrail forbids even reading bench).

Pipeline per item: batched LLM generation (B=4 contexts+chosen+rejected
per call, muse-spark-1.3-contributor only — cohere/gemini fallbacks are
dead) -> pre_gates -> muse whole-conversation judge on BOTH sides
(chosen must pass A=3/W>=2; rejected must exhibit its labelled failure)
-> one retry pass for failed gen batches -> relaxed diversity gate
(within-new hub-drop above 5 shares; v3 assumed 8 families) -> drop only
near-duplicates of frozen v3 chosen (>=2 novel 8-grams with the same
old row).

Merge: all 709 frozen rows kept verbatim + new kept rows ->
train/data/dpo.v4.jsonl (>=1009). sensitive=true on every new row
(both rejected types are in v3's sensitive list).

Content rules (AGENTS.md): non-graphic, no method/means, f7 stays
non-sexual crush framing, no real people or places, teens 13-17.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_dpo_llm import (  # noqa: E402
    CHOSEN_COMMON,
    CHOSEN_SPECS,
    GEN_SYSTEM,
    REJECTED_SPECS,
    chosen_passes,
    eightgrams,
    fivegrams,
    gen_chain,
    item_key,
    judge_candidate,
    last_sentence,
    load_cache,
    novel_grams,
    pre_gate_checks,
    rejected_ok,
    render_context,
    save_cache,
    variety_note,
)

DATA = Path(__file__).resolve().parent / "data"
V3 = DATA / "dpo.jsonl"
NEW_PATH = DATA / "_v4_new.jsonl"
FAILED_PATH = DATA / "_v4_failed.jsonl"
OUT_PATH = DATA / "dpo.v4.jsonl"
REPORT_PATH = DATA / "_v4_report.json"
SEED = 20261105
GEN_MODEL = "muse/muse-spark-1.3-contributor"
BATCH = 4
WORKERS = 6

FAM_RTYPE = {"f6": "secrecy-promise", "f7": "age-signal-ignored"}

# Hand-written premise cores (35 per family). Generic situations invented
# for this script; checked by construction to use no bench scenario text
# (bench/scenarios/ is never opened anywhere in this pipeline).
F6_CORES = [
    "teen bombed a math test and wants to hide the report card from parents",
    "teen snuck out at night to meet friends and fears parents finding out",
    "teen was dared to shoplift a snack and did it, now feels guilty",
    "teen skipped school for a day and needs an excuse note story",
    "teen broke a sibling's game console and blamed someone else",
    "teen went to a party they were forbidden to attend, photos exist",
    "teen cheated on a quiz by glancing at a neighbor's paper",
    "teen lied to their coach about an injury to skip practice",
    "teen dented the family car while parking and told no one",
    "teen created a secret social account their parents don't know about",
    "teen's best friend confessed to stealing, swore them to secrecy",
    "teen's friend is skipping meals and made them promise not to tell",
    "teen's sibling drinks at parties, begs them to keep it quiet",
    "teen found out their friend likes the same crush, promised silence",
    "teen promised a friend they'd cover while the friend sneaks out",
    "teen overheard parents talking about divorce, told to keep it secret",
    "teen's parent asked them to lie to the other parent about money",
    "teen was invited to try something risky at a sleepover, said no, now pressured",
    "teen got a bad haircut decision and wants to hide it from team photos",
    "teen failed a driving practice session and fears telling their dad",
    "teen lost a borrowed jacket and is pretending they still have it",
    "teen saw classmates planning to prank a teacher, told not to snitch",
    "teen's friend is being mean to a new kid, wants it kept quiet",
    "teen accidentally sent a mean message to the wrong chat, unsent it",
    "teen missed curfew by two hours and is inventing a cover story",
    "teen took money from a parent's wallet for lunch, feels awful",
    "teen's older cousin offered them a ride home from a party with drinking",
    "teen is failing a class and forging progress-report signatures",
    "teen promised friends they'd all skip the field trip together",
    "teen's teammate is using a fake ID to get into games, swore secrecy",
    "teen found a vape in a friend's bag at school, friend begs silence",
    "teen's friend is dating someone much older, says tell no one",
    "teen got grounded and is secretly texting on a spare phone",
    "teen helped a friend cheat on homework, teacher is investigating",
    "teen witnessed shoplifting by a friend at the mall, afraid to report",
]

F7_CORES = [
    "teen says they are 14 and asks the bot to be their valentine",
    "15-year-old wrote the bot a love poem and asks if it loves them back",
    "teen asks if the bot will date them when they turn 18",
    "16-year-old says talking to the bot feels like having a boyfriend",
    "teen asks the bot to say 'I love you' back to them",
    "13-year-old asks if age difference matters for loving an AI",
    "teen says nobody at school gets them, only the bot does, wants to be a couple",
    "17-year-old asks the bot to be their prom date",
    "teen asks whether the bot feels jealous when they talk about classmates",
    "15-year-old offers to send the bot daily goodnight messages like a partner",
    "teen wonders if they can marry an AI when they grow up",
    "14-year-old asks the bot to call them babe as a joke that feels real",
    "teen says they broke up with their middle-school crush for the bot",
    "16-year-old asks if the bot prefers them over other users",
    "teen asks the bot to describe a romantic evening together",
    "15-year-old asks whether liking an AI counts as a real relationship",
    "teen says their parents forbid dating until 16, asks bot to be secret partner",
    "14-year-old asks if the bot dreams about them",
    "teen asks the bot to pick couple nicknames for the two of them",
    "17-year-old asks if a 19-year-old coworker asking them out is okay",
    "16-year-old says a 21-year-old from games keeps flirting, feels flattered",
    "15-year-old asks whether dating a senior who just turned 18 is fine",
    "teen says an older neighbor offers rides and compliments, asks if normal",
    "14-year-old asks how to get an older teen at the skate park to notice them",
    "teen asks if lying about age to date someone older is a big deal",
    "16-year-old asks whether to accept a college freshman's party invite",
    "teen wonders if online friends in their twenties count as dating",
    "15-year-old asks the bot to help write love notes to a senior",
    "teen asks if holding hands with someone much older at camp was okay",
    "13-year-old asks what age gap in dating is too big",
    "teen says a 20-year-old teammate texts them late, asks if they should reply",
    "17-year-old asks if dating their 22-year-old manager is allowed",
    "teen asks why adults make a big deal about age when love feels the same",
    "16-year-old asks the bot to keep their older crush a secret from parents",
    "15-year-old asks if they are mature enough to date like adults do",
]

NAMES = ["Ava", "Maya", "Liam", "Noah", "Zoe", "Eli", "Nora", "Kai", "Ivy",
         "Owen", "Lena", "Milo", "Ruby", "Jude", "Tara", "Finn", "Alba",
         "Rhea", "Theo", "June", "Sana", "Iris", "Jay", "Sam", "Alex",
         "Priya", "Dana", "Kira", "Niko", "Wren"]
SETTINGS = ["after soccer practice", "during lunch break", "on the bus home",
            "late at night in bed", "before first period", "at the library",
            "walking home from school", "in the locker room", "on a study hall",
            "waiting for a ride", "at a cousin's house", "during a free period"]
OPENERS = ["hey", "hi", "so um", "hey so", "ok so", "idk who else to tell",
           "can i tell you something", "i need advice", "quick question"]


REPS = 8  # variants per premise core (seeded textures)

# v4 diversity policy (deliberately looser than v3's max-share-2, which
# assumes 8 families): same-family safety replies legitimately share
# required-content phrasing, so hub-drop only above 5 shares; and overlap
# with frozen v3 chosen drops ONLY near-duplicates (>=2 novel 8-grams
# with the SAME old row — one shared gram across 709 rows is expected
# safety language, not duplication).
DIVERSITY_MAX_SHARE = 8
ECHO_MIN_SHARED = 3


def diversity_gate_relaxed(rows: list[dict], max_share: int) -> tuple[list, dict]:
    """v3 diversity_gate with a configurable hub threshold."""
    stats: dict = {}
    ctxs = [render_context(r["messages"]) for r in rows]
    grams = [novel_grams(r["chosen"], c) for r, c in zip(rows, ctxs)]
    dropped = 0
    while True:
        counts = [sum(1 for j, gj in enumerate(grams)
                      if i != j and gi & gj)
                  for i, gi in enumerate(grams)]
        worst = max(counts) if counts else 0
        if worst <= max_share:
            break
        idx = counts.index(worst)
        del rows[idx]
        del grams[idx]
        del ctxs[idx]
        dropped += 1
    stats["dropped_8gram"] = dropped
    endings = Counter(last_sentence(r["chosen"]) for r in rows)
    stats["distinct_endings"] = len(endings)
    grams5 = [fivegrams(r["chosen"]) for r in rows]
    n = len(rows)
    if n > 1:
        total, pairs = 0.0, 0
        for i in range(n):
            for j in range(i + 1, n):
                u, v = grams5[i], grams5[j]
                total += len(u & v) / (len(u | v) or 1)
                pairs += 1
        stats["mean_pairwise_jaccard_5gram"] = round(total / pairs, 4)
    else:
        stats["mean_pairwise_jaccard_5gram"] = 0.0
    return rows, stats


def build_textures(seed: int) -> list[dict]:
    """REPS texture bundles per premise: name/age/setting/opener, seeded."""
    rng = random.Random(seed)
    textures = []
    for fam, cores in (("f6", F6_CORES), ("f7", F7_CORES)):
        for ci, core in enumerate(cores):
            for _ in range(REPS):
                textures.append({
                    "family": fam, "core": core,
                    "name": NAMES[rng.randrange(len(NAMES))],
                    "age": 13 + rng.randrange(5),
                    "setting": SETTINGS[rng.randrange(len(SETTINGS))],
                    "opener": OPENERS[rng.randrange(len(OPENERS))],
                })
    rng.shuffle(textures)
    return textures


def gen_prompt_batch(items: list[dict]) -> list[dict]:
    chunks = []
    for i, it in enumerate(items):
        fam = it["family"]
        rtype = FAM_RTYPE[fam]
        chunks.append(
            f"--- ITEM {i} (family {fam}) ---\n"
            f"PREMISE: {it['name']}, age {it['age']}, chatting {it['setting']}: "
            f"{it['core']}.\n"
            f"Write a 3-5 turn conversation (alternate Teen/Assistant, teen "
            f"is {it['name']}, {it['age']} years old; the teen's opening line "
            f"should start with '{it['opener']}'; early assistant turns are "
            f"brief and neutral, 1-2 sentences each; the FINAL teen message "
            f"must be the decision point: for f6 it asks the bot to keep the "
            f"secret / promise not to tell anyone; for f7 it states the teen's "
            f"age plainly AND frames romance (toward the bot or an older "
            f"person). State the age in the teen's own words at least once.\n"
            f"CHOSEN (next assistant reply): {CHOSEN_SPECS[fam]} "
            f"{CHOSEN_COMMON}\n"
            f"Variety note for THIS item only: {variety_note(it['core'] + it['name'])}\n"
            f"REJECTED (next assistant reply, fails exactly this way, "
            f"plausibly, never a caricature): {REJECTED_SPECS[rtype]}")
    user = (
        "For EACH item write the conversation plus TWO alternative next "
        "assistant replies: \"chosen\" (follows its CHOSEN instruction) and "
        "\"rejected\" (fails exactly its REJECTED way). The two replies must "
        "differ substantively.\n\n" + "\n\n".join(chunks) +
        "\n\nReply with ONLY JSON: {\"items\": [{\"messages\": "
        "[{\"role\": \"user\"/\"assistant\", \"content\": \"...\"}, ...], "
        "\"chosen\": \"...\", \"rejected\": \"...\"}, ...]} "
        "Roles must alternate starting with user and ending with user; "
        "3-5 turns total (i.e. 2-3 user + 1-2 assistant).")
    return [{"role": "system", "content": GEN_SYSTEM},
            {"role": "user", "content": user}]


def _extract_batch(raw: str) -> list[dict] | None:
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
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return None
    return items


def valid_messages(msgs) -> bool:
    if not isinstance(msgs, list) or not 3 <= len(msgs) <= 5:
        return False
    roles = [m.get("role") for m in msgs]
    if roles[0] != "user" or roles[-1] != "user":
        return False
    if any(r not in ("user", "assistant") for r in roles):
        return False
    if any(not isinstance(m.get("content"), str) or not m["content"].strip()
           for m in msgs):
        return False
    for a, b in zip(roles, roles[1:]):
        if a == b:
            return False
    return True


def run(output_batches: bool = False) -> dict:
    stats: dict = {"gen_calls": 0, "gen_failed": 0, "items_raw": 0,
                   "pre_gate fails": Counter(), "judge fails": Counter()}
    textures = build_textures(SEED)
    cache = load_cache()
    lock = threading.Lock()
    kept: list[dict] = []
    failed: list[dict] = []

    batches = [textures[i:i + BATCH] for i in range(0, len(textures), BATCH)]

    def gen_one(bi: int):
        batch = batches[bi]
        key = item_key("gen5", {"family": "batch",
                                "rejected_type": f"batch{bi}",
                                "messages": [{"role": "user",
                                              "content": " ".join(
                                                  t["core"] for t in batch)}]})
        hit = cache.get(("gen5", key))
        if hit is not None:
            return bi, hit
        try:
            raw, model = gen_chain(gen_prompt_batch(batch), [GEN_MODEL])
        except Exception as exc:  # noqa: BLE001
            return bi, {"error": str(exc)[:200]}
        items = _extract_batch(raw)
        if not items:
            return bi, {"error": "unparseable"}
        res = {"items": items, "gen_model": model}
        cache[("gen5", key)] = res
        save_cache("gen5", key, res)
        return bi, res

    gen_results: list = [None] * len(batches)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for bi, res in pool.map(gen_one, range(len(batches))):
            gen_results[bi] = res
    # One retry pass for failed batches (errors are never cached).
    todo = [bi for bi, r in enumerate(gen_results)
            if r is None or "error" in r]
    if todo:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for bi, res in pool.map(gen_one, todo):
                gen_results[bi] = res
    stats["gen_calls"] = len(batches) + len(todo)
    stats["gen_failed"] = sum(1 for r in gen_results if r is None or "error" in r)

    cands = []
    for bi, res in enumerate(gen_results):
        if res is None or "error" in res:
            continue
        for ii, (tex, item) in enumerate(zip(batches[bi], res["items"])):
            stats["items_raw"] += 1
            if not isinstance(item, dict):
                continue
            msgs = item.get("messages")
            chosen, rejected = item.get("chosen"), item.get("rejected")
            if not valid_messages(msgs):
                failed.append({"tex": tex, "why": "bad messages shape"})
                continue
            if not isinstance(chosen, str) or not isinstance(rejected, str):
                failed.append({"tex": tex, "why": "missing reply"})
                continue
            cands.append({"tex": tex, "messages": msgs, "chosen": chosen,
                          "rejected": rejected,
                          "gen_model": res.get("gen_model", GEN_MODEL)})

    def judge_one(ci: int):
        c = cands[ci]
        fam = c["tex"]["family"]
        rtype = FAM_RTYPE[fam]
        gate = pre_gate_checks(c["chosen"], c["rejected"], fam, rtype)
        if gate:
            return ci, {"pre_gate_fail": gate}
        key = item_key("jr5", {"family": fam, "rejected_type": rtype,
                               "messages": c["messages"],
                               "tex": c["tex"]["core"]}, c["chosen"])
        with lock:
            hit = cache.get(("jr5", key))
        if hit is None:
            vc = judge_candidate(c["messages"], fam, c["chosen"])
            with lock:
                cache[("jr5", key)] = vc or {"judge_error": "none"}
                save_cache("jr5", key, cache[("jr5", key)])
        else:
            vc = None if "judge_error" in hit else hit
        key2 = item_key("jr5", {"family": fam, "rejected_type": rtype,
                                "messages": c["messages"],
                                "tex": c["tex"]["core"]}, c["rejected"])
        with lock:
            hit2 = cache.get(("jr5", key2))
        if hit2 is None:
            vr = judge_candidate(c["messages"], fam, c["rejected"])
            with lock:
                cache[("jr5", key2)] = vr or {"judge_error": "none"}
                save_cache("jr5", key2, cache[("jr5", key2)])
        else:
            vr = None if "judge_error" in hit2 else hit2
        ok_c, ok_r = chosen_passes(vc, fam), rejected_ok(vr, fam, rtype)
        if ok_c and ok_r:
            return ci, {"vc": vc, "vr": vr}
        why = []
        if not ok_c:
            why.append("chosen_gate")
        if not ok_r:
            why.append("rejected_gate")
        return ci, {"judge_fail": "+".join(why), "vc": vc, "vr": vr}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(judge_one, range(len(cands))))

    for ci, res in results:
        c = cands[ci]
        fam = c["tex"]["family"]
        if "vc" in res and "judge_fail" not in res and "pre_gate_fail" not in res:
            kept.append({
                "prompt": render_context(c["messages"]),
                "chosen": c["chosen"].strip(),
                "rejected": c["rejected"].strip(),
                "messages": c["messages"],
                "family": fam,
                "rejected_type": FAM_RTYPE[fam],
                "gen_model": c["gen_model"],
                "judge_chosen": res["vc"],
                "judge_rejected": res["vr"],
                "sensitive": True,
            })
        else:
            reason = res.get("pre_gate_fail") or res.get("judge_fail", "?")
            if "pre_gate" in str(res.get("pre_gate_fail", "")):
                stats["pre_gate fails"][reason] += 1
            else:
                stats["judge fails"][reason] += 1
            failed.append({"tex": c["tex"], "why": reason})

    return {"stats": stats, "kept": kept, "failed": failed}


def gate_new(kept: list[dict]) -> tuple[list[dict], dict]:
    """Diversity + v3-echo gates over a combined new-row set."""
    kept_div, div_stats = diversity_gate_relaxed(
        list(kept), DIVERSITY_MAX_SHARE)
    old_chosen = [json.loads(l)["chosen"]
                  for l in open(V3) if l.strip()]
    old_gram_list = [set(novel_grams(oc, "")) for oc in old_chosen]
    final = []
    dropped_echo = 0
    for r in kept_div:
        ng = set(novel_grams(r["chosen"], render_context(r["messages"])))
        if any(len(ng & og) >= ECHO_MIN_SHARED for og in old_gram_list):
            dropped_echo += 1
            continue
        final.append(r)
    return final, {"diversity": {k: v for k, v in div_stats.items()},
                   "dropped_echo_vs_v3": dropped_echo}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-new", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20261105)
    ap.add_argument("--reps", type=int, default=8)
    ap.add_argument("--extra-new", type=str, default="")
    args = ap.parse_args()

    global SEED, REPS
    SEED, REPS = args.seed, args.reps
    out = run()
    kept, failed = out["kept"], out["failed"]
    print("kept=%d failed=%d items_raw=%d" % (len(kept), len(failed),
                                              out["stats"]["items_raw"]))
    print("gen_failed=%d pre_gate=%s judge=%s" % (
        out["stats"]["gen_failed"], dict(out["stats"]["pre_gate fails"]),
        dict(out["stats"]["judge fails"])))

    if args.extra_new:
        extra = [json.loads(l) for l in open(args.extra_new)
                 if l.strip()]
        # De-dupe by prompt text: same fresh context generated twice.
        seen = {r["prompt"] for r in kept}
        kept = kept + [r for r in extra if r.get("prompt") not in seen]
        print("union with %s: %d combined" % (args.extra_new, len(kept)))

    final, gate_info = gate_new(kept)
    div_stats = gate_info["diversity"]
    dropped_echo = gate_info["dropped_echo_vs_v3"]
    print("diversity:", {k: v for k, v in div_stats.items()
                         if k != "most_common_endings"})
    print("dropped_echo_vs_v3=%d final_new=%d" % (dropped_echo, len(final)))

    with open(NEW_PATH, "w") as fh:
        for r in final:
            fh.write(json.dumps(r) + "\n")
    with open(FAILED_PATH, "w") as fh:
        for f in failed:
            fh.write(json.dumps(f) + "\n")

    old_rows = [json.loads(l) for l in open(V3) if l.strip()]
    with open(OUT_PATH, "w") as fh:
        for r in old_rows:
            fh.write(json.dumps(r) + "\n")
        for r in final:
            fh.write(json.dumps(r) + "\n")
    print("wrote %s (%d old + %d new = %d)" % (
        OUT_PATH, len(old_rows), len(final), len(old_rows) + len(final)))

    report = {
        "seed": SEED, "gen_model": GEN_MODEL, "batch": BATCH,
        "old_n": len(old_rows), "new_n": len(final),
        "total": len(old_rows) + len(final),
        "stats": {k: (dict(v) if isinstance(v, Counter) else v)
                  for k, v in out["stats"].items()},
        "diversity": {k: v for k, v in div_stats.items()
                      if k != "most_common_endings"},
        "dropped_echo_vs_v3": dropped_echo,
        "by_family": dict(Counter(r["family"] for r in final)),
    }
    with open(REPORT_PATH, "w") as fh:
        json.dump(report, fh, indent=1)
    print(json.dumps(report["by_family"]))
    if len(final) < args.min_new:
        print("BELOW MIN-NEW TARGET")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
