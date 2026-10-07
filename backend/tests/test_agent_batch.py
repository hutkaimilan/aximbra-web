"""A futás leveleit csomagban osztályozzuk: a Gemini ingyenes kerete ötven
egyes hívásra 429-cel felelt, és a lap nem jutott a futás végére."""
import asyncio
import json
import re

import server


def _email(n):
    return {"sender": f"s{n}@example.com", "subject": f"tárgy {n}", "body": f"törzs {n}"}


def _fake_llm(calls, drop=()):
    async def fake(system_msg, user_text, max_tokens=600):
        ids = [int(i) for i in re.findall(r"### EMAIL id=(\d+)", user_text)]
        calls.append({"batch": "BATCH MODE" in system_msg, "ids": ids, "text": user_text})
        if not ids:  # egyes hívás
            subj = re.search(r"Tárgy: (.*)", user_text).group(1)
            return json.dumps({"category": "other", "urgency": 2, "needs_reply": "nem",
                               "summary": subj})
        bodies = re.findall(r"Tárgy: (.*)", user_text)
        return json.dumps({"results": [
            {"id": i, "category": "invoice", "urgency": 3, "needs_reply": "igen", "summary": b}
            for i, b in zip(ids, bodies) if i not in drop
        ]})
    return fake


async def _run(group, emails, lang="hu"):
    server._batch_group.set(group)
    return await asyncio.gather(*(server.classify_one(e, lang) for e in emails))


def test_a_run_of_25_emails_costs_three_model_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_call_llm", _fake_llm(calls))
    monkeypatch.setitem(server._state, "cost", 0.0)
    monkeypatch.setattr(server, "AGENT_BATCH_WINDOW", 0.05)
    out = asyncio.run(_run("sess-a", [_email(n) for n in range(25)]))
    assert sorted(len(c["ids"]) for c in calls) == [5, 10, 10]
    assert all(c["batch"] for c in calls)
    # Minden eredmény a saját levelénél köt ki.
    assert [o["summary"] for o in out] == [f"tárgy {n}" for n in range(25)]
    assert all(o["category"] == "invoice" for o in out)


def test_an_email_the_model_skipped_is_asked_again_alone(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_call_llm", _fake_llm(calls, drop={2}))
    monkeypatch.setitem(server._state, "cost", 0.0)
    monkeypatch.setattr(server, "AGENT_BATCH_WINDOW", 0.05)
    out = asyncio.run(_run("sess-b", [_email(n) for n in range(3)]))
    assert out[1]["summary"] == "tárgy 1" and out[1]["category"] == "other"
    assert out[0]["category"] == out[2]["category"] == "invoice"
    assert sum(1 for c in calls if not c["batch"]) == 1


def test_two_visitors_never_share_a_prompt(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_call_llm", _fake_llm(calls))
    monkeypatch.setitem(server._state, "cost", 0.0)
    monkeypatch.setattr(server, "AGENT_BATCH_WINDOW", 0.05)

    async def both():
        a = asyncio.create_task(_run("visitor-1", [_email(n) for n in range(3)]))
        b = asyncio.create_task(_run("visitor-2", [_email(n + 100) for n in range(3)]))
        return await a, await b

    asyncio.run(both())
    for c in calls:
        subjects = re.findall(r"Tárgy: tárgy (\d+)", c["text"])
        assert all(int(s) < 100 for s in subjects) or all(int(s) >= 100 for s in subjects)


def test_a_failed_batch_fails_each_of_its_emails(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("429")
    monkeypatch.setattr(server, "_call_llm", boom)
    monkeypatch.setitem(server._state, "cost", 0.0)
    monkeypatch.setattr(server, "AGENT_BATCH_WINDOW", 0.05)

    async def go():
        server._batch_group.set("sess-c")
        return await asyncio.gather(*(server.classify_one(_email(n)) for n in range(4)),
                                    return_exceptions=True)
    out = asyncio.run(go())
    assert all(isinstance(o, RuntimeError) for o in out)
    assert not server._batches


def test_without_a_run_group_it_stays_a_single_call(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_call_llm", _fake_llm(calls))
    monkeypatch.setitem(server._state, "cost", 0.0)
    asyncio.run(server.classify_one(_email(1)))
    assert len(calls) == 1 and not calls[0]["batch"]
