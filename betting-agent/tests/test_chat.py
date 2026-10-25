"""Csevegés: a Gemini-kérés felépítése, a bemenet ellenőrzése és a hibák magyar üzenetei."""
import base64
import io
import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chat  # noqa: E402

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 50).decode()


def test_request_puts_context_on_last_user_message_and_maps_roles():
    req = chat.build_request([{"role": "user", "text": "szia"}, {"role": "assistant", "text": "helló"},
                              {"role": "user", "text": "mi a véleményed?", "images": [PNG]}], "SZELVÉNY: ...")
    roles = [c["role"] for c in req["contents"]]
    assert roles == ["user", "model", "user"]
    last = req["contents"][-1]["parts"]
    assert last[0]["text"].startswith("ADATOK") and "SZELVÉNY" in last[0]["text"]
    assert last[1]["inline_data"]["mime_type"] == "image/png"
    assert last[2]["text"] == "mi a véleményed?"
    assert "ADATOK" not in json.dumps(req["contents"][0])
    assert "Csak az ADATOK" in req["system_instruction"]["parts"][0]["text"]


@pytest.mark.parametrize("messages", [[], None, [{"role": "system", "text": "x"}], [{"role": "assistant", "text": "x"}]])
def test_bad_conversations_rejected(messages):
    with pytest.raises(chat.ChatError) as e:
        chat.build_request(messages, "")
    assert e.value.status == 400


@pytest.mark.parametrize("url", ["data:image/gif;base64,AAAA", "http://x/y.png", "data:image/png;base64,@@@"])
def test_bad_images_rejected(url):
    with pytest.raises(chat.ChatError):
        chat.build_request([{"role": "user", "text": "x", "images": [url]}], "")


def test_too_many_images_rejected():
    msgs = [{"role": "user", "text": "x", "images": [PNG] * 4}, {"role": "assistant", "text": "y"},
            {"role": "user", "text": "z", "images": [PNG] * 3}]
    with pytest.raises(chat.ChatError):
        chat.build_request(msgs, "")


def test_text_and_context_are_capped():
    req = chat.build_request([{"role": "user", "text": "a" * 10000}], "b" * 100000)
    parts = req["contents"][0]["parts"]
    assert len(parts[1]["text"]) == chat.MAX_TEXT
    assert len(parts[0]["text"]) < chat.MAX_CONTEXT + 100


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ask_returns_text_and_sends_key_in_header(monkeypatch):
    seen = {}

    def fake(req, timeout):
        seen["url"], seen["key"] = req.full_url, req.get_header("X-goog-api-key")
        return _Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": "Erős szelvény."}]}}]}).encode())

    monkeypatch.setenv("GEMINI_API_KEY", "titok")
    monkeypatch.setenv("GEMINI_MODEL", "")
    monkeypatch.setattr(chat.urllib.request, "urlopen", fake)
    monkeypatch.setattr(chat, "DAILY", chat.DailyLimit(5))
    assert chat.ask([{"role": "user", "text": "?"}], "") == "Erős szelvény."
    assert seen["key"] == "titok" and "titok" not in seen["url"] and chat.DEFAULT_MODEL in seen["url"]


def test_ask_errors_are_friendly(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "titok")
    monkeypatch.setattr(chat, "DAILY", chat.DailyLimit(5))

    def rate(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "x", {}, io.BytesIO(b"{}"))
    monkeypatch.setattr(chat.urllib.request, "urlopen", rate)
    with pytest.raises(chat.ChatError) as e:
        chat.ask([{"role": "user", "text": "?"}], "")
    assert e.value.status == 429 and "Gemini" in str(e.value)


def test_missing_key_and_daily_limit(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(chat.ChatError) as e:
        chat.ask([{"role": "user", "text": "?"}], "")
    assert e.value.status == 503
    lim = chat.DailyLimit(2)
    assert lim.take() and lim.take() and not lim.take()
