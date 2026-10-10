import pytest
from fastapi.testclient import TestClient

import db
import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("LLM_STUB", "1")
    with TestClient(main.app) as c:
        yield c


def test_stub_returns_schema_shaped_200(client):
    r = client.post("/tasks/triage", json={"text": "Login page crashes on submit"})
    assert r.status_code == 200
    assert set(r.json()) == {"category", "priority", "confidence", "reason"}


@pytest.mark.parametrize("body,field", [
    ({}, "text"),
    ({"text": 5}, "text"),
    ({"text": ""}, "text"),
    ({"text": "   "}, "text"),
    ({"text": "x" * 501}, "text"),
])
def test_bad_input_is_400_naming_the_field(client, body, field):
    r = client.post("/tasks/triage", json=body)
    assert r.status_code == 400
    assert r.json()["error"].startswith(field + ":")
