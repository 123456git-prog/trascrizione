"""API web con motore di trascrizione e LLM finti; ffmpeg vero."""

import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.server import create_app
from app.service import Service

from .conftest import FakeLLM
from .test_service_cli import FakeEngine

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg non installato")


@pytest.fixture
def audio_bytes(tmp_path):
    path = tmp_path / "a.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:a", "aac", str(path)], check=True)
    return path.read_bytes()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("app.service.get_engine", lambda settings: FakeEngine())
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    settings = Settings(data_dir=tmp_path / "data", diarization=False)
    app = create_app(settings, Service(settings, llm=FakeLLM()))
    with TestClient(app) as c:
        yield c


def wait_done(client, rec_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        meta = client.get(f"/api/recordings/{rec_id}/status").json()
        if meta["status"] in ("pronta", "trascritta", "errore") and not meta["job"]:
            return meta
        time.sleep(0.05)
    raise AssertionError(f"elaborazione non terminata: {meta}")


def test_upload_process_and_read(client, audio_bytes):
    r = client.post("/api/recordings", files={"file": ("Riunione lunedì.m4a", audio_bytes, "audio/mp4")},
                    data={"template": "riunione", "provider": "ollama"})
    assert r.status_code == 201, r.text
    rec_id = r.json()["id"]
    assert r.json()["status"] == "in coda"
    meta = wait_done(client, rec_id)
    assert meta["status"] == "pronta" and meta["title"] == "Riunione budget"

    data = client.get(f"/api/recordings/{rec_id}").json()
    assert data["transcript"]["segments"][1]["text"].startswith("Il budget")
    assert data["analysis"]["provider"] == "ollama"
    assert data["analysis"]["extraction"]["action_items"][0]["timestamp"] == "00:00:00"

    # audio con supporto Range (per saltare nel player)
    r = client.get(f"/api/recordings/{rec_id}/audio", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100

    # ricerca a testo libero, senza accenti e per prefisso
    hits = client.get("/api/recordings", params={"q": "approvato BUDG"}).json()
    assert [h["id"] for h in hits] == [rec_id] and "[" in hits[0]["snippet"]
    assert client.get("/api/recordings", params={"q": "inesistente"}).json() == []

    # chat
    r = client.post(f"/api/recordings/{rec_id}/ask", json={"question": "Qual è il budget?"})
    assert r.json()["citations"][0]["timestamp"] == "00:00:00"

    # export
    r = client.get(f"/api/recordings/{rec_id}/export")
    assert r.status_code == 200 and r.text.startswith("# Riunione budget")
    assert "filename*=UTF-8''Riunione%20budget.md" in r.headers["content-disposition"]


def test_edit_transcript_and_speakers(client, audio_bytes):
    rec_id = client.post("/api/recordings", files={"file": ("x.m4a", audio_bytes)}).json()["id"]
    wait_done(client, rec_id)
    r = client.patch(f"/api/recordings/{rec_id}/segments/1", json={"text": "Il budget approvato è di 45.000 euro."})
    assert r.status_code == 200
    data = client.get(f"/api/recordings/{rec_id}").json()
    assert data["transcript"]["segments"][1]["text"].endswith("45.000 euro.")
    assert data["analysis"]["stale"] is True
    assert client.get("/api/recordings", params={"q": "45.000"}).json()[0]["id"] == rec_id

    client.patch(f"/api/recordings/{rec_id}", json={"title": "Nuovo titolo", "speaker_names": {"SPEAKER_00": "Anna"}})
    data = client.get(f"/api/recordings/{rec_id}").json()
    assert data["meta"]["title"] == "Nuovo titolo"
    assert data["transcript"]["speaker_names"] == {"SPEAKER_00": "Anna"}

    # nuovo riassunto con un altro template, in background
    assert client.post(f"/api/recordings/{rec_id}/summary", json={"template": "lezione"}).status_code == 202
    wait_done(client, rec_id)
    assert "lezione" in client.get(f"/api/recordings/{rec_id}").json()["analysis"]["summaries"]

    assert client.delete(f"/api/recordings/{rec_id}").status_code == 204
    assert client.get(f"/api/recordings/{rec_id}").status_code == 404
    assert client.get("/api/recordings").json() == []


def test_errors_and_templates(client, audio_bytes):
    r = client.post("/api/recordings", files={"file": ("note.txt", b"ciao")})
    assert r.status_code == 400 and "non supportato" in r.json()["detail"]
    r = client.post("/api/recordings", files={"file": ("a.m4a", audio_bytes)}, data={"template": "boh"})
    assert r.status_code == 404

    r = client.post("/api/templates", json={"description": "assemblea di condominio con spese"})
    assert r.status_code == 201 and r.json()["id"] == "condominio"
    assert any(t["id"] == "condominio" for t in client.get("/api/templates").json())
    assert client.delete("/api/templates/riunione").status_code == 400
    assert client.delete("/api/templates/condominio").status_code == 204

    providers = {p["id"]: p for p in client.get("/api/providers").json()}
    assert providers["ollama"]["sensitive_ok"] and not providers["gemini"]["sensitive_ok"]


def test_password_protection(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "segreta")
    settings = Settings(data_dir=tmp_path / "data")
    with TestClient(create_app(settings, Service(settings, llm=FakeLLM()), start_worker=False)) as c:
        assert c.get("/api/recordings").status_code == 401
        assert c.get("/api/session").json() == {"authenticated": False, "password_required": True}
        assert c.post("/api/login", json={"password": "no"}).status_code == 401
        assert c.post("/api/login", json={"password": "segreta"}).status_code == 200
        assert c.get("/api/recordings").status_code == 200


def test_jobs_resume_after_restart(tmp_path, monkeypatch, audio_bytes):
    from app.jobs import JobQueue

    monkeypatch.setattr("app.service.get_engine", lambda settings: FakeEngine())
    settings = Settings(data_dir=tmp_path / "data")
    service = Service(settings, llm=FakeLLM())
    src = tmp_path / "r.m4a"
    src.write_bytes(audio_bytes)
    rec_id = service.import_audio(src)
    # simula un server spento durante la trascrizione
    service.store.update_meta(rec_id, status="trascrizione", job={"kind": "process", "template": "riunione"})
    jobs = JobQueue(service)
    jobs.start()
    deadline = time.time() + 10
    while service.store.meta(rec_id).status != "pronta" and time.time() < deadline:
        time.sleep(0.05)
    jobs.stop()
    meta = service.store.meta(rec_id)
    assert meta.status == "pronta" and meta.job is None
