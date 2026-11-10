"""Riptide Modal judge endpoint (vLLM, Qwen3-32B-AWQ).

Self-hosted judge B: Qwen3-32B-AWQ served with vLLM (continuous
batching) as an OpenAI-compatible POST endpoint that riptide's
``modaljudge`` provider calls::

    RIPTIDE_MODAL_JUDGE_URL="https://<workspace>--riptide-judge-judgeserve-chat.modal.run" \
        uv run python -c "from riptide.providers import chat; ..."

Why this model: 32B-class open instruct model (Apache-2.0, ungated — no
HF approval needed), fits one A100-80GB as AWQ with room for a 32k
context window, and Qwen3's ``enable_thinking=False`` template flag
gives strict-JSON answers without a reasoning trace (judge outputs must
parse as ``{"turns": [...]}``). NOT Cohere/Aya (tested models) and not
Muse (judge A).

Request shape (OpenAI-compatible subset):
    POST {"model": "<ignored>", "messages": [{"role": ..., "content": ...}],
          "temperature": 0.0, "max_tokens": 2048, "thinking": false}

``thinking: true`` enables Qwen3's <think> trace for harder checklist
following; the server strips the trace and returns only the verdict, so
the reply still parses as JSON.

Response: ``{"choices": [{"message": {"role": "assistant",
"content": "<judge JSON>"}}], "usage": {...}}`` (plus a ``text`` alias
for convenience). URL is not secret; never send tokens.

Deploy / refresh::
    uvx modal deploy infra/modal_judge.py

Cost control: A100-80GB ($2.50/hr list), ``min_containers=0``
(scale-to-zero), container idles out after 120 s, per-request token
cap, input-length cap. vLLM serves concurrent requests from one engine
(continuous batching); bursty judge traffic needs no extra plumbing.
"""

import modal

APP_NAME = "riptide-judge"
MODEL_ID = "Qwen/Qwen3-32B-AWQ"
# Judge prompts are whole conversations (~20-30k chars); 32k tokens of
# context comfortably holds prompt + a ~2k-token verdict.
MAX_MODEL_LEN = 32768
MAX_NEW_TOKENS = 2048
# Thinking traces reason before answering; the verdict still fits, but
# the trace itself needs headroom.
MAX_NEW_TOKENS_THINKING = 4096
# ~3 chars/token guard: 100k chars ~= 30k tokens, inside the window.
MAX_PROMPT_CHARS = 100000

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "vllm",
        "fastapi[standard]",
    )
)

app = modal.App(APP_NAME)


@app.cls(
    gpu="A100-80GB",
    timeout=900,
    scaledown_window=120,
    min_containers=0,
    max_containers=1,
    image=image,
)
class JudgeServe:
    @modal.enter()
    def load(self):
        import os

        # Same FlashInfer-sampler JIT failure seen in stack-smoke §7:
        # the fused sampler dies on driver-only boxes, so force the
        # native sampler before vllm is imported. Identical output for
        # greedy (temperature 0) decoding.
        os.environ["VLLM_USE_FLASHINFER_SAMPLER"] = "0"
        from vllm import LLM

        self.llm = LLM(
            model=MODEL_ID,
            max_model_len=MAX_MODEL_LEN,
            trust_remote_code=False,
        )

    @modal.fastapi_endpoint(method="POST")
    def chat(self, item: dict):
        import time

        from fastapi.responses import JSONResponse
        from vllm import SamplingParams

        t0 = time.time()
        messages = item.get("messages", [])
        if not isinstance(messages, list) or not messages:
            return JSONResponse(
                status_code=400,
                content={"error": "expected non-empty 'messages' list"})
        for m in messages:
            if not isinstance(m, dict) or not isinstance(
                    m.get("content"), str):
                return JSONResponse(
                    status_code=400,
                    content={"error": "each message needs str 'content'"})
        prompt_chars = sum(len(m["content"]) for m in messages)
        if prompt_chars > MAX_PROMPT_CHARS:
            return JSONResponse(
                status_code=413, content={"error": "prompt too long"})
        try:
            temperature = float(item.get("temperature", 0.0))
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"error": "temperature must be a number"})
        try:
            max_tokens = int(item.get("max_tokens", MAX_NEW_TOKENS))
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"error": "max_tokens must be an integer"})
        thinking = bool(item.get("thinking", False))
        cap = MAX_NEW_TOKENS_THINKING if thinking else MAX_NEW_TOKENS
        max_tokens = max(1, min(max_tokens, cap))
        params = SamplingParams(
            temperature=temperature, max_tokens=max_tokens)
        try:
            # Qwen3 is a hybrid thinking model. Non-thinking mode answers
            # directly (strict JSON); thinking mode reasons first, and the
            # server strips the trace so the reply still parses as JSON.
            outputs = self.llm.chat(
                messages, params,
                chat_template_kwargs={"enable_thinking": thinking},
            )
            text = outputs[0].outputs[0].text.strip()
            if thinking and "</think>" in text:
                text = text.split("</think>")[-1].strip()
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content={"error": f"generation failed: {exc}"})
        if not text:
            return JSONResponse(
                status_code=500, content={"error": "empty generation"})
        return {
            "text": text,
            "choices": [{"message": {"role": "assistant",
                                     "content": text}}],
            "usage": {"prompt_chars": prompt_chars},
            "elapsed_s": round(time.time() - t0, 2),
        }
