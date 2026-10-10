import httpx
import openai
import pytest
from fastapi.testclient import TestClient

import db
import main
from llm import client

OK = '{"category": "bug", "priority": "high", "confidence": 0.9, "reason": "It crashes."}'
REQ = httpx.Request("POST", "http://x/chat/completions")


def status_error(cls, code, headers=None):
    return cls("boom", response=httpx.Response(code, request=REQ, headers=headers or {}), body=None)


class Usage:
    prompt_tokens, completion_tokens = 120, 30


class Resp:
    usage = Usage()

    class _C:
        class message:
            content = OK
    choices = [_C()]


class FakeOpenAI:
    """Raises the scripted exceptions in order, then answers."""
    def __init__(self, errors):
        self.errors, self.calls = list(errors), 0
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return Resp()


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(client, "CALL_LOG", tmp_path / "calls.jsonl")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.delenv("LLM_STUB", raising=False)
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    sleeps = []
    monkeypatch.setattr(client, "sleep", sleeps.append)

    def use(*errors):
        fake = FakeOpenAI(errors)
        monkeypatch.setattr(client, "_client", lambda: fake)
        return fake
    with TestClient(main.app) as c:
        yield c, use, sleeps, tmp_path


def post(c):
    return c.post("/tasks/triage", json={"text": "app crashes"})


@pytest.mark.parametrize("code,cls", [(400, openai.BadRequestError), (401, openai.AuthenticationError),
                                      (403, openai.PermissionDeniedError)])
def test_never_retry_400_401_403(rig, code, cls):
    c, use, sleeps, _ = rig
    fake = use(status_error(cls, code))
    r = post(c)
    assert r.status_code == 502 and fake.calls == 1 and sleeps == []


def test_5xx_retried_with_backoff_and_jitter_then_succeeds(rig):
    c, use, sleeps, _ = rig
    fake = use(status_error(openai.InternalServerError, 500), status_error(openai.InternalServerError, 503))
    assert post(c).status_code == 200 and fake.calls == 3
    assert 1 <= sleeps[0] <= 1.5 and 2 <= sleeps[1] <= 2.5


def test_429_obeys_retry_after(rig):
    c, use, sleeps, _ = rig
    fake = use(status_error(openai.RateLimitError, 429, {"retry-after": "7"}))
    assert post(c).status_code == 200 and sleeps == [7.0] and fake.calls == 2


def test_timeouts_exhaust_into_504(rig):
    c, use, sleeps, _ = rig
    fake = use(*[openai.APITimeoutError(request=REQ)] * 4)
    r = post(c)
    assert r.status_code == 504 and fake.calls == 4 and len(sleeps) == 3


def test_every_call_logs_tokens_duration_version_model_repair(rig):
    c, use, sleeps, tmp = rig
    use()
    post(c)
    import json
    line = json.loads((tmp / "calls.jsonl").read_text().splitlines()[0])
    assert line["input_tokens"] == 120 and line["output_tokens"] == 30
    assert line["model"] == "test-model" and line["prompt_version"] == "triage-v1"
    assert line["repair"] is False and "duration_ms" in line


def test_kill_switch_makes_no_model_call(rig, monkeypatch):
    c, use, sleeps, _ = rig
    fake = use()
    monkeypatch.setenv("LLM_ENABLED", "false")
    r = post(c)
    assert r.status_code == 200 and r.json()["category"] == "other" and r.json()["confidence"] == 0.0
    assert fake.calls == 0


def test_sdk_defaults_are_not_left_in_place():
    assert client.TIMEOUT <= 60
    c = client.openai.OpenAI(base_url="http://x", api_key="k", timeout=client.TIMEOUT, max_retries=0)
    assert c.max_retries == 0 and c.timeout == client.TIMEOUT
