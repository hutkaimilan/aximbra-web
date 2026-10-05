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
    assert model.startswith("gemini") and client.max_retries > 0


def test_gemini_without_key_is_a_clean_503(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(HTTPException) as e:
        server._llm_client()
    assert e.value.status_code == 503


def test_gemini_quota_pauses_the_demo():
    assert server._quota_exhausted(Exception("429 RESOURCE_EXHAUSTED: quota"))
