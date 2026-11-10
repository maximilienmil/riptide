# Dataset & Research Seeds for Teen/Vulnerable-User Benchmark

All links verified (HTTP 200 via curl, 2026-11-03). English-only items.

## 1. Teen / minor prompts and personas

- **MinorBench** — `govtech/MinorBench` ([HF](https://huggingface.co/datasets/govtech/MinorBench), [arXiv:2503.10242](https://arxiv.org/abs/2503.10242)). MIT license. 299 single-turn prompts, 6 risk categories. No real minors' data (hand-built adult-authored prompts). Use: seed refusal/coping scenarios; extend each prompt into multi-turn arcs (our core gap — it is single-turn only).
- **Safe-Child-LLM** — ([GitHub](https://github.com/The-Responsible-AI-Initiative/Safe_Child_LLM_Benchmark), [arXiv:2506.13510](https://arxiv.org/abs/2506.13510)). 200 adversarial prompts split ages 7–12 / 13–17, adapted from SG-Bench/HarmBench/JBB with 0–5 refusal rubric. License per repo (check before reuse). Synthetic, no minors' data. Use: teen item bank + reuse their graded-refusal rubric shape.
- **YAIR / YouthSafe** — ([arXiv:2509.08997](https://arxiv.org/abs/2509.08997)). 12,449 annotated conversation snippets, 78 fine-grained youth-harm types (grooming, boundary violation, emotional over-reliance). Single-turn snippets. Data release via authors — confirm license/access. No confirmed real-minor data. Use: largest youth-risk taxonomy; best source of scenario labels.
- **CAREBench** — ([GitHub](https://github.com/handshake-ai-research/carebench), [arXiv:2606.29685](https://arxiv.org/abs/2606.29685)). 500 prompts, 12 categories incl. grooming/relationship-engineering, emotional dependency, mental-illness sensitivity. Single-turn + auto-grader. Responsibly scoped (no explicit content). Use: dependency/manipulation categories map directly onto our engagement-bait and not-letting-user-leave axes.
- **NPS Chat Corpus** — ([NLTK data](https://www.nltk.org/data.html), ~500k posts from age-specific chat rooms incl. teens). LDC/educational license; check redistribution terms. Real minors' chat possible (2006, masked) — ethics flag: use for *register/style* only, never as personas with real content. Use: teen texting-style/slang overlay dictionary.

## 2. Disclosure detection (buried abuse / self-harm)

- **UMD Reddit Suicidality / CLPsych shared tasks** — ([CLPsych](https://clpsych.org/)). Reddit posts with suicide-risk levels. Gated: application + IRB, task-only use. Authors are adults; treat as sensitive anyway. Use: methodology for grading escalating risk; cannot redistribute — author our own escalating-risk arcs instead.
- **Dreaddit** — ([arXiv:2112.10064](https://arxiv.org/abs/2112.10064)). ~190k Reddit posts, stress vs casual labels, public download. Adult-authored. Use: stressor-topic seeds for rambling-story scenarios with buried disclosures.
- ⚠️ **PAN12 / Perverted Justice (PJ) grooming logs** — ([PAN](https://pan.webis.de/)). Hundreds of thousands of chats; decoys pose as minors, explicit sexual content present. **FLAG: falls under our hard rule — never generate, reproduce, or fine-tune on this material.** Use only as background on grooming-phase taxonomies (e.g. phase-annotation literature), never as scenario text.
- **EIBench** — ([arXiv:2606.15532](https://arxiv.org/abs/2606.15532)). 2,222 simulator-based emotion-management scenarios (2,009 train / 213 test). Use: turn-credit/support-seeker simulator pattern for long-horizon evaluation design.

## 3. Multi-turn dynamics (sycophancy, dependency, retention)

- **Spiral-Bench** — ([GitHub](https://github.com/sam-paech/spiral-bench), [leaderboard](https://eqbench.com/spiral-bench.html)). 30 simulated ~20-turn chats, seeker persona (Kimi-K2) vs target model, GPT-5/Claude judge on protective vs risky behaviors. Open code/logs. Use: closest existing harness to ours — copy the user-simulator + per-turn judge architecture.
- **MHJ (Multi-Turn Human Jailbreaks)** — `ScaleAI/mhj` ([HF](https://huggingface.co/datasets/ScaleAI/mhj), [arXiv:2408.15221](https://arxiv.org/abs/2408.15221)). 2,912 prompts / 537 conversations (2–34 turns). Gated, CC-BY-NC-4.0. Adult red-teamers. Use: multi-turn tactic catalog (gradual escalation, reframing) applied to self-harm/dependency elicitation.
- **ELEPHANT** — ([GitHub](https://github.com/myracheng/elephant), [arXiv:2505.13995](https://arxiv.org/abs/2505.13995)). Social-sycophancy benchmark (QEQ advice + r/AmITheAsshole wrongdoing; 11 models). Use: moral-endorsement items for "rational updating when user is right vs wrong" axis.
- **SycEval** — ([arXiv:2502.08177](https://arxiv.org/abs/2502.08177)). Sycophancy on AMPS math + MedQuad medical; 58% sycophancy rate, persistence metric. Single-turn. Use: rebuttal-strength/persistence metrics; port to multi-turn.
- **DarkBench** — `apart/darkbench` ([HF](https://huggingface.co/datasets/apart/darkbench), [arXiv:2503.10728](https://arxiv.org/abs/2503.10728)). MIT. 660 prompts, 6 dark patterns incl. user-retention and sycophancy. Single-turn. Use: retention/guilt-trip items seed "won't let user leave" scenarios.
- **Companion-dependency studies**: De Freitas et al. guilt/FOMO farewells ([arXiv:2508.19258](https://arxiv.org/abs/2508.19258)); Chu et al. 17k-chat affect-mirroring analysis ([arXiv:2505.11649](https://arxiv.org/abs/2505.11649)). Observational data, not redistributable benchmarks. Use: behavioral codebooks (guilt-tripping, FOMO, affect amplification) for our judge rubric.
- **MHQA** — ([arXiv:2502.15418](https://arxiv.org/abs/2502.15418)). 2,475 expert-verified MCQs (anxiety/depression/trauma/OCD). Single-turn knowledge QA, not dialogue. Use: factual-accuracy checks only; not a dialogue seed.

## 4. Register robustness

- MIT FAccT 2025 study: typos/slang/informal register shift LLM clinical recommendations toward self-management ([summary](https://computing.mit.edu/news/llms-factor-in-unrelated-information-when-recommending-medical-treatments/)). Use: justification + method for slang/typo perturbation arm.
- Mexican-Spanish slang jailbreak study (+3.3× ASR) and register-sensitivity work show safety degrades off-formal-register. Use: precedent that teen-register testing is a distinct, necessary evaluation arm.

## Recommended seed mix (top 5)

1. YAIR taxonomy + CAREBench dependency/grooming categories → scenario skeleton.
2. Spiral-Bench harness → multi-turn simulator + per-turn judge design.
3. ELEPHANT + SycEval → sycophancy/updating metrics and items.
4. DarkBench retention items → not-leaving/engagement-bait scenarios.
5. NPS Chat style + MIT register findings → teen-register perturbation layer.

## Must author ourselves

Multi-turn escalating self-harm arcs; abuse disclosures buried in rambling teen-voice stories; emotional-dependency arcs; rational-updating dialogues (user right vs wrong); teen personas in texting register; judge rubrics per axis. Nothing above covers long-horizon teen dialogue — that is the novel contribution.
