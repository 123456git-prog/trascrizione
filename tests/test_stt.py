from app.models import Segment, Transcript
from app.stt.base import assign_speakers
from app.stt.whisper_cpp_engine import parse_whisper_cpp_json


def test_parse_whisper_cpp_json():
    data = {"transcription": [
        {"offsets": {"from": 0, "to": 2500}, "text": " Buongiorno a tutti."},
        {"offsets": {"from": 2500, "to": 3000}, "text": "  "},
        {"offsets": {"from": 3000, "to": 7120}, "text": " Iniziamo."},
    ]}
    segs = parse_whisper_cpp_json(data)
    assert [(s.id, s.start, s.end, s.text) for s in segs] == [
        (0, 0.0, 2.5, "Buongiorno a tutti."), (1, 3.0, 7.12, "Iniziamo.")]


def test_assign_speakers_by_overlap_and_renumber():
    t = Transcript(segments=[
        Segment(id=0, start=0, end=4, text="a"),
        Segment(id=1, start=4, end=9, text="b"),
        Segment(id=2, start=20, end=22, text="c"),  # nessuna sovrapposizione: turno più vicino
    ])
    turns = [(0, 4.5, "SPEAKER_05"), (4.5, 10, "SPEAKER_02"), (23, 30, "SPEAKER_05")]
    assign_speakers(t, turns)
    assert [s.speaker for s in t.segments] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]
    assert t.speaker_label("SPEAKER_01") == "Interlocutore 2"
    t.speaker_names["SPEAKER_01"] = "Marco"
    assert t.render_line(t.segments[1]) == "[#1 00:00:04] Marco: b"


def test_faster_whisper_engine_with_fake_model(monkeypatch, tmp_path):
    import types

    import faster_whisper

    from app.stt.faster_whisper_engine import FasterWhisperEngine

    calls = {}

    class FakeModel:
        def __init__(self, name, **kwargs):
            calls["init"] = (name, kwargs)

        def transcribe(self, path, **kwargs):
            calls["transcribe"] = kwargs
            segs = [types.SimpleNamespace(start=0.0, end=2.0, text=" Ciao "),
                    types.SimpleNamespace(start=2.0, end=3.0, text="  "),
                    types.SimpleNamespace(start=3.0, end=6.0, text="a tutti")]
            return iter(segs), types.SimpleNamespace(duration=6.0)

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    progress = []
    engine = FasterWhisperEngine("large-v3-turbo", "it", vocabulary="Anthropic, GDPR")
    t = engine.transcribe(tmp_path / "x.wav", 6.0, lambda f, m: progress.append(f))
    assert [(s.id, s.text) for s in t.segments] == [(0, "Ciao"), (1, "a tutti")]
    assert calls["init"] == ("large-v3-turbo", {"device": "cpu", "compute_type": "int8", "cpu_threads": 0})
    assert calls["transcribe"]["language"] == "it" and calls["transcribe"]["vad_filter"] is True
    assert calls["transcribe"]["initial_prompt"] == "Anthropic, GDPR"
    assert progress[-1] == 1.0
