"""A demómodell szolgáltatója: alapból OpenAI, LLM_PROVIDER=gemini-vel Gemini."""
import os, sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import server


def test_default_is_openai(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    client, model = server._llm_client()
    assert "openai.com" in str(client.base_url) and model


def test_gemini_uses_its_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    client, model = server._llm_client()
    assert "generativelanguage.googleapis.com" in str(client.base_url)
    assert model.startswith("gemini")


def test_gemini_without_key_is_a_clean_503(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(HTTPException) as e:
        server._llm_client()
    assert e.value.status_code == 503


def test_gemini_quota_pauses_the_demo():
    assert server._quota_exhausted(Exception("429 RESOURCE_EXHAUSTED: quota"))


def test_gemini_gets_the_strict_json_rules(monkeypatch):
    import asyncio
    seen = {}

    class Fake:
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    seen.update(kw)
                    class R: choices = [type("C", (), {"message": type("M", (), {"content": "{}"})()})()]
                    return R()

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setattr(server, "_llm_client", lambda: (Fake(), "gemini-x"))
    asyncio.run(server._call_llm("SYS", "hi"))
    assert seen["messages"][0]["content"].startswith("SYS") and "KIMENETI SZABÁLYOK" in seen["messages"][0]["content"]
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    asyncio.run(server._call_llm("SYS", "hi"))
    assert seen["messages"][0]["content"] == "SYS"


def _rate_limit(msg):
    import httpx, openai
    r = httpx.Response(429, request=httpx.Request("POST", "https://x"))
    return openai.RateLimitError(msg, response=r, body=None)


def _fake_client(errors):
    class Fake:
        calls = 0
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    Fake.calls += 1
                    if errors:
                        raise errors.pop(0)
                    class R: choices = [type("C", (), {"message": type("M", (), {"content": "{}"})()})()]
                    return R()
    return Fake


def test_per_minute_limit_is_waited_out(monkeypatch):
    import asyncio
    fake = _fake_client([_rate_limit("RESOURCE_EXHAUSTED PerMinute"), _rate_limit("RESOURCE_EXHAUSTED PerMinute")])
    monkeypatch.setattr(server, "_llm_client", lambda: (fake(), "m"))
    monkeypatch.setattr(server, "RATE_LIMIT_WAITS", (0, 0, 0))
    assert asyncio.run(server._call_llm("S", "x")) == "{}" and fake.calls == 3


def test_daily_quota_is_not_retried(monkeypatch):
    import asyncio, openai
    fake = _fake_client([_rate_limit("RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")])
    monkeypatch.setattr(server, "_llm_client", lambda: (fake(), "m"))
    monkeypatch.setattr(server, "RATE_LIMIT_WAITS", (0, 0, 0))
    with pytest.raises(openai.RateLimitError):
        asyncio.run(server._call_llm("S", "x"))
    assert fake.calls == 1
