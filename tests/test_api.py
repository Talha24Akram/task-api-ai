import pytest
from fastapi.testclient import TestClient

import db
import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    with TestClient(main.app) as c:  # runs lifespan -> init_db on the temp file
        yield c


def test_seed_only_once(client):
    assert len(client.get("/tasks").json()) == 3
    db.init_db()
    db.init_db()
    assert len(client.get("/tasks").json()) == 3


def test_read_and_404(client):
    assert client.get("/tasks/1").json() == {"id": 1, "title": "Buy milk", "done": False}
    r = client.get("/tasks/99")
    assert r.status_code == 404 and r.json() == {"error": "Task 99 not found"}


def test_create_validation_and_persistence(client):
    assert client.post("/tasks", json={}).status_code == 400
    assert client.post("/tasks", json={"title": "   "}).status_code == 400
    r = client.post("/tasks", json={"title": "Buy eggs"})
    assert r.status_code == 201 and r.json()["done"] is False
    assert client.get(f"/tasks/{r.json()['id']}").json()["title"] == "Buy eggs"


def test_update_delete(client):
    assert client.put("/tasks/1", json={"done": True}).json()["done"] is True
    assert client.put("/tasks/1", json={}).status_code == 400
    assert client.put("/tasks/99", json={"done": True}).status_code == 404
    assert client.delete("/tasks/1").status_code == 204
    assert client.delete("/tasks/1").status_code == 404
    assert client.get("/tasks/1").status_code == 404


def test_filters_and_stats(client):
    assert [t["title"] for t in client.get("/tasks?done=true").json()] == ["Write README"]
    assert [t["title"] for t in client.get("/tasks?search=MILK").json()] == ["Buy milk"]
    assert client.get("/stats").json() == {"total": 3, "done": 1, "open": 2}
