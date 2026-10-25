"""Flusso completo con ffmpeg reale e un motore di trascrizione finto (i modelli veri sono troppo grandi per i test)."""

import shutil
import subprocess

import pytest

from app import cli
from app.config import Settings
from app.errors import AudioError
from app.models import Segment, Transcript
from app.service import Service

from .conftest import FakeLLM

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg non installato")


class FakeEngine:
    name = "fake"

    def __init__(self):
        self.runs = 0

    def transcribe(self, wav_path, duration, progress):
        self.runs += 1
        assert wav_path.suffix == ".wav" and wav_path.stat().st_size > 1000
        progress(1.0, "ok")
        return Transcript(duration=duration, engine="fake", segments=[
            Segment(id=0, start=0.0, end=1.0, text="Buongiorno, iniziamo la riunione."),
            Segment(id=1, start=1.0, end=2.5, text="Il budget approvato è di 40.000 euro."),
        ])


@pytest.fixture
def audio_file(tmp_path):
    path = tmp_path / "riunione prova.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-c:a", "aac", str(path)], check=True)
    return path


@pytest.fixture
def service(tmp_path, monkeypatch):
    engine = FakeEngine()
    monkeypatch.setattr("app.service.get_engine", lambda settings: engine)
    settings = Settings(data_dir=tmp_path / "data", diarization=False)
    svc = Service(settings, llm=FakeLLM())
    svc.engine = engine
    return svc


@needs_ffmpeg
def test_process_end_to_end(service, audio_file):
    rec_id = service.process(audio_file, template_id="lezione")
    meta = service.store.meta(rec_id)
    assert meta.status == "pronta" and 2.5 < meta.duration < 3.5
    assert meta.title == "Riunione budget"  # titolo generato al posto del nome file
    assert (service.store.dir(rec_id) / "audio.m4a").exists()
    analysis = service.store.analysis(rec_id)
    assert set(analysis) >= {"chunks", "summaries", "keywords", "extraction", "mindmaps", "provider"}

    # si trascrive una sola volta
    service.transcribe(rec_id)
    assert service.engine.runs == 1


def test_rejects_bad_files(service, tmp_path):
    with pytest.raises(AudioError, match="non trovato"):
        service.import_audio(tmp_path / "manca.mp3")
    doc = tmp_path / "note.txt"
    doc.write_text("x")
    with pytest.raises(AudioError, match="non supportato"):
        service.import_audio(doc)
    fake = tmp_path / "rotto.mp3"
    fake.write_bytes(b"non sono un mp3")
    if shutil.which("ffprobe"):
        with pytest.raises(AudioError, match="audio valido"):
            service.import_audio(fake)


@needs_ffmpeg
def test_cli_commands(service, audio_file, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Service", lambda settings: service)
    assert cli.main(["process", str(audio_file)]) == 0
    out = capsys.readouterr().out
    assert "consenso" in out and "## Riassunto (Riunione)" in out and "Decisioni" in out
    rec_id = service.store.list()[0].id

    assert cli.main(["list"]) == 0
    assert "pronta" in capsys.readouterr().out

    assert cli.main(["ask", rec_id[:10], "Qual è il budget?"]) == 0
    assert "Fonti:" in capsys.readouterr().out

    assert cli.main(["show", rec_id, "transcript"]) == 0
    assert "[00:00:01] Il budget" in capsys.readouterr().out

    assert cli.main(["speakers", rec_id, "SPEAKER_00=Marco"]) == 0
    assert service.store.transcript(rec_id).speaker_names == {"SPEAKER_00": "Marco"}

    out_file = tmp_path / "export.md"
    assert cli.main(["export", rec_id, "-o", str(out_file)]) == 0
    md = out_file.read_text(encoding="utf-8")
    assert md.startswith("# Riunione budget") and "## Trascrizione" in md and "_(00:00:00)_" in md

    assert cli.main(["delete", rec_id, "-y"]) == 0
    assert service.store.list() == []

    assert cli.main(["show", "inesistente"]) == 1
    assert "Errore:" in capsys.readouterr().err
