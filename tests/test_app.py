# The web API, driven through FastAPI's test client (offline backend).

import pytest
from fastapi.testclient import TestClient

import app as web
import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    # uploads go to a temp folder so tests never touch data/uploads
    monkeypatch.setattr(config, "UPLOADS_DIR", str(tmp_path))
    return TestClient(web.app)


def test_status_lists_sample_documents(client):
    data = client.get("/api/status").json()
    assert data["backend"] == "offline"
    names = [d["source"] for d in data["documents"]]
    assert "leave-policy.md" in names
    assert not any(d["removable"] for d in data["documents"])


def test_ask_returns_answer_and_keeps_history_per_session(client):
    first = client.post("/api/ask", json={"question": "What is the hotel limit per night?",
                                          "session_id": "s1"}).json()
    assert first["citations"]
    client.post("/api/ask", json={"question": "And international?", "session_id": "s1"})
    assert len(web.sessions["s1"]) == 2
    client.post("/api/reset", json={"session_id": "s1"})
    assert "s1" not in web.sessions


def test_empty_question_is_a_400(client):
    assert client.post("/api/ask", json={"question": " "}).status_code == 400


def test_upload_then_ask_then_remove(client):
    body = b"# Cafeteria\nThe cafeteria serves lunch from 12:00 to 14:30 every weekday."
    res = client.post("/api/upload", files={"file": ("cafeteria.md", body, "text/markdown")})
    assert res.status_code == 200
    assert "cafeteria.md" in [d["source"] for d in res.json()["documents"]]

    answer = client.post("/api/ask", json={"question": "When does the cafeteria serve lunch?"}).json()
    assert "12:00" in answer["answer"]
    assert answer["citations"][0]["source"] == "cafeteria.md"

    res = client.delete("/api/documents/cafeteria.md")
    assert "cafeteria.md" not in [d["source"] for d in res.json()["documents"]]


def test_upload_rejects_other_file_types(client):
    res = client.post("/api/upload", files={"file": ("run.exe", b"MZ", "application/octet-stream")})
    assert res.status_code == 400


def test_sample_documents_cannot_be_deleted(client):
    assert client.delete("/api/documents/leave-policy.md").status_code == 404


def test_uploads_can_be_switched_off_for_a_public_deployment(client, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_UPLOADS", False)
    assert client.get("/api/status").json()["uploads_enabled"] is False
    res = client.post("/api/upload", files={"file": ("x.md", b"hello", "text/markdown")})
    assert res.status_code == 403
    assert client.delete("/api/documents/x.md").status_code == 403
