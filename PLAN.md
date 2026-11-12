# Riptide — plan

> "The current that pulls you out while each wave looks harmless."
> A multi-turn benchmark of how chatbots treat teens and vulnerable users over long conversations, plus a proof that the failures can be fixed in an open model.

Lexsi Labs hackathon, Track 2, solo. Submission is due end of day Nov 14, 2026. If shortlisted, Demo Day is Nov 22.

## Thesis
Single-prompt safety tests miss the real pattern: harm builds up across many turns. Riptide measures this gradual drift across 7 failure families seeded from real cases. It scores 3 axes: agency/safety, warmth, and rational updating. It then shows that Tiny Aya can be repaired without becoming cold or stubborn.

## Track mapping (no special approval sought)
- Track 2a: adversarial and safety evaluation sets; multi-turn audits.
- Track 2b: safety-preserving fine-tuning; inference-time steering; locating where safety lives.

## Repo chain
CuratorKIT (scenarios and preference pairs) → AuditKIT (runner and metrics) → SafeTune / CircuitKIT (find the direction and steer) + AlignTune (DPO LoRA).

## Models
- **Trained:** Tiny Aya Global.
- **Eval baseline:** Aya Expanse 8B. Do not steer the 32B model.
- **Tested, free tiers only:**
  - OpenRouter `:free` models (Llama, DeepSeek, Qwen)
  - Gemini Flash (free tier)
  - Cohere trial (Command A, Aya)
  - Muse Spark
  - Claude Haiku/Sonnet and GPT `gpt-6-luna` via CLI, about 15 scenarios each, labelled "via CLI"
  - Never Opus, Fable or GPT Sol.
  - Hand-paste 3 scenarios into the web apps only if a result is surprising.
- **Compute:** Modal free tier, $20 HF credit, Colab/Kaggle.

## Benchmark
About 60 English scenarios, 8–12 turns each, plus a teen-slang/texting variant of every scenario.

| # | Family | Seeds |
|---|---|---|
| 1 | Escalating self-harm | Raine, CCDH |
| 2 | Buried disclosure (non-graphic, unambiguous, normalised) | youth-council pattern (private), YAIR |
| 3 | Attachment & retention (won't let you leave) | Setzer, DarkBench, GPT-5 backlash |
| 4 | Sycophancy on bad decisions | ELEPHANT, SycEval |
| 5 | Rational updating (the user is right) | arXiv:2608.26511 |
| 6 | Secrecy coaching | Raine, Texas suits |
| 7 | Age-blind romance (does the model notice the age signal and redirect?) | Meta leak, Setzer |

Delusion validation is out of scope; cite Spiral-Bench instead.

Real quotes seed the opening or critical turn, and Muse writes the rest of the conversation. Every scenario carries a `seeded_from` URL pointing to a primary source.

**Judges:** Muse Spark and Gemini Flash. Report inter-judge agreement, using Max's 50 hand labels as ground truth.

**Metrics:**
- Per-family pass rate
- The turn of first failure (a drift curve)
- Warmth win-rate against the base model
- MT-Bench-style helpfulness
- XSTest over-refusal
- Rational-updating score

## Hard rules
- No sexual content involving minors, ever. Generation runs through an explicit-content reject filter.
- Gated HF dataset with a content warning. Family-2 transcripts are click-to-reveal in the Space.
- Private source material is never published, committed, or pasted into an agent brief. `private/` is gitignored.
- The "more explicit prompts" extrapolation appears only as a stated hypothesis under Limitations.
- No code is shared with any future Gemini Counterweight project.

## Scope ladder
- **A (core):** the benchmark plus a leaderboard of the tested models.
- **B (parallel, stretch):** the teen-register robustness slice, run as a separate analysis.
- **C (parallel):** the Tiny Aya repair shootout: DPO LoRA (AlignTune) vs steering (SafeTune/CircuitKIT).
  - **Gate on Nov 8:** go only if Tiny Aya shows clear drift and the steering vector extracts cleanly; otherwise drop C.

## Schedule (Max: 1–2 h/day; agents run continuously)
| Date | Agents | Max |
|---|---|---|
| Nov 3–4 | Repo scaffold; upgrade quotes to primary sources; smoke-test the Lexsi repos on Tiny Aya; write scenario schema and judge rubrics | Review rubrics, seed list, taste |
| Nov 5–6 | Generate the 60 scenarios plus the slang variants; build the multi-turn runner (adapting the Spiral-Bench design) | Spot-read 15 scenarios |
| Nov 7 | Full runs on every model; judge both ways | 50 hand labels (~1 h) |
| **Nov 8** | **C gate**; preference pairs; steering vector | Go/no-go decision |
| Nov 9–11 | DPO LoRA + steering runs; re-run the evals; ROI table | Review failure traces |
| Nov 12–13 | HF Space (report cards + turn viewer, styled like humanetech.com); HF Article (MIT cognitive-offload register); upload artifacts | Edit the article; record the demo |
| Nov 14 | Buffer and submission | Submit |

## Deliverables
- HF namespace: `maximilianmilo` (confirmed). GitHub: `maximilienmil/riptide`
- HF dataset `riptide-bench` (gated)
- HF model / adapter `riptide-tinyaya-dpo`, plus the steering vector
- Logs
- HF Space and HF Article
- ROI comparison: closed API vs self-hosted Tiny Aya

## Orchestration
- Claude orchestrates and reviews.
- All build and research agents run Muse Code `muse-spark-1.3-contributor`.
- Total budget: $100. About $50 is for the orchestrator.

## Research
`research/novelty.md`, `research/datasets.md`

## Visuals & video
- All visuals are built in HTML from real results, with one humanetech-style palette shared by the README, Article, Space and video. We iterate on design direction together.
- Charts:
  1. Drift curve hero: % of models still safe, by turn
  2. Report-card grid: models x 7 behaviours, graded A-F
  3. Tiny Aya 3-axis before/after: safety, warmth, updating
  4. Repo pipeline diagram
- Video: about 2 minutes, no voiceover, captions only, made with HyperFrames (HTML to video; Remotion as fallback). Beats: the Raine pattern, then a model failing at a specific turn, then the report card, then the Tiny Aya before/after. Render by Nov 13.

## Judge reliability gate (before Nov 7 full runs)
- Safety-axis κ must be at least 0.6, measured on Max's 50 hand labels plus a first batch of real scenarios.
- If it falls short, tighten the rubrics (add worked examples to each score level) and score again.
- Rational updating is scored only in family 5 and marked "not applicable" elsewhere.

## Judge decision (Nov 4)
- Judge A is Muse Spark 1.3 Contributor. Judge B is Codex `gpt-6-luna`: safety-axis κ 0.603 against Muse, and 96% of its quotes appear in the turn it scored.
- Rejected as judge B:
  - Gemini Flash and Flash-Lite: free tier is 20 requests per day.
  - Qwen3-32B and Qwen2.5-72B: too lenient (κ 0.22–0.29), even in per-turn mode.
  - Claude Haiku: κ 0.49 and near-zero agreement on warmth.
- Warmth: absolute scores don't agree between judges (κ ≤ 0.25). Use a pairwise warmth win-rate (base vs repaired) instead, and keep warmth out of pass/fail.
- Max's 50 hand labels remain the ground truth for the published κ.

## Continued judging authorization (Nov 4)
- Max approved Luna as second judge for all remaining runs (Q41), including repaired Tiny Aya and leaderboard models. Hand-label calibration remains pending; uncalibrated results are provisional.
- Queue: `runs/judged/run_remaining.sh`; log: `runs/judged/remaining.log`. Resume preserves valid judge sides and reuses cached raw responses for parse repairs.
