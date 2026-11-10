"""One chat() interface with per-provider adapters.

Model IDs look like "<provider>/<model>":

- ``openrouter/<org>/<name>:free`` — only ``:free`` models, others refused.
- ``gemini/<model>`` — e.g. ``gemini/gemini-2.5-flash-lite``; on 429/5xx
  falls back through ``RIPTIDE_GEMINI_FALLBACKS`` (see ``gemini_candidates``).
- ``cohere/<model>`` — e.g. ``cohere/command-a-03-2025``.
- ``claude/haiku`` / ``claude/sonnet`` — via ``claude -p``; opus/fable rejected.
- ``codex/gpt-6-luna`` — via ``codex exec``; only ``gpt-6-luna`` allowed.
- ``muse/<model>`` — via the Muse Code CLI
  (``muse exec --model <model> --reasoning-effort low``), run with cwd=/tmp;
  never via opencode (privacy setting stays off).
- ``modal/<model>`` — Tiny Aya endpoint placeholder (needs RIPTIDE_MODAL_URL).
- ``modaljudge/<model>`` — self-hosted vLLM judge endpoint
  (``infra/modal_judge.py``; needs RIPTIDE_MODAL_JUDGE_URL, not secret).

Secrets are read from the macOS Keychain at call time and never stored::

    security find-generic-password -a riptide -s <service> -w

``messages`` is a list of ``{"role": ..., "content": ...}`` dicts with roles
``system`` / ``user`` / ``assistant``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

KEYCHAIN_ACCOUNT = "riptide"
KEYCHAIN_SERVICES = {
    "openrouter": "riptide-openrouter",
    "gemini": "riptide-gemini",
    "cohere": "riptide-cohere",
}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
COHERE_URL = "https://api.cohere.com/v2/chat"

ALLOWED_CLAUDE_FAMILIES = ("haiku", "sonnet")
BLOCKED_CLAUDE_FAMILIES = ("opus", "fable")
ALLOWED_CODEX_MODEL = "gpt-6-luna"


class ProviderError(Exception):
    """A provider call failed (network, API error, or CLI error)."""


class RetryableError(ProviderError):
    """Transient failure: honor retries with backoff."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _keychain(service: str) -> str:
    """Read one secret from the macOS Keychain. Never log the value."""
    try:
        proc = subprocess.run(
            ["security", "find-generic-password",
             "-a", KEYCHAIN_ACCOUNT, "-s", service, "-w"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderError(f"keychain lookup failed for {service}: {exc}") from exc
    if proc.returncode != 0:
        raise ProviderError(
            f"missing keychain entry (account={KEYCHAIN_ACCOUNT} "
            f"service={service}); add it with `security add-generic-password`"
        )
    return proc.stdout.strip()


def _normalise_messages(messages) -> list[dict]:
    norm = []
    for m in messages:
        if isinstance(m, dict):
            norm.append({"role": m["role"], "content": m["content"]})
        else:  # tuple / object with role+content
            norm.append({"role": m[0], "content": m[1]})
    return norm


def _post_json(url: str, payload: dict, headers: dict | None = None,
               timeout: float = 120) -> tuple[int, dict, bytes]:
    """POST JSON, return (status, headers, body). Raise RetryableError on
    transport failure; non-2xx responses are returned for the caller to map."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RetryableError(f"transport error POST {url}: {exc}") from exc


def _check_status(provider: str, status: int, headers: dict, body: bytes) -> dict:
    if 200 <= status < 300:
        try:
            return json.loads(body.decode() or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{provider}: invalid JSON response") from exc
    if status == 429 or status >= 500:
        retry_after = None
        for key in ("Retry-After", "retry-after"):
            if key in headers:
                try:
                    retry_after = float(headers[key])
                except ValueError:
                    pass
        raise RetryableError(
            f"{provider}: HTTP {status}: {body.decode(errors='replace')[:300]}",
            retry_after=retry_after,
        )
    raise ProviderError(
        f"{provider}: HTTP {status}: {body.decode(errors='replace')[:300]}"
    )


# ---------------------------------------------------------------- adapters

def _openrouter_chat(model: str, messages: list[dict], timeout: float,
                   temperature: float | None = None) -> str:
    if not model.endswith(":free"):
        raise ValueError(
            f"openrouter: only :free models allowed, got {model!r}"
        )
    key = _keychain(KEYCHAIN_SERVICES["openrouter"])
    payload: dict = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    status, headers, body = _post_json(
        OPENROUTER_URL,
        payload,
        {"Authorization": f"Bearer {key}",
         "HTTP-Referer": "https://github.com/maximilienmil/riptide",
         "X-Title": "Riptide"},
        timeout,
    )
    data = _check_status("openrouter", status, headers, body)
    if isinstance(data.get("error"), dict):
        msg = data["error"].get("message", "unknown error")
        raise ProviderError(f"openrouter: {msg}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"openrouter: unexpected response shape: {data!r}"[:300]) from exc
    if isinstance(content, list):  # structured parts
        content = "".join(
            p.get("text", "") for p in content if isinstance(p, dict)
        )
    return content or ""


def _gemini_chat(model: str, messages: list[dict], timeout: float,
               temperature: float | None = None) -> str:
    key = _keychain(KEYCHAIN_SERVICES["gemini"])
    system_texts, contents = [], []
    for m in messages:
        if m["role"] == "system":
            system_texts.append(m["content"])
        else:
            contents.append({
                "role": "user" if m["role"] == "user" else "model",
                "parts": [{"text": m["content"]}],
            })
    payload: dict = {"contents": contents}
    if system_texts:
        payload["system_instruction"] = {
            "parts": [{"text": "\n".join(system_texts)}]
        }
    if temperature is not None:
        payload["generationConfig"] = {"temperature": temperature}
    url = GEMINI_URL.format(model=model) + f"?key={key}"
    status, headers, body = _post_json(url, payload, None, timeout)
    data = _check_status("gemini", status, headers, body)
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"gemini: unexpected response shape: {data!r}"[:300]) from exc


def _cohere_chat(model: str, messages: list[dict], timeout: float,
               temperature: float | None = None) -> str:
    key = _keychain(KEYCHAIN_SERVICES["cohere"])
    payload: dict = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    status, headers, body = _post_json(
        COHERE_URL,
        payload,
        {"Authorization": f"Bearer {key}"},
        timeout,
    )
    data = _check_status("cohere", status, headers, body)
    try:
        content = data["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise ProviderError(f"cohere: unexpected response shape: {data!r}"[:300]) from exc
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") for p in content if isinstance(p, dict)
        )
    return content or ""


def _format_prompt(messages: list[dict]) -> str:
    labels = {"system": "System", "user": "User", "assistant": "Assistant"}
    return "\n\n".join(
        f"{labels.get(m['role'], m['role'])}: {m['content']}" for m in messages
    )


def _run_cli(cmd: list[str], timeout: float, label: str) -> str:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderError(f"{label}: failed to launch: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RetryableError(f"{label}: timed out") from exc
    if proc.returncode != 0:
        raise ProviderError(
            f"{label}: exit {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()[:300]}"
        )
    out = proc.stdout.strip()
    if not out:
        raise ProviderError(f"{label}: empty response")
    return out


def _claude_chat(model: str, messages: list[dict], timeout: float) -> str:
    lowered = model.lower()
    if any(bad in lowered for bad in BLOCKED_CLAUDE_FAMILIES):
        raise ValueError(
            f"claude: opus/fable models are not allowed, got {model!r}"
        )
    if not any(fam in lowered for fam in ALLOWED_CLAUDE_FAMILIES):
        raise ValueError(
            f"claude: only haiku|sonnet allowed, got {model!r}"
        )
    return _run_cli(
        ["claude", "-p", "--model", model, _format_prompt(messages)],
        timeout, "claude",
    )


def _codex_chat(model: str, messages: list[dict], timeout: float) -> str:
    if model != ALLOWED_CODEX_MODEL:
        raise ValueError(
            f"codex: only {ALLOWED_CODEX_MODEL} allowed, got {model!r}"
        )
    return _run_cli(
        ["codex", "exec", "-m", model, _format_prompt(messages)],
        timeout, "codex",
    )


def _parse_muse_jsonl(stdout: str) -> str | None:
    """Extract the terminal text from ``muse exec --json`` JSONL output.

    Returns the last ``run_terminal`` payload text, or None when absent.
    """
    text: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") if isinstance(event, dict) else None
        if isinstance(payload, dict) and payload.get("kind") == "run_terminal" \
                and isinstance(payload.get("text"), str):
            text = payload["text"]
    return text


def _muse_chat(model: str, messages: list[dict], timeout: float,
             temperature: float | None = None) -> str:
    """Muse Spark (or sibling) via the Muse Code CLI.

    Runs ``muse exec --model <model> --reasoning-effort low <prompt>`` with
    cwd=/tmp (``--json`` so the reply is parsed from the ``run_terminal``
    event, never from log lines). Never via opencode: the privacy setting
    stays off. Agentic CLI calls are slow, so the timeout is floored at
    600 s.
    """
    del temperature  # CLI agents take no temperature flag; judge at default 0-ish
    cmd = ["muse", "exec", "--json", "--model", model,
           "--reasoning-effort", "low", _format_prompt(messages)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=max(timeout, 600), cwd="/tmp",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderError(f"muse: failed to launch: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RetryableError("muse: timed out") from exc
    if proc.returncode != 0:
        raise ProviderError(
            f"muse: exit {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()[:300]}"
        )
    text = _parse_muse_jsonl(proc.stdout)
    if text is None:
        raise ProviderError(
            f"muse: no run_terminal text in --json output: "
            f"{proc.stdout.strip()[:300]!r}"
        )
    out = text.strip()
    if not out:
        raise ProviderError("muse: empty response")
    return out


def gemini_candidates(model_id: str) -> list[str]:
    """Ordered ``gemini/<model>`` ids to try: primary first, then fallbacks.

    Fallbacks come from ``RIPTIDE_GEMINI_FALLBACKS`` (comma-separated bare
    model names, default ``gemini-2.5-flash``), deduplicated against the
    primary. Callers record which candidate actually answered.
    """
    try:
        _, primary = model_id.split("/", 1)
    except ValueError:
        raise ValueError(
            f"bad model_id {model_id!r}: expected '<provider>/<model>'"
        ) from None
    raw = os.environ.get("RIPTIDE_GEMINI_FALLBACKS", "gemini-2.5-flash")
    fallbacks = [m.strip() for m in raw.split(",") if m.strip()]
    return [f"gemini/{primary}"] + [
        f"gemini/{m}" for m in fallbacks if m != primary
    ]


def _modaljudge_chat(model: str, messages: list[dict], timeout: float,
                   temperature: float | None = None) -> str:
    """Self-hosted vLLM judge (OpenAI-compatible ``/chat`` shape).

    Endpoint URL comes from ``RIPTIDE_MODAL_JUDGE_URL`` (not secret —
    the Modal URL carries no credentials). Surfaces endpoint-reported
    ``{"error": ...}`` verbatim and maps 429/5xx to RetryableError via
    ``_check_status``.
    """
    url = os.environ.get("RIPTIDE_MODAL_JUDGE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "modaljudge: judge endpoint not configured; "
            "set RIPTIDE_MODAL_JUDGE_URL to the Modal web endpoint URL"
        )
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": 0.0 if temperature is None else temperature,
        "thinking": os.environ.get(
            "RIPTIDE_MODAL_JUDGE_THINKING", "") == "1",
    }
    status, headers, body = _post_json(url, payload, None, timeout)
    data = _check_status("modaljudge", status, headers, body)
    if isinstance(data, dict) and isinstance(data.get("error"), str):
        raise ProviderError(f"modaljudge: {data['error']}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(
            f"modaljudge: unexpected response shape: {data!r}"[:300]
        ) from exc
    return content or ""


def _modal_chat(model: str, messages: list[dict], timeout: float) -> str:
    url = os.environ.get("RIPTIDE_MODAL_URL", "").strip()
    if not url:
        raise RuntimeError(
            "modal: Tiny Aya endpoint not configured; "
            "set RIPTIDE_MODAL_URL to the Modal web endpoint URL"
        )
    status, headers, body = _post_json(
        url, {"model": model, "messages": messages}, None, timeout,
    )
    data = _check_status("modal", status, headers, body)
    # Surface endpoint-reported errors verbatim instead of a shape dump,
    # whether the endpoint returns {"error": ...} directly or (legacy)
    # a serialised (payload, status) pair carrying an error dict.
    if isinstance(data, dict) and isinstance(data.get("error"), str):
        raise ProviderError(f"modal: {data['error']}")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("error"), str):
                raise ProviderError(f"modal: {item['error']}")
    if isinstance(data, dict):
        for key in ("text", "response", "output"):
            if isinstance(data.get(key), str):
                return data[key]
    raise ProviderError(f"modal: unexpected response shape: {data!r}"[:300])


_ADAPTERS = {
    "openrouter": _openrouter_chat,
    "gemini": _gemini_chat,
    "cohere": _cohere_chat,
    "claude": _claude_chat,
    "codex": _codex_chat,
    "muse": _muse_chat,
    "modal": _modal_chat,
    "modaljudge": _modaljudge_chat,
}


# ---------------------------------------------------------------- plumbing

def _cache_dir() -> Path:
    override = os.environ.get("RIPTIDE_CACHE_DIR", "").strip()
    base = Path(override) if override else Path.home() / ".cache" / "riptide"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _cache_key(model_id: str, messages: list[dict],
               temperature: float | None = None) -> str:
    payload: dict = {"model": model_id, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if model_id.split("/", 1)[0] == "modaljudge":
        # The thinking flag changes the endpoint's reply; without it a
        # thinking run would replay cached non-thinking responses.
        payload["thinking"] = os.environ.get(
            "RIPTIDE_MODAL_JUDGE_THINKING", "") == "1"
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _log_turn(model_id: str, messages: list[dict], response: str) -> None:
    if os.environ.get("RIPTIDE_NO_LOG", "") == "1":
        return
    override = os.environ.get("RIPTIDE_TRANSCRIPT_LOG", "").strip()
    path = Path(override) if override else Path("runs/provider_transcripts.jsonl")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "model": model_id,
                "messages": messages,
                "response": response,
            }) + "\n")
    except OSError:
        pass  # logging is best-effort; never fail a run over it


def chat(model_id: str, messages, *, timeout: float = 120,
         max_retries: int = 3, no_cache: bool = False,
         temperature: float | None = None) -> str:
    """Send ``messages`` to ``model_id`` ("<provider>/<model>") and return text.

    Validates provider allowlists (openrouter ``:free`` only, claude
    haiku|sonnet, codex ``gpt-6-luna``) before touching the network, caches
    successful responses on disk keyed by hash(model, messages), and retries
    transient (429/5xx/transport) failures with backoff honoring Retry-After.
    ``temperature`` is forwarded to HTTP API adapters only (judges use 0).
    """
    try:
        provider, model = model_id.split("/", 1)
    except ValueError:
        raise ValueError(
            f"bad model_id {model_id!r}: expected '<provider>/<model>'"
        ) from None
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        raise ValueError(
            f"unknown provider {provider!r}; expected one of "
            f"{sorted(_ADAPTERS)}"
        )
    norm = _normalise_messages(messages)

    # Refusals (ValueError/RuntimeError) raise before cache/network.
    if provider == "openrouter" and not model.endswith(":free"):
        raise ValueError(f"openrouter: only :free models allowed, got {model!r}")
    if provider == "claude":
        lowered = model.lower()
        if any(b in lowered for b in BLOCKED_CLAUDE_FAMILIES) or not any(
                f in lowered for f in ALLOWED_CLAUDE_FAMILIES):
            raise ValueError(
                f"claude: only haiku|sonnet allowed, got {model!r}"
            )
    if provider == "codex" and model != ALLOWED_CODEX_MODEL:
        raise ValueError(
            f"codex: only {ALLOWED_CODEX_MODEL} allowed, got {model!r}"
        )
    if provider == "modal" and not os.environ.get("RIPTIDE_MODAL_URL", "").strip():
        raise RuntimeError(
            "modal: Tiny Aya endpoint not configured; set RIPTIDE_MODAL_URL"
        )
    if provider == "modaljudge" and not os.environ.get(
            "RIPTIDE_MODAL_JUDGE_URL", "").strip():
        raise RuntimeError(
            "modaljudge: judge endpoint not configured; "
            "set RIPTIDE_MODAL_JUDGE_URL"
        )

    cache_file = _cache_dir() / f"{_cache_key(model_id, norm, temperature)}.json"
    if not no_cache and cache_file.exists():
        try:
            return json.loads(cache_file.read_text())["response"]
        except (OSError, ValueError, KeyError):
            pass  # corrupt entry: fall through to a live call

    last: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            if provider in ("openrouter", "gemini", "cohere", "modaljudge"):
                response = adapter(model, norm, timeout, temperature)
            else:
                response = adapter(model, norm, timeout)
            try:
                cache_file.write_text(json.dumps({"response": response}))
            except OSError:
                pass
            _log_turn(model_id, norm, response)
            return response
        except (ValueError, RuntimeError):
            raise
        except RetryableError as exc:
            last = exc
            if attempt < max_retries:
                wait = exc.retry_after if exc.retry_after else min(2 ** attempt * 2, 30)
                time.sleep(wait)
        except ProviderError as exc:
            last = exc
            if attempt < max_retries:
                time.sleep(min(2 ** attempt * 2, 30))
    assert last is not None
    raise last
