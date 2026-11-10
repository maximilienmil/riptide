#!/usr/bin/env python3
# /// script
# dependencies = [
#   "torch",
#   "transformers>=4.48",
#   "accelerate",
#   "safetensors",
#   "huggingface_hub",
#   "fastapi",
#   "uvicorn",
#   "safetune @ git+https://github.com/Lexsi-Labs/SafeTune.git",
# ]
# ///
"""Steer2 CAA server for HF Jobs (uv script).

Ports ``Steer2Chat`` from ``infra/modal_repair_v2.py`` verbatim (same model,
same greedy decode, same guards) but serves plain HTTP instead of Modal:
POST {"/", "/chat"} {"model", "messages", "max_new_tokens"} -> {"text", ...}.

Run on HF Jobs, e.g.:
    hf jobs uv run --flavor t4-small -s HF_TOKEN \\
        -v /tmp/hfart/steerv2:/mnt/art:ro --expose 8000 \\
        --timeout 3h --detach infra/hf_serve_steer.py

Artifacts: /mnt/art/steer-v2/{config.json, vectors.pt} (volume mount).
Gated base model needs HF_TOKEN in env.
"""
from __future__ import annotations

import json
import os
import time

import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from transformers import AutoModelForCausalLM, AutoTokenizer

TINY_AYA = "CohereLabs/tiny-aya-global"
ART = os.environ.get("RIPTIDE_STEER_ART", "/mnt/art/steer-v2")
MAX_NEW_TOKENS = 256
MAX_PROMPT_CHARS = 24000

app = FastAPI()
TOK = None
MODEL = None


@app.on_event("startup")
def load():
    global TOK, MODEL
    TOK = AutoTokenizer.from_pretrained(TINY_AYA, trust_remote_code=False)
    base = AutoModelForCausalLM.from_pretrained(
        TINY_AYA,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=False,
    )
    base.eval()
    try:
        from safetune.interventions.steer.caa import CAAModel
    except ImportError:
        from safetune.steer.caa import CAAModel  # type: ignore[no-redef]
    with open(os.path.join(ART, "config.json")) as fh:
        cfg = json.load(fh)
    vecs = torch.load(os.path.join(ART, "vectors.pt"), map_location="cpu",
                      weights_only=True)
    layer, alpha = int(cfg["layer"]), float(cfg["alpha"])
    dev = next(base.parameters()).device
    CAAModel(base, {layer: vecs[layer].to(dev)},
             strength=alpha).install()
    MODEL = base
    print("STEER_LOADED layer=%d alpha=%s" % (layer, alpha), flush=True)


def _chat(item: dict):
    t0 = time.time()
    messages = item.get("messages", [])
    if not isinstance(messages, list) or not messages:
        return JSONResponse(
            status_code=400,
            content={"error": "expected non-empty 'messages' list"})
    max_new = max(1, min(int(item.get("max_new_tokens", MAX_NEW_TOKENS)),
                         MAX_NEW_TOKENS))
    try:
        prompt = TOK.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False)
    except Exception as exc:
        return JSONResponse(
            status_code=400, content={"error": f"bad messages: {exc}"})
    if len(prompt) > MAX_PROMPT_CHARS:
        return JSONResponse(
            status_code=413, content={"error": "prompt too long"})
    try:
        dev = next(MODEL.parameters()).device
    except StopIteration:
        dev = "cuda"
    enc = TOK(prompt, return_tensors="pt").to(dev)
    try:
        with torch.no_grad():
            out = MODEL.generate(
                **enc, max_new_tokens=max_new, do_sample=False,
                pad_token_id=TOK.pad_token_id or TOK.eos_token_id)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": f"generation failed: {exc}"})
    new_tokens = out[0][enc["input_ids"].shape[1]:]
    text = TOK.decode(new_tokens, skip_special_tokens=True).strip()
    return {"text": text,
            "choices": [{"message": {"role": "assistant",
                                     "content": text}}],
            "gen_tokens": len(new_tokens),
            "elapsed_s": round(time.time() - t0, 2)}


@app.post("/")
def root(item: dict):
    return _chat(item)


@app.post("/chat")
def chat(item: dict):
    return _chat(item)


@app.get("/health")
def health():
    return {"ok": MODEL is not None}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
