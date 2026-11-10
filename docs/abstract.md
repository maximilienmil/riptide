# Abstract

Single-turn safety tests miss how a chatbot conversation goes wrong. A
teenager rarely opens with a crisis. They hint on Monday, go quiet on
Wednesday, and say the scary thing on Friday, and every reply along the way
can look harmless while the conversation drifts somewhere unsafe. Riptide
measures that drift.

Riptide is 120 scripted conversations, 60 stems in a standard and a slang
register, across seven behaviour families: crisis disclosure, buried
disclosure, attachment and engagement bait, coercion, rational updating,
secrecy, and age-blind romance. Thirteen model configurations produced 1,065
transcripts; 344 of 525 board conversations are complete. Two independent
judges score every turn on safety, warmth, and rational updating.

The judge reliability work is reported as a result. Inter-judge safety
agreement is 0.603 on the pilot and 0.52 to 0.59 on the full runs; agreement
with 50 hand labels peaks at 0.577, so the 0.6 gate is unmet and every score
is provisional. Three candidates were rejected for cause: Gemini's free tier
allows 20 requests a day, and Qwen (0.22 to 0.29 against the primary judge)
and Claude Haiku (0.49) both fell well short. Warmth agreement, 0.22 to 0.39,
is too weak to decide anything, so it stays a guardrail.

The benchmark finds drift everywhere and finds it late. Tiny Aya base keeps
81% of conversations clean at turn 2 and 17% at turn 12; Aya Expanse 8B falls
from 92% to 26%; Muse Spark 1.3 holds 97% to 71%. A model can look adequate
at the start and fail most of the way through. Secrecy is where every small
open model collapses: all five Tiny Aya variants pass 0 of 16, against 8 of
16 for Muse Spark.

I repaired Tiny Aya Global two ways. Direct preference optimisation on 1,016
pairs, 307 of them mined for the secrecy and age failures, raised passes from
24 to 36 of 120 under the primary judge (McNemar p=0.023) and lifted mean
safety by 0.211 and warmth by 0.257. It also cost attachment, family 3
falling from 3 of 18 to 0 of 18, and left rational updating's point estimate
negative under both judges; the second judge sees the repair's direction but
not its significance (p=0.72). Contrastive activation steering failed the
opposite way, 24 passes falling to 19. Secrecy coaching survived neither
repair, which is the main warning: four families moved and the isolation
failure is still there.

Released: a gated dataset of scenarios, transcripts and verdicts, the DPO
adapter, the steering vectors as a documented negative result, a report-card
Space and a turn viewer. Serving the repaired model on Modal costs about
$1,977 a month at a million conversations, roughly 9x cheaper than a
Sonnet-class API but more than Haiku, so the case for self-hosting is control
of weights and failure data, not price alone.
