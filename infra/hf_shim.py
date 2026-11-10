#!/usr/bin/env python3
"""Local modal-shape -> vLLM OpenAI translator (stdlib only, CPU).

The ``modal`` provider in riptide speaks POST {"model","messages"} and reads
``text``/``response``/``output``. The HF-Job vLLM servers speak OpenAI
``/v1/chat/completions``. This shim translates, routing by modal model name:

- ``tiny-aya-global`` -> RIPTIDE_HF_TINY_URL as ``CohereLabs/tiny-aya-global``
- ``tinyaya-dpo2``    -> RIPTIDE_HF_TINY_URL as LoRA ``dpo2``
- ``aya-expanse-8b``  -> RIPTIDE_HF_AYA_URL  as ``CohereLabs/aya-expanse-8b``

Guards mirror the Modal endpoints: server cap MAX_NEW_TOKENS=256, prompt
guard MAX_PROMPT_CHARS=24000 (on concatenated content), greedy
(temperature 0). Errors surface as {"error": str} so the provider maps
429/5xx to retries exactly as with Modal.

Usage:
    HF_TOKEN="$(cat ~/.cache/huggingface/token)" \\
    RIPTIDE_HF_TINY_URL=https://... RIPTIDE_HF_AYA_URL=https://... \\
    python3 infra/hf_shim.py  # listens 127.0.0.1:8471
Never log the token.
"""
from __future__ import annotations

import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

LISTEN = ("127.0.0.1", int(os.environ.get("RIPTIDE_HF_SHIM_PORT", "8471")))
MAX_NEW_TOKENS = 256
MAX_PROMPT_CHARS = 24000

BASE_ID = "CohereLabs/tiny-aya-global"
AYA_ID = "CohereLabs/aya-expanse-8b"


def _routes():
    tiny = os.environ.get("RIPTIDE_HF_TINY_URL", "").rstrip("/")
    aya = os.environ.get("RIPTIDE_HF_AYA_URL", "").rstrip("/")
    return {
        "tiny-aya-global": (tiny, BASE_ID),
        "tinyaya-dpo2": (tiny, "dpo2"),
        "aya-expanse-8b": (aya, AYA_ID),
    }


def _passthrough(base_url: str, item: dict, token: str,
                 timeout: float = 300.0) -> tuple[int, dict]:
    """Forward a modal-shaped payload unchanged (steer job speaks it)."""
    req = urllib.request.Request(
        base_url + "/",
        data=json.dumps(item).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode() or "{}")
        except Exception:
            body = {"error": "HTTP %d" % exc.code}
        if isinstance(body, dict) and "text" not in body \
                and "choices" not in body:
            return exc.code, body
        return exc.code, {"error": "steer: HTTP %d" % exc.code}
    except Exception as exc:
        return 502, {"error": f"shim transport: {exc}"}


def _openai_chat(base_url: str, model: str, messages, max_tokens: int,
                 token: str, timeout: float = 300.0) -> tuple[int, dict]:
    payload = {"model": model, "messages": messages,
               "temperature": 0.0, "max_tokens": max_tokens}
    req = urllib.request.Request(
        base_url + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode() or "{}")
        except Exception:
            body = {"error": {"message": "HTTP %d" % exc.code}}
        return exc.code, body
    except Exception as exc:  # transport failure: 502 so provider retries
        return 502, {"error": {"message": f"shim transport: {exc}"}}


def _err_text(data: dict) -> str:
    err = data.get("error", data)
    if isinstance(err, dict):
        return str(err.get("message", err))[:300]
    return str(err)[:300]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, status: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/health", "/"):
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        try:
            item = json.loads(self.rfile.read(max(n, 0)).decode() or "{}")
        except Exception:
            self._send(400, {"error": "bad JSON"})
            return
        model = str(item.get("model", ""))
        messages = item.get("messages", [])
        if not isinstance(messages, list) or not messages:
            self._send(400, {"error": "expected non-empty 'messages' list"})
            return
        if model == "tinyaya-steer2":
            steer = os.environ.get("RIPTIDE_HF_STEER_URL", "").rstrip("/")
            if not steer:
                self._send(400, {"error": "shim: steer URL not configured"})
                return
            status, data = _passthrough(
                steer, item, os.environ.get("HF_TOKEN", ""))
            if status == 200 and isinstance(data, dict) \
                    and isinstance(data.get("text"), str):
                self._send(200, data)
            else:
                err = data.get("error", "steer: bad shape") \
                    if isinstance(data, dict) else "steer: bad shape"
                self._send(status if status in (429, 500, 502, 503) else 400,
                           {"error": str(err)[:300]})
            return
        routes = _routes()
        if model not in routes or not routes[model][0]:
            self._send(400, {"error": f"shim: unknown model {model!r}"})
            return
        prompt_len = sum(len(str(m.get("content", "")))
                         for m in messages if isinstance(m, dict))
        if prompt_len > MAX_PROMPT_CHARS:
            self._send(413, {"error": "prompt too long"})
            return
        try:
            max_tokens = max(1, min(int(item.get("max_new_tokens",
                                                 MAX_NEW_TOKENS)),
                                    MAX_NEW_TOKENS))
        except (TypeError, ValueError):
            max_tokens = MAX_NEW_TOKENS
        base_url, openai_model = routes[model]
        token = os.environ.get("HF_TOKEN", "")
        status, data = _openai_chat(base_url, openai_model, messages,
                                    max_tokens, token)
        if status == 200:
            try:
                content = data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                self._send(500, {"error": "shim: bad vLLM shape"})
                return
            self._send(200, {"text": content,
                             "choices": [{"message": {"role": "assistant",
                                                     "content": content}}]})
        else:
            # Preserve retryable statuses so the provider backs off as usual.
            self._send(status if status in (429, 500, 502, 503) else 400,
                       {"error": "vllm: " + _err_text(data)})


if __name__ == "__main__":
    HTTPServer(LISTEN, Handler).serve_forever()
