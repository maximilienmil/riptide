# Eval sources (pinned 2026-11-04)

All item sets are baked into the Modal eval image (`infra/modal_evals.py`
`add_local_file`), so reruns are bit-identical without network access.

## XSTest — over-refusal / compliance
- Repo: https://github.com/paul-rottger/xstest (verified 200, 2026-11-04)
- Prompts: `xstest_prompts.csv` (verbatim copy in this dir), 450 rows:
  250 `safe` + 200 `unsafe`.
- Classifier: `strmatch_label` copied verbatim from
  https://github.com/paul-rottger/xstest/blob/main/evaluation/classify_completions_strmatch.py
  (checks the lowercased completion prefix; `2_full_refusal` vs
  `1_full_compliance`).
- Paper: Röttger et al. 2023, "XSTest: A Test Suite for Identifying
  Exaggerated Safety Behaviours in Large Language Models",
  arXiv:2308.01263 (https://arxiv.org/abs/2308.01263, verified 200).
- Reported: over-refusal rate on the 250 safe prompts
  (fraction labelled `2_full_refusal`), compliance rate on the 200 unsafe
  prompts (fraction labelled `1_full_compliance`), Wilson 95% CIs.

## MMLU — general capability via AuditKIT
- Dataset: `cais/mmlu`, config `all`, split `test` (14042 items, 57 subjects),
  via `datasets==5.1.0`.
- Subset: `mmlu_200.jsonl`, 200 items, stratified 3-per-subject (57×3=171)
  + 29 uniform fill, seed 7, order shuffled with seed 7.
- Prompt: 0-shot, chat template, "Answer with the letter only." Generation
  capped at 8 new tokens; score target is the answer letter. The AuditKIT
  model callable returns the first `[A-D]` in the generation (else the
  stripped raw text) and `ak.evaluate` scores `exact_match`.
- AuditKIT: `auditkit==1.1.3` (same version as the stack smoke test).
  Run fingerprint recorded per variant in `RESULTS.md`.

## Fluency — perplexity on neutral held-out text
- Corpus: `Salesforce/wikitext`, revision
  `b08601e04326c79dfdd32d625aee71d232d685c3`,
  file `wikitext-103-raw-v1/test-00000-of-00001.parquet`
  (https://huggingface.co/datasets/Salesforce/wikitext, verified 2026-11-04).
- `fluency.txt`: first 10000 whitespace-separated words of the test split
  (non-empty rows concatenated). Held out from all Riptide training
  (DPO/steer pairs are teen-conversation replies, disjoint domain).
- Metric: teacher-forced perplexity in 512-token non-overlapping windows;
  reported as mean ± 95% CI over windows, with total token count.
