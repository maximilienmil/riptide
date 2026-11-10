"""Cross-judge failure handling: no poisoned cache, valid-only kappa.

Regression tests for the Track C v3 silent failure where 475/483 cached
cross-judge verdicts were errors and the empty drop lists were reported
as agreement. No network.
"""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "train"))

import gen_dpo_v3 as v3


def _msg(text="hi"):
    return [{"role": "user", "content": text}]


def test_xjudge_failure_not_cached(monkeypatch):
    """A total cross-judge failure must not be written to the cache."""
    monkeypatch.setattr(v3, "judge_candidate", lambda *a, **k: None)
    saved = []
    monkeypatch.setattr(v3, "save_cache",
                        lambda kind, key, res: saved.append((kind, key)))
    cache: dict = {}
    verdict, model = v3.xjudge_candidate(_msg(), "control", "reply", cache)
    assert model == "failed"
    assert "judge_error" in verdict
    assert cache == {}
    assert saved == []


def test_run_cross_ignores_errored_verdicts(monkeypatch):
    """Errored cross verdicts are excluded from kappa and drops."""

    def fake_xjudge(messages, family, candidate, cache):
        if candidate.startswith("chosen"):
            return {"A": 3, "W": 3}, "fake-model"  # agree with muse
        return {"judge_error": "boom"}, "failed"  # excluded, not agreement

    monkeypatch.setattr(v3, "xjudge_candidate", fake_xjudge)
    base = [{"family": "control", "messages": _msg(f"m{i}"),
             "chosen": f"chosen {i}",
             "judge_chosen": {"A": 3, "W": 3}} for i in range(4)]
    kept = [{"family": "control", "messages": _msg(f"n{j}"),
             "rejected": f"rej {j}", "rejected_type": "cold-refusal",
             "base_idx": 0} for j in range(2)]
    stats: dict = {}
    drops = v3.run_cross(base, kept, [], {}, stats, random.Random(v3.SEED))
    assert drops == {"drop_base": [], "drop_new": []}
    assert stats["cross_errors"] == 2
    assert stats["cross_kappa"]["n"] == 1  # only the sampled chosen pair
    assert stats["cross_kappa"]["agree"] == 1
