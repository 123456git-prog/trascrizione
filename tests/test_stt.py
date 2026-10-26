from app.models import Segment, Transcript, Word
from app.stt.base import assign_speakers, split_sentences
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
            w = types.SimpleNamespace
            segs = [types.SimpleNamespace(start=0.0, end=2.0, text=" Ciao "),
                    types.SimpleNamespace(start=2.0, end=3.0, text="  "),
                    types.SimpleNamespace(start=3.0, end=6.0, text="a tutti"),
                    types.SimpleNamespace(start=6.0, end=9.0, text=" Sì. Va bene?", words=[
                        w(start=6.0, end=6.5, word=" Sì."), w(start=7.0, end=8.0, word=" Va"),
                        w(start=8.0, end=9.0, word=" bene?")])]
            return iter(segs), types.SimpleNamespace(duration=9.0)

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    progress = []
    engine = FasterWhisperEngine("large-v3-turbo", "it", vocabulary="Anthropic, GDPR")
    t = engine.transcribe(tmp_path / "x.wav", 9.0, lambda f, m: progress.append(f))
    assert [(s.id, s.text, s.start) for s in t.segments] == [
        (0, "Ciao", 0.0), (1, "a tutti", 3.0), (2, "Sì.", 6.0), (3, "Va bene?", 7.0)]
    assert calls["transcribe"]["word_timestamps"] is True
    assert calls["init"] == ("large-v3-turbo", {"device": "cpu", "compute_type": "int8", "cpu_threads": 0})
    assert calls["transcribe"]["language"] == "it" and calls["transcribe"]["vad_filter"] is True
    prompt = calls["transcribe"]["hotwords"]
    assert prompt.endswith("Termini: Anthropic, GDPR.") and "?" in prompt
    assert progress[-1] == 1.0


def test_get_diarizer_choice(tmp_path):
    from app.config import Settings
    from app.stt import get_diarizer
    from app.stt.sherpa_diarization import SherpaDiarizer

    settings = Settings(data_dir=tmp_path)
    assert get_diarizer(settings, speakers=1) is None  # una sola persona: niente da distinguere
    d = get_diarizer(settings, speakers=3)
    assert isinstance(d, SherpaDiarizer) and d.num_speakers == 3
    assert get_diarizer(settings).num_speakers is None
    assert get_diarizer(Settings(data_dir=tmp_path, diarization=False)) is None


def _words(*items):
    return [Word(start=a, end=b, text=t) for a, b, t in items]


def test_split_sentences():
    words = _words((0, 1, " Ciao."), (1, 2, " Come"), (2, 3, " stai?"), (3, 4, " Bene"))
    assert [[w.text for w in s] for s in split_sentences(words)] == [[" Ciao."], [" Come", " stai?"], [" Bene"]]
    long = _words(*[(i, i + 1, " parola") for i in range(70)])
    assert [len(s) for s in split_sentences(long)] == [30, 30, 10]


def test_assign_speakers_splits_segment_at_voice_change():
    words = _words((0, 1, " Allora"), (1, 2, " iniziamo"), (2, 2.2, " eh"), (2.2, 3, " va"),
                   (3, 4, " bene"), (4.2, 5, " sì"), (5, 6, " certo."))
    t = Transcript(segments=[Segment(id=0, start=0, end=6, text="x", words=words)])
    # "eh" brevissimo attribuito a un terzo: è rumore e resta con chi parlava
    turns = [(0, 2.0, "A"), (2.0, 2.2, "C"), (2.2, 4.1, "A"), (4.1, 6, "B")]
    assign_speakers(t, turns)
    assert [(s.id, s.speaker, s.text, s.start, s.end) for s in t.segments] == [
        (0, "SPEAKER_00", "Allora iniziamo eh va bene", 0, 4),
        (1, "SPEAKER_01", "sì certo.", 4.2, 6),
    ]
    assert "words" not in t.model_dump()["segments"][0]
