#!/usr/bin/env python3
"""Track C v3 post-processing: method-term 0-hit contract + sensitive flags.

Runs on the gen_dpo_v3.py merge outputs (712 rows):

1. Word-boundary scan of every rejected reply for method-term tokens
   (pills/overdose/rope/hanging/cutting/blade/jump/gun/poison/dose).
   Hits are removed outright — even when all are benign idioms ("hanging
   out") — for a literal 0-hit contract on the shipped file.
2. Adds a `sensitive` flag per row (true iff the rejected-type is one of
   validation-of-ideation, secrecy-promise, disclosure-missed,
   age-signal-ignored) so an HF upload can gate on it.
3. Rebuilds steer_pairs.jsonl (non-cold f3/f4 only, cap 150) and refreshes
   the count/mix fields of _report_llm.json with the pipeline's own
   mix_table/targets_met.

Deterministic; safe to re-run (idempotent on its own outputs).
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_dpo_v3 import SEED, mix_table, targets_met  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"

METHOD_TERMS = re.compile(
    r"\b(pills|overdose|rope|hanging|cutting|blade|jump|gun|poison|dose)\b",
    re.IGNORECASE)
SENSITIVE_TYPES = {"validation-of-ideation", "secrecy-promise",
                   "disclosure-missed", "age-signal-ignored"}


def main() -> None:
    rng = random.Random(SEED)
    rows = [json.loads(l) for l in (DATA / "dpo.jsonl").read_text().splitlines()]
    n_in = len(rows)
    hits = [(i, r["family"], r["rejected_type"])
            for i, r in enumerate(rows) if METHOD_TERMS.search(r["rejected"])]
    rows = [r for r in rows if not METHOD_TERMS.search(r["rejected"])]
    for r in rows:
        r["sensitive"] = r["rejected_type"] in SENSITIVE_TYPES
    n_sensitive = sum(1 for r in rows if r["sensitive"])

    steer = [{"prompt": r["prompt"], "positive": r["chosen"],
              "negative": r["rejected"],
              "direction": "sycophancy" if r["family"] == "f4" else "engagement"}
             for r in rows if r["family"] in ("f4", "f3")
             and r["rejected_type"] != "cold-refusal"]
    # Deterministic order: rank by prompt hash (no dependence on file order).
    steer.sort(key=lambda s: hash(s["prompt"]) % (2 ** 63))
    rng.shuffle(steer)
    steer = steer[:150]

    with (DATA / "dpo.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    with (DATA / "steer_pairs.jsonl").open("w") as fh:
        for s in steer:
            fh.write(json.dumps(s) + "\n")

    report = json.loads((DATA / "_report_llm.json").read_text())
    report["postprocess"] = {
        "method_term_hits_removed": [
            {"family": f, "rejected_type": t} for _, f, t in hits],
        "n_sensitive": n_sensitive,
    }
    report["final_counts"] = dict(Counter(r["family"] for r in rows))
    report["rejected_mix"] = dict(Counter(r["rejected_type"] for r in rows))
    report["mix_table"] = mix_table(rows)
    report["target_problems"] = targets_met(report["mix_table"])
    report["n_dpo"] = len(rows)
    report["n_steer"] = len(steer)
    (DATA / "_report_llm.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"n_in": n_in, "removed": len(hits), "hits": hits,
                      "n_out": len(rows), "n_sensitive": n_sensitive,
                      "n_steer": len(steer),
                      "target_problems": report["target_problems"]},
                     indent=2))


if __name__ == "__main__":
    main()
