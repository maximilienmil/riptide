# ROI: self-hosted open model vs closed APIs for a teen-support workload

Status: working draft, 2026-11-04. Self-hosted figures use measured
throughput and list GPU prices from
[research/stack-smoke.md](../research/stack-smoke.md) §7. Closed-API figures
are placeholders until filled from the linked list-price pages. Every
unmeasured number is marked `{{TBD: ...}}`.

## Licence framing

Tiny Aya Global is CC-BY-NC-4.0 and gated. It cannot be commercialised, so
this comparison frames the self-hosted column as **an open model of this
size** (3.3B parameters, run on Modal list-price GPUs). Any production
deployment would substitute a commercially licensed model in the same
size class and re-measure throughput. The method below transfers directly.

## Workload assumption (stated, not measured)

A teen-support app at **1,000,000 conversations/month, 10 turns each**,
with an assumed average of 150 input + 150 output tokens per turn:

- Tokens per conversation: 3,000 (assumption; replace with measured means)
- Tokens per month: **3.00B** (1,500M input + 1,500M output)
- A month is taken as 30 days (2,592,000 seconds)

## Self-hosted cost (measured throughput, list GPU prices)

Measured Tiny Aya Global throughput, batch 1 unless noted
(stack-smoke §7.2): L4 18.8 and 27.9 tok/s across runs (host noise, use
~20 to 28); A10G 24.8 tok/s; A10G vLLM offline 463.6 tok/s total across
8 prompts of 64 tokens (~58 tok/s per sequence). List prices
(stack-smoke §7.3, from `modal billing rates`,
[modal.com/pricing](https://modal.com/pricing), verified HTTP 200
2026-11-04): T4 $0.59/hr, L4 $0.80/hr, A10G $1.10/hr.

Effective cost per million tokens = $/hr ÷ (tok/s × 3600) × 1e6:

| Serving setup | Throughput | Effective $/MTok | GPU-hours/month | $/month at 3B tokens |
|---|---|---|---|---|
| A10G, vLLM batched | 463.6 tok/s | $0.66 | 1,798 | $1,977 |
| A10G, batch 1 | 24.8 tok/s | $12.32 | 33,602 | $36,962 |
| L4, batch 1 (~23.4 tok/s midpoint) | ~23.4 tok/s | $9.52 | 35,689 | $28,551 |

Notes:

- The vLLM row is the correct basis for high-volume math (stack-smoke §7:
  "feed the vLLM row, not batch-1, into any high-volume ROI math"). It was
  measured on short generations (64 tokens); longer replies lower
  throughput. Replace with a production-length measurement before budgeting.
- At 3B tokens/month the vLLM setup needs about 1,798 GPU-hours, which is
  roughly 2.5 A10G GPUs running continuously (a month has ~730 hours).
- Batch-1 rows show why naive per-request serving is an order of magnitude
  more expensive. They assume one GPU and no batching.
- Modal billed cost for all smoke work so far is $0.00 (metered $1.53
  workspace-lifetime, covered by free allowance). DPO training cost for the
  repair is not included above; see Repair.

## Closed API cost

Monthly API cost = (input MTok × input $/MTok) + (output MTok × output
$/MTok), with 1,500M input + 1,500M output tokens from the workload above.
Anthropic list prices as of 2026-11-03 (Claude API pricing table; re-check at submission time). Prices change:

| Provider | Price page | Input $/MTok | Output $/MTok | $/month at 3B tokens |
|---|---|---|---|---|
| Anthropic Claude Haiku 5.5 | [claude.com/pricing](https://claude.com/pricing) | $0.10 (prompts ≤100K tokens) | $0.50 | $900 |
| Anthropic Claude Sonnet 5.5 | [claude.com/pricing](https://claude.com/pricing) | $2.00 | $10.00 | $18,000 |
| OpenAI | [platform.openai.com/docs/pricing](https://platform.openai.com/docs/pricing) (verified HTTP 200) | {{TBD: input $/MTok}} | {{TBD: output $/MTok}} | {{TBD: monthly $}} |

The tested closed models are Claude Haiku/Sonnet and Codex `gpt-6-luna`
via CLI (about 15 scenarios each). Report the API column for the same
model classes that appear on the leaderboard.

## Reading the comparison

At the measured vLLM throughput, self-hosted effective cost is $0.66 per
million tokens. The comparison therefore reduces to one question: is the
applicable API list price per blended million tokens above or below $0.66
plus the engineering cost of running the endpoint? If yes, self-hosting an
open model of this size wins on price at this volume, before any safety
difference is considered. The batch-1 rows show the reverse: unbatched
serving loses to APIs by roughly an order of magnitude.

Caveats:

- Throughput was measured on short generations. Re-measure at the
  production reply-length distribution.
- No quantization was used in the smoke runs. INT8/AWQ serving changes
  both throughput and GPU choice.
- The repair (DPO LoRA or steering) adds one training bill and possibly a
  small inference overhead. Both are {{TBD: training $ and latency delta}}.
- Reliability, not price, is the binding constraint for this workload.
  A cheaper model that fails the benchmark is not a saving.
