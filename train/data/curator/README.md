---
tags:
- curatorkit
configs:
- config_name: sft_alpaca
  default: true
  description: curatorkit sft_alpaca export, sha256 571c46615892e225ef76dcf0ae2ab10d19c2853c2d0908c972a142b69d36052e
  data_files:
  - split: train
    path: sft_alpaca.jsonl
---

# Dataset Card: curatorkit_run

## Summary

- **Run timestamp**: 2026-11-04T10:05:29.852829Z
- **Wall clock time**: 3.2s
- **Pipeline config hash**: `309416929d82a746`

## Source Documents

  - Unknown

## Pipeline Stages

| Step | Input | Passed | Recovered | Rejected | Forward |
|------|-------|--------|-----------|----------|---------|
| JSONLReader | 712 | 712 | — | 0 | 712 |
| SchemaGate | 712 | 712 | 0 | 0 | 712 |
| ExactDeduplicator | 712 | 448 | — | — | 448 |
| MinHashDeduplicator | 448 | 448 | — | — | 448 |
| TextCleaner | 448 | 448 | — | — | 448 |
| AlpacaExporter | — | 448 | — | — | 448 |

## Gate Pass Rates and Rejection Breakdown

- **JSONLReader**: 712/0 passed (N/A), 0 rejected
- **SchemaGate**: 712/712 passed (100.0%), 0 rejected


**Rejection reasons:**
  - None

## Deduplication

  - near_duplicates_removed: 0
  - surviving_count: 448

## Known Limitations

- MinHash threshold used: **0.85** — this is a starting point, not a universal answer. Adjust per domain (legal, medical, and other domain-specific corpora may need a lower threshold to avoid losing structurally similar but semantically valid examples).
- Table extraction requires `extract_tables: true` on the PDF reader and MinerU with GPU support. Disabled by default.
- Token counting uses a whitespace tokenizer by default. For exact LLM context window
  enforcement, enable `use_tiktoken: true` in the SchemaGate config.
- Both within-run (MinHash/Diversity) and cross-run (EmbeddingDeduplicator) deduplication
  are available. Cross-run dedup persists an embedding index across runs; use
  `embedding_reset_index: true` to start fresh.

## Reproduction

```bash
pip install curatorkit
curatorkit run pipeline.yaml --output-dir ./out/
```

## Tool Versions

- **curatorkit**: 0.1.22
- **python**: 3.11.16

## Configs

Load one with `datasets.load_dataset("<this folder or Hub repo>", "<config>")`.

| Config | Splits (rows) | Columns |
|--------|---------------|---------|
| `sft_alpaca` | train (448) | `instruction`: string<br>`input`: string (empty when there is no input)<br>`output`: string |
