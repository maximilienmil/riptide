"""Riptide second Modal judge endpoint (vLLM, Qwen2.5-72B-Instruct-AWQ).

70B-class judge B candidate: Llama-3.3-70B-Instruct is gated on the Hub
and user maximilianmilo is NOT granted (download attempt -> "Access
denied. This repository requires approval."), so per the task brief we
use the best ungated 70B-class alternative:
Qwen/Qwen2.5-72B-Instruct-AWQ (official AWQ quant, ungated, Apache-2.0).

Same OpenAI-compatible POST shape as infra/modal_judge.py so riptide's
``modaljudge`` provider calls it unchanged::

    RIPTIDE_MODAL_JUDGE_URL="https://<workspace>--riptide-judge-llama-judgeserve-chat.modal.run" \
        uv run python runs/pilot-rejudge/modal-judge-llama/judge_modal_llama.py

Separate Modal app (``riptide-judge-llama``) — the ``riptide-judge``
(Qwen3-32B) app is untouched. Differences from the 32B endpoint:

- No ``enable_thinking`` chat-template kwarg: Qwen2.5's template does
  not accept it, so the ``thinking`` payload field is accepted and
  ignored (judge outputs must still parse as ``{"turns": [...]}``).
- ``max_model_len=24576``: 72B AWQ weights (~39GB) leave less room
  for KV cache on one A100-80GB than the 32B model; 24k tokens still
  holds the largest pilot judge prompt (~49k chars ~= ~14k tokens)
  plus a ~2k-token verdict. Input-length cap enforced below.
- ``trust_remote_code`` stays False (Qwen2.5 needs no remote code).

Deploy / refresh::

    uvx modal deploy infra/modal_judge_llama.py

Cost control: A100-80GB ($2.50/hr list), ``min_containers=0``
(scale-to-zero), container idles out after 120 s, per-request token
cap, input-length cap.
"""

import modal

APP_NAME = "riptide-judge-llama"
MODEL_ID = "Qwen/Qwen2.5-72B-Instruct-AWQ"
# Largest pilot judge prompt is ~49k chars (~14k tokens); 24k holds
# prompt + a ~2k-token verdict with margin.
MAX_MODEL_LEN = 24576
MAX_NEW_TOKENS = 2048
# ~3.5 chars/token guard: 70k chars ~= 20k tokens, inside the window.
MAX_PROMPT_CHARS = 70000

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
        # Accepted for shape-compatibility with the modaljudge provider
        # (which always sends it); ignored — Qwen2.5 answers directly.
        max_tokens = max(1, min(max_tokens, MAX_NEW_TOKENS))
        params = SamplingParams(
            temperature=temperature, max_tokens=max_tokens)
        try:
            outputs = self.llm.chat(messages, params)
            text = outputs[0].outputs[0].text.strip()
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
