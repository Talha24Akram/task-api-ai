import json

import pytest
from fastapi.testclient import TestClient

import db
import main
from llm import client, triage as triage_mod
from llm.client import Completion

GOOD = '{"category": "bug", "priority": "high", "confidence": 0.9, "reason": "It crashes."}'


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.delenv("LLM_STUB", raising=False)
    monkeypatch.setattr(triage_mod, "QUARANTINE", tmp_path / "logs" / "quarantine.jsonl")
    calls = []

    def script(*answers):
        it = iter(answers)

        def fake(messages, **kw):
            calls.append(messages)
            return Completion(text=next(it))
        monkeypatch.setattr(client, "complete", fake)
    with TestClient(main.app) as c:
        yield c, script, calls, tmp_path


def post(c):
    return c.post("/tasks/triage", json={"text": "app crashes"})


def test_happy_path(api):
    c, script, calls, _ = api
    script(GOOD)
    r = post(c)
    assert r.status_code == 200 and r.json()["category"] == "bug" and len(calls) == 1


def test_code_fence_and_chatty_preamble_are_stripped(api):
    c, script, calls, _ = api
    script("Sure! Here's the JSON:\n```json\n" + GOOD + "\n```")
    assert post(c).status_code == 200 and len(calls) == 1


def test_one_repair_then_success(api):
    c, script, calls, _ = api
    script(GOOD.replace("bug", "urgent"), GOOD)
    r = post(c)
    assert r.status_code == 200 and len(calls) == 2
    repair_msg = calls[1][-1]["content"]
    assert "category" in repair_msg and "Return only corrected JSON" in repair_msg
    assert calls[1][-2] == {"role": "assistant", "content": GOOD.replace("bug", "urgent")}


def test_two_failures_give_422_quarantine_and_never_raw_text(api):
    c, script, calls, tmp = api
    bad = GOOD.replace("bug", "urgent")
    script(bad, "I cannot help with that")
    r = post(c)
    assert r.status_code == 422 and len(calls) == 2  # exactly one repair, no more
    assert "urgent" not in r.text and "cannot help" not in r.text  # raw model text is never returned
    line = json.loads((tmp / "logs" / "quarantine.jsonl").read_text().splitlines()[0])
    assert line["input"] == "app crashes" and line["prompt_version"] == "triage-v1" and line["raw_outputs"][0] == bad


def test_extra_fields_are_rejected(api):
    c, script, calls, _ = api
    script(GOOD[:-1] + ', "advice": "take aspirin"}', GOOD[:-1] + ', "x": 1}')
    assert post(c).status_code == 422


def test_user_text_stays_out_of_the_system_prompt(api):
    c, script, calls, _ = api
    script(GOOD)
    c.post("/tasks/triage", json={"text": "zebra-unique-42"})
    system, user = calls[0]
    assert "zebra-unique-42" not in system["content"] and json.loads(user["content"]) == {"text": "zebra-unique-42"}
