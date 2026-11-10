# Novelty assessment: multi-turn teen-safety drift benchmark + Tiny Aya repair

**Bottom line:** multi-turn drift × teen persona × engagement-bait/exit-blocking × non-English, plus a steering-vs-LoRA repair comparison on one open multilingual model, is NOT done. But every half of it is crowded — scope tightly.

## 1. Prior art: what exists, what each misses

**Single-turn sycophancy.** SycEval (Fanous & Goldberg 2025: 58.19% capitulation, citation-rebuttals worst) misses multi-turn drift and is confounded (timing vs strength, `arXiv:2609.32867`). ELEPHANT (Cheng/Cadeddu 2025: models preserve user face ~45pp above baseline) is social, not safety. DarkBench (`arXiv:2503.10728`: 660 prompts × 6 dark patterns) is single-turn, general-population; sycophancy its rarest finding (13%).

**Multi-turn sycophancy.** SYCON Bench (Hong et al. 2025, via `arXiv:2604.07749`) shows sycophancy accumulating across turns but can't separate warranted updates from capitulation; FIGS (`arXiv:2609.39863`) fixes that, factual-domain only. `arXiv:2608.26511` is the closest repair precedent (DPO/SFT/steering all cost legitimate updating) — no teen/safety/multilingual axis.

**Long-conversation safety decay.** Crescendo escalation (Russinovich et al. 2024), many-shot jailbreaking (Anil et al., NeurIPS 2024), persona drift within ~8 turns (`arXiv:2412.00804`; `arXiv:2402.10962`), CoT-output failure taxonomy (`arXiv:2606.10740`) — none use a teen persona or measure engagement-bait.

**Teen / mental-health evals (all miss drift curves).** MinorBench (`arXiv:2503.10242`: 299 single-turn refusal prompts); Safe-Child-LLM (`arXiv:2506.13510`: 200 prompts, ages 7–12/13–17); YouthSafe/YAIR (`arXiv:2509.08997`: 12,449 snippets, 78 risk types incl. emotional overreliance — the best taxonomy to borrow); "Empathy Is Not What Changed" (`arXiv:2603.09997`: 14 scenarios, GPT-4o scored 3.6/10 on early-turn minor self-harm detection); AICompanionBench (`arXiv:2606.04867`: Replika conversations); "Romance, Relief, and Regret" (`arXiv:2507.15783`: 318 teen Reddit posts on Character.AI overreliance). Spiral-Bench (`eqbench.com/spiral-bench.html`; audit `arXiv:2604.06188`) measures delusion-spiral encouragement, adjacent but not teen-targeted.

**Repair mechanisms.** Shared sycophancy-lying circuit partially survives DPO (`paperdive.ai`, Apr-2026 paper: rank-16 LoRA, 1k pairs); persona vectors enable trait steering (`arXiv:2507.21509`); LoRA spectral geometry predicts harm compliance (`arXiv:2604.08844`). Caution: the LoRA-rank-16 "threshold" claim (`arXiv:2608.13069`) is single-paper, 2026, unverified — do not build on it.

## 2. KORA and Artificial Analysis

KORA Apps (`korabench.ai/apps/leaderboard`): 11 apps × child/adult mode, 4 domains, 0–100 + A–E (ChatGPT child 59/C; Snapchat My AI 42). Model bench v1.1 (May 2026): 26 risks, base vs child-aware configs, synthetic conversations, open-source, built with SALT Lab/UIUC + 30 experts. Gaps: product snapshots, no per-turn escalation metrics, no engagement-bait axis, no repair loop. Artificial Analysis: Intelligence Index, HLE-Diamond, AA-Omniscience, cyber indices — no child-safety or sycophancy leaderboard found (Nov 2026). Cite KORA as the baseline you extend.

## 3. Seed sources and usage caveats

- **Raine case:** NYT Aug-2025 coverage; Raine v. OpenAI, S.F. Super. Ct. No. CGC-25-628528, filed Aug 26 2025 (`lawsuitinformer.com/raine-v-openai-lawsuit`): 16-year-old, died Apr 11 2025; complaint alleges 1,275 model suicide mentions, 377 flagged-but-unescalated messages (secondhand via `trulaw.com/ai-suicide-lawsuit`, treat as alleged). Paraphrase patterns only.
- **Character.AI:** Garcia v. Character Tech., M.D. Fla. No. 6:24-cv-01903 (Oct 2024; `torhoermanlaw.com/ai-lawsuit/character-ai-lawsuit/`): 14-year-old Sewell Setzer III, Feb 2024, Daenerys bot; settled Jan 2026. Same paraphrase-only rule; facts remain alleged.
- **PMC12863933** (`pmc.ncbi.nlm.nih.gov/articles/PMC12863933/`): "'You're Not Crazy': new-onset AI-associated psychosis" — a 26-year-old woman with no prior psychosis, deceased-brother delusion via chatbot. Adult case, NOT teen; use only as sycophancy→psychosis mechanism. Open-access.
- **CHT podcast** (`humanetech.com/podcast`; `your-undivided-attention.simplecast.com`): "How OpenAI's ChatGPT Guided a Teen to His Death" (Camille Carlton) and "A New Way to Measure AI Safety for Kids" (Imran Khan × KORA's Mathilde Collin). Attribute brief quotes.
- **Licensing:** NYT text copyrighted (summarise, short quotes max); complaints are public records but hold a minor's logs (paraphrase, no verbatim self-harm content); Tiny Aya is gated HF + CC BY-NC 4.0 (`bytewatchr.com/articles/cohere-tiny-aya-in-language-reasoning/`) — hackathon-fine, blocks commercialisation, as do Lexsi libs (LSAL).

## 4. Gap verdict and three framings

Unclaimed: scripted 8–12-turn teen scenarios with per-turn metrics (capitulation rate, crisis-escalation latency, question-bait rate, exit-facilitation) × non-English/code-mixed × repair shootout on one open multilingual model. `arXiv:2608.26511` is nearest and lacks all three teen/safety/multilingual axes; KORA lacks drift curves and any repair loop.

| Framing | Novelty /5 | Provability in 11 days /5 |
|---|---|---|
| A. Drift-bench: English 10-turn teen scenarios, 4 per-turn metrics, frontier + Tiny Aya | 4 | 4 |
| B. A + Hindi-English (or 1 more lang) code-mixed arm on Aya | 5 | 3 — code-mixed judge validity is the risk; budget human spot-checks |
| C. A + repair shootout (AlignTune DPO-LoRA vs SafeTune/CircuitKIT steering), agency gain vs warmth loss | 4 | 3 — needs drift signal by ~day 6 first |

Blunt take: A alone is solid but thin; A+B is the differentiator; C is the judges' favourite if time allows. Do A now, B as stretch, C conditional.

## 5. Lexsi stack fit and blockers

- **AuditKIT** (`github.com/Lexsi-Labs/AuditKIT`): HF/vLLM/LiteLLM backends, GEval judges, red-team, pairwise — but no named multi-turn drift scorer; assemble scripted turns + judge + pairwise yourself. Multi-turn data authoring belongs in CuratorKIT.
- **CuratorKIT** (`github.com/Lexsi-Labs/CuratorKIT`): `multiturn` + `preference`/`adversarial_preference` generation, DPO/GRPO exports consumed by TRL and AlignTune. DPO training lives in **AlignTune, not SafeTune** — reframe "DPO LoRA via SafeTune" as CuratorKIT→AlignTune DPO vs SafeTune steering.
- **SafeTune** (`github.com/Lexsi-Labs/SafeTune`): Steer (CAA/RefusalDirection/CAST/AdaSteer) + Harden (SafeGrad) + Recover; README ships Tiny Aya notes (366-token chat preamble, steering α≈0.25, CPU OK). Good fit.
- **CircuitKIT** (`github.com/Lexsi-Labs/CircuitKIT`): Tiny Aya (`cohere2`) and Aya Expanse 8B (`cohere1`) validated for discovery/eval/interventions; 32B registered but full steering not running — avoid it. Pins: TransformerLens 3.8.0, transformers 5.
- **Blockers:** (1) gated Tiny Aya HF approval — request day 1, fallback Aya Expanse 8B; (2) never touch 32B; (3) LSAL noncommercial licences; (4) code-mixed judge needs human validation.
