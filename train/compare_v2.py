"""Paired comparison of a repair-v2 candidate vs frozen base (Judge A only).

Mirrors research/gate-analysis.md stats: per-turn A/W deltas (paired 95%
CI + Wilcoxon signed-rank, zeros dropped), scenario win-rates, drift
curves, f6/f7 slices, pass-rate table. Reads Judge-A verdicts only.

Usage:
  uv run python train/compare_v2.py --base runs/judged/tinyaya-base-v2 \
      --cand runs/judged/tinyaya-steer2 --label steer2
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

try:
    from scipy.stats import wilcoxon
except ImportError:
    wilcoxon = None


def load_side(d: Path):
    out = {}
    for p in sorted(d.glob("*.judge.json")):
        v = json.loads(p.read_text())
        scen = v.get("scenario") or p.stem.split("--")[0]
        turns = {}
        for t in v.get("judge_a", []):
            if "judge_error" in t:
                continue
            turns[t["turn"]] = (t.get("A"), t.get("W"), t.get("R"))
        out[scen] = turns
    return out


def paired_stats(deltas):
    d = np.asarray(deltas, dtype=float)
    n = len(d)
    if n == 0:
        return {"n": 0}
    mean = float(d.mean())
    se = float(d.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    ci = (mean - 1.96 * se, mean + 1.96 * se)
    nz = d[d != 0]
    p = float(wilcoxon(nz).pvalue) if wilcoxon and len(nz) > 0 else float("nan")
    return {"n": n, "mean": round(mean, 4), "ci": [round(ci[0], 4), round(ci[1], 4)],
            "p": p, "n_nonzero": len(nz)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--label", default="cand")
    args = ap.parse_args()
    base = load_side(Path(args.base))
    cand = load_side(Path(args.cand))
    common = sorted(set(base) & set(cand))
    print(f"scenarios: base={len(base)} cand={len(cand)} common={len(common)}")

    for axis, idx in (("A", 0), ("W", 1)):
        deltas = []
        for s in common:
            for t, bv in base[s].items():
                cv = cand[s].get(t)
                if cv is None or bv[idx] is None or cv[idx] is None:
                    continue
                deltas.append(cv[idx] - bv[idx])
        st = paired_stats(deltas)
        print(f"{axis}: {args.label}-base n={st['n']} mean={st.get('mean')} "
              f"CI={st.get('ci')} p={st.get('p'):.4g} "
              f"(nonzero={st.get('n_nonzero')})")

    # scenario win-rate on mean axis score
    for axis, idx in (("A", 0), ("W", 1)):
        w = l = t = 0
        for s in common:
            bs = [v[idx] for v in base[s].values() if v[idx] is not None]
            cs = [v[idx] for v in cand[s].values() if v[idx] is not None]
            if not bs or not cs:
                continue
            bm, cm = sum(bs) / len(bs), sum(cs) / len(cs)
            if cm > bm:
                w += 1
            elif cm < bm:
                l += 1
            else:
                t += 1
        print(f"{axis} scenario W/L/T: {w}/{l}/{t} "
              f"(excl-tie={w/max(w+l,1):.3f})")

    # pass-rate proxy per family: need pass/fail rule — report mean-A by family
    # and hard-zero (A=0 ever) counts; full pass/fail needs runner files.
    from collections import defaultdict
    fam = defaultdict(lambda: [0, 0])  # fam -> [n_scen_zeroA_cand, total]
    for s in common:
        f = s.split("-")[0]
        fam[f][1] += 1
    for s in common:
        f = s.split("-")[0]
        if any(v[0] == 0 for v in cand[s].values()):
            fam[f][0] += 1
    print("cand scenarios ever hitting A=0 by family:",
          {k: f"{v[0]}/{v[1]}" for k, v in sorted(fam.items())})
    fam_b = defaultdict(lambda: [0, 0])
    for s in common:
        f = s.split("-")[0]
        fam_b[f][1] += 1
        if any(v[0] == 0 for v in base[s].values()):
            fam_b[f][0] += 1
    print("base scenarios ever hitting A=0 by family:",
          {k: f"{v[0]}/{v[1]}" for k, v in sorted(fam_b.items())})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
