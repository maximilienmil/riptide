"""Riptide Aya Expanse 8B chat endpoint (Modal).

Serves CohereLabs/aya-expanse-8b as a scale-to-zero web endpoint that
riptide's ``modal`` provider can call::

    RIPTIDE_MODAL_URL="https://<workspace>--riptide-aya8b-ayaexpansechat-chat.modal.run" \
        python -m riptide.cli chat modal/aya-expanse-8b "..."

Request shape (matches ``riptide/providers.py::_modal_chat``):
    POST {"model": "<ignored>", "messages": [{"role": ..., "content": ...}],
          "max_new_tokens": 256}

Response: ``{"text": "<assistant reply>"}`` (plus an OpenAI-style
``choices`` block for convenience). URL is not secret; never send tokens.

Mirrors ``infra/modal_endpoint.py`` (Tiny Aya Global) exactly: same
endpoint-greedy sampling (``do_sample=False``), same server cap
``MAX_NEW_TOKENS=256``, same prompt guard ``MAX_PROMPT_CHARS=24000``,
same A10G scale-to-zero shape (``min_containers=0``). Only the app name
and the HF model id differ.

Deploy / refresh::
    uvx modal deploy infra/modal_aya_expanse.py

Cost control: A10G, ``min_containers=0`` (scale-to-zero), container
idles out after 60 s, per-request token cap, input-length cap.
"""

import modal

APP_NAME = "riptide-aya8b"
AYA_8B = "CohereLabs/aya-expanse-8b"
MAX_NEW_TOKENS = 256
# 12-turn histories run ~20-24k chars (long assistant replies); Aya
# Expanse 8B's 8k-token window holds ~32k chars, so 24k stays safely
# inside it.
MAX_PROMPT_CHARS = 24000

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch",
        "transformers>=4.48",
        "accelerate",
        "safetensors",
        "huggingface_hub",
        "fastapi[standard]",
    )
)

app = modal.App(APP_NAME)


@app.cls(
    # A10G: L4 pool was exhausted for hours on 2026-11-03/04 (cold starts
    # never got a worker); scale-to-zero keeps cost to eval traffic only.
    gpu="A10G",
    timeout=600,
    scaledown_window=60,
    min_containers=0,
    max_containers=2,
    secrets=[modal.Secret.from_name("huggingface-secret")],
    image=image,
)
class AyaExpanseChat:
    @modal.enter()
    def load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tok = AutoTokenizer.from_pretrained(
            AYA_8B, trust_remote_code=False
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            AYA_8B,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=False,
        )
        self.model.eval()
        self.device = next(self.model.parameters()).device

    @modal.fastapi_endpoint(method="POST")
    def chat(self, item: dict):
        import time
        import torch
        from fastapi.responses import JSONResponse

        t0 = time.time()
        messages = item.get("messages", [])
        if not isinstance(messages, list) or not messages:
            return JSONResponse(
                status_code=400,
                content={"error": "expected non-empty 'messages' list"})
        max_new = int(item.get("max_new_tokens", MAX_NEW_TOKENS))
        max_new = max(1, min(max_new, MAX_NEW_TOKENS))
        try:
            prompt = self.tok.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=False
            )
        except Exception as exc:
            return JSONResponse(
                status_code=400, content={"error": f"bad messages: {exc}"})
        if len(prompt) > MAX_PROMPT_CHARS:
            return JSONResponse(
                status_code=413, content={"error": "prompt too long"})
        enc = self.tok(prompt, return_tensors="pt").to(self.device)
        try:
            with torch.no_grad():
                out = self.model.generate(
                    **enc,
                    max_new_tokens=max_new,
                    do_sample=False,
                    pad_token_id=self.tok.pad_token_id or self.tok.eos_token_id,
                )
        except Exception as exc:
            return JSONResponse(
                status_code=500, content={"error": f"generation failed: {exc}"})
        new_tokens = out[0][enc["input_ids"].shape[1]:]
        text = self.tok.decode(new_tokens, skip_special_tokens=True).strip()
        return {
            "text": text,
            "choices": [{"message": {"role": "assistant",
                                     "content": text}}],
            "gen_tokens": len(new_tokens),
            "elapsed_s": round(time.time() - t0, 2),
        }
