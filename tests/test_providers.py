"""Provider tests with faked transport/keychain/CLI. No network, no secrets."""

import json

import pytest

from riptide import providers


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RIPTIDE_NO_LOG", "1")
    monkeypatch.setenv("RIPTIDE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(providers, "_keychain", lambda service: "test-key")


def _ok_response(text, monkeypatch, calls=None):
    body = json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": text}}]}
    ).encode()

    def fake_post(url, payload, headers=None, timeout=120):
        if calls is not None:
            calls.append((url, payload))
        return 200, {}, body

    monkeypatch.setattr(providers, "_post_json", fake_post)


def test_openrouter_refuses_non_free(monkeypatch):
    with pytest.raises(ValueError, match=":free"):
        providers.chat("openrouter/meta-llama/llama-3.3-70b-instruct",
                       [{"role": "user", "content": "hi"}])


def test_openrouter_free_roundtrip(monkeypatch):
    _ok_response("hello", monkeypatch)
    out = providers.chat("openrouter/x/y:free",
                         [{"role": "user", "content": "hi"}])
    assert out == "hello"


def test_cache_hit_avoids_network(monkeypatch):
    calls = []
    _ok_response("cached-me", monkeypatch, calls)
    msgs = [{"role": "user", "content": "hi"}]
    first = providers.chat("openrouter/x/y:free", msgs)
    second = providers.chat("openrouter/x/y:free", msgs)
    assert first == second == "cached-me"
    assert len(calls) == 1


def test_retry_on_429_then_success(monkeypatch):
    body = json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    ).encode()
    responses = [(429, {"Retry-After": "0"}, b"slow down"), (200, {}, body)]
    monkeypatch.setattr(
        providers, "_post_json",
        lambda *a, **k: responses.pop(0),
    )
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    out = providers.chat("openrouter/x/y:free",
                         [{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert responses == []


def test_claude_rejects_opus_fable():
    for bad in ("claude/opus-4", "claude/fable-1", "claude/sonnet-opus-x"):
        with pytest.raises(ValueError, match="[Oo]pus|[Ff]able|haiku"):
            providers.chat(bad, [{"role": "user", "content": "hi"}])


def test_claude_accepts_haiku_sonnet(monkeypatch):
    seen = {}

    def fake_run(cmd, timeout, label):
        seen["cmd"] = cmd
        return "claude says hi"

    monkeypatch.setattr(providers, "_run_cli", fake_run)
    out = providers.chat("claude/sonnet", [{"role": "user", "content": "hi"}])
    assert out == "claude says hi"
    assert seen["cmd"][:3] == ["claude", "-p", "--model"]


def test_codex_rejects_non_luna():
    with pytest.raises(ValueError, match="gpt-6-luna"):
        providers.chat("codex/gpt-5",
                       [{"role": "user", "content": "hi"}])


def test_codex_accepts_luna(monkeypatch):
    monkeypatch.setattr(
        providers, "_run_cli", lambda cmd, timeout, label: "luna says hi")
    out = providers.chat("codex/gpt-6-luna",
                         [{"role": "user", "content": "hi"}])
    assert out == "luna says hi"


def _muse_jsonl(text):
    import json as _json
    return (
        '{"payload": {"kind": "other"}}\n'
        + _json.dumps({"payload": {"kind": "run_terminal",
                                   "text": text}}) + "\n"
    )


def test_muse_uses_muse_cli_in_tmp(monkeypatch):
    import subprocess
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = _muse_jsonl("muse says hi")
        stderr = "muse: workspace root: /private/tmp\n"

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = providers.chat("muse/muse-spark-1.3-contributor",
                         [{"role": "user", "content": "hi"}])
    assert out == "muse says hi"
    assert seen["cmd"][:6] == ["muse", "exec", "--json", "--model",
                               "muse-spark-1.3-contributor",
                               "--reasoning-effort"]
    assert "low" in seen["cmd"]
    assert seen["cmd"][-1].endswith("hi")
    assert "opencode" not in seen["cmd"]
    assert seen["kwargs"]["cwd"] == "/tmp"
    assert seen["kwargs"]["timeout"] >= 600


def test_muse_rejects_missing_terminal_text(monkeypatch):
    import subprocess

    class FakeProc:
        returncode = 0
        stdout = '{"payload": {"kind": "other"}}\n'
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: FakeProc())
    with pytest.raises(providers.ProviderError, match="run_terminal"):
        providers.chat("muse/muse-spark-1.3-contributor",
                       [{"role": "user", "content": "hi"}])


def test_gemini_candidates_primary_first(monkeypatch):
    monkeypatch.setenv("RIPTIDE_GEMINI_FALLBACKS",
                       "gemini-2.0-flash, gemini-2.5-flash-lite")
    assert providers.gemini_candidates(
        "gemini/gemini-2.5-flash-lite") == [
        "gemini/gemini-2.5-flash-lite", "gemini/gemini-2.0-flash",
    ]


def test_temperature_forwarded_to_api(monkeypatch):
    calls = []

    def fake_post(url, payload, headers=None, timeout=120):
        calls.append(payload)
        body = json.dumps(
            {"choices": [{"message": {"role": "assistant",
                                      "content": "ok"}}]}).encode()
        return 200, {}, body

    monkeypatch.setattr(providers, "_post_json", fake_post)
    providers.chat("openrouter/x/y:free", [{"role": "user", "content": "hi"}],
                   temperature=0.0)
    assert calls[0]["temperature"] == 0.0


def test_unknown_provider():
    with pytest.raises(ValueError, match="unknown provider"):
        providers.chat("nope/model", [{"role": "user", "content": "hi"}])


def test_modal_placeholder_without_url(monkeypatch):
    monkeypatch.delenv("RIPTIDE_MODAL_URL", raising=False)
    with pytest.raises(RuntimeError, match="RIPTIDE_MODAL_URL"):
        providers.chat("modal/tiny-aya",
                       [{"role": "user", "content": "hi"}])


def test_modal_surfaces_endpoint_error_message(monkeypatch):
    monkeypatch.setenv("RIPTIDE_MODAL_URL", "https://example.com/chat")
    body = json.dumps({"error": "prompt too long"}).encode()
    monkeypatch.setattr(
        providers, "_post_json", lambda *a, **k: (200, {}, body))
    with pytest.raises(providers.ProviderError, match="modal: prompt too long"):
        providers.chat("modal/tiny-aya",
                       [{"role": "user", "content": "hi"}])
    legacy = json.dumps([{"error": "bad messages: x"}, 400]).encode()
    monkeypatch.setattr(
        providers, "_post_json", lambda *a, **k: (200, {}, legacy))
    with pytest.raises(providers.ProviderError, match="modal: bad messages"):
        providers.chat("modal/tiny-aya",
                       [{"role": "user", "content": "hi"}], no_cache=True)


def test_modaljudge_without_url(monkeypatch):
    monkeypatch.delenv("RIPTIDE_MODAL_JUDGE_URL", raising=False)
    with pytest.raises(RuntimeError, match="RIPTIDE_MODAL_JUDGE_URL"):
        providers.chat("modaljudge/qwen3-32b-awq",
                       [{"role": "user", "content": "hi"}])


def test_modaljudge_parses_openai_choices(monkeypatch):
    monkeypatch.setenv("RIPTIDE_MODAL_JUDGE_URL",
                       "https://example.com/judge")
    calls = []

    def fake_post(url, payload, headers=None, timeout=120):
        calls.append((url, payload))
        body = json.dumps(
            {"choices": [{"message": {"role": "assistant",
                                      "content": '{"turns": []}'}}]}).encode()
        return 200, {}, body

    monkeypatch.setattr(providers, "_post_json", fake_post)
    out = providers.chat("modaljudge/qwen3-32b-awq",
                         [{"role": "user", "content": "hi"}],
                         temperature=0.0)
    assert out == '{"turns": []}'
    assert calls[0][0] == "https://example.com/judge"
    assert calls[0][1]["messages"] == [{"role": "user", "content": "hi"}]
    assert calls[0][1]["temperature"] == 0.0
    assert calls[0][1]["thinking"] is False


def test_modaljudge_cache_separates_thinking(monkeypatch):
    msgs = [{"role": "user", "content": "hi"}]
    monkeypatch.delenv("RIPTIDE_MODAL_JUDGE_THINKING", raising=False)
    plain = providers._cache_key("modaljudge/qwen3-32b-awq", msgs, 0.0)
    monkeypatch.setenv("RIPTIDE_MODAL_JUDGE_THINKING", "1")
    thinking = providers._cache_key("modaljudge/qwen3-32b-awq", msgs, 0.0)
    assert plain != thinking


def test_modaljudge_thinking_flag(monkeypatch):
    monkeypatch.setenv("RIPTIDE_MODAL_JUDGE_URL",
                       "https://example.com/judge")
    monkeypatch.setenv("RIPTIDE_MODAL_JUDGE_THINKING", "1")
    calls = []

    def fake_post(url, payload, headers=None, timeout=120):
        calls.append((url, payload))
        body = json.dumps(
            {"choices": [{"message": {"role": "assistant",
                                      "content": "ok"}}]}).encode()
        return 200, {}, body

    monkeypatch.setattr(providers, "_post_json", fake_post)
    providers.chat("modaljudge/qwen3-32b-awq",
                   [{"role": "user", "content": "hi"}])
    assert calls[0][1]["thinking"] is True


def test_modaljudge_surfaces_endpoint_error(monkeypatch):
    monkeypatch.setenv("RIPTIDE_MODAL_JUDGE_URL",
                       "https://example.com/judge")
    body = json.dumps({"error": "prompt too long"}).encode()
    monkeypatch.setattr(
        providers, "_post_json", lambda *a, **k: (200, {}, body))
    with pytest.raises(providers.ProviderError,
                       match="modaljudge: prompt too long"):
        providers.chat("modaljudge/qwen3-32b-awq",
                       [{"role": "user", "content": "hi"}])


def test_transcript_log_has_no_key(monkeypatch, tmp_path):
    log = tmp_path / "t.jsonl"
    monkeypatch.setenv("RIPTIDE_TRANSCRIPT_LOG", str(log))
    monkeypatch.setenv("RIPTIDE_NO_LOG", "0")
    monkeypatch.setattr(providers, "_keychain",
                        lambda service: "SUPERSECRETKEY123")
    _ok_response("hi", monkeypatch)
    providers.chat("openrouter/x/y:free", [{"role": "user", "content": "hi"}])
    content = log.read_text()
    assert "SUPERSECRETKEY123" not in content
    assert "openrouter/x/y:free" in content
