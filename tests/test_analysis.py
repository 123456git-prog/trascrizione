import pytest

from app import models as m
from app.analysis.chunking import chunk_segments
from app.analysis.pipeline import Analyzer, create_template
from app.analysis.templates import TemplateStore
from app.errors import AnalysisError, NotFoundError

from .conftest import FakeLLM


def test_chunks_cover_everything_within_limit(transcript):
    chunks = chunk_segments(transcript, 600)
    assert len(chunks) > 1
    assert [s.id for c in chunks for s in c] == [s.id for s in transcript.segments]
    for c in chunks:
        assert len(transcript.render(c)) <= 600


def test_full_analysis_resolves_timestamps(transcript, fake_llm, tmp_path):
    store = TemplateStore(tmp_path / "t.json")
    a = Analyzer(fake_llm, transcript, chunk_chars=600, workers=2)
    a.run_all(store.get("riunione"))
    n = len(a.chunks)

    # map: un blocco = una chiamata per gli appunti e una per l'estrazione; poi 3 chiamate globali
    schemas = [c[2] for c in fake_llm.calls]
    assert schemas.count(m.ChunkNotes) == n and schemas.count(m.ExtractionOut) == n
    assert schemas.count(m.SummaryOut) == schemas.count(m.KeywordsOut) == schemas.count(m.MindMapOut) == 1

    first_kp = a.cache["chunks"][1]["key_points"]
    start_id = a.chunks[1][0].id
    assert first_kp[0]["segment_id"] == start_id
    assert first_kp[0]["timestamp"] == m.format_ts(transcript.segments[start_id].start)
    assert first_kp[1]["segment_id"] is None  # id inventato: scartato

    ex = a.cache["extraction"]
    assert len(ex["decisions"]) == n
    assert ex["action_items"][0]["owner"] == "Marco"
    assert ex["action_items"][0]["speaker"] == "Interlocutore 1"
    assert len(ex["people"]) == 1  # deduplicato tra blocchi
    topics = a.cache["keywords"]["topics"][0]["refs"]
    assert [r["start"] for r in topics] == sorted(r["start"] for r in topics)
    assert a.cache["summaries"]["riunione"]["title"] == "Riunione budget"


def test_cache_avoids_repeated_calls(transcript, fake_llm, tmp_path):
    store = TemplateStore(tmp_path / "t.json")
    a = Analyzer(fake_llm, transcript, chunk_chars=600)
    a.run_all(store.get("riunione"))
    calls = len(fake_llm.calls)
    b = Analyzer(fake_llm, transcript, cache=a.cache, chunk_chars=600)
    b.run_all(store.get("riunione"))
    assert len(fake_llm.calls) == calls
    b.summary(store.get("lezione"))  # nuovo template: riusa gli appunti, una sola chiamata
    assert len(fake_llm.calls) == calls + 1


def test_resume_after_failure(transcript, tmp_path):
    store = TemplateStore(tmp_path / "t.json")
    saved = {}
    failing = FakeLLM(fail_on=m.ExtractionOut)
    a = Analyzer(failing, transcript, chunk_chars=600)
    with pytest.raises(AnalysisError):
        a.run_all(store.get("riunione"), save=lambda c: saved.update(c))
    assert "chunks" in saved and "summaries" in saved and "extraction" not in saved

    ok = FakeLLM()
    Analyzer(ok, transcript, cache=saved, chunk_chars=600).run_all(store.get("riunione"))
    assert {c[2] for c in ok.calls} == {m.ExtractionOut, m.MindMapOut}


def test_ask_returns_citations(transcript, fake_llm):
    a = Analyzer(fake_llm, transcript)
    r = a.ask("Qual è il budget?")
    assert r["citations"][0]["segment_id"] == 0
    assert r["citations"][0]["timestamp"] == "00:00:00"
    # secondo turno: la trascrizione resta nel primo messaggio (cache), non viene ripetuta
    a.ask("E chi fa il preventivo?", [{"role": "user", "content": "Qual è il budget?"},
                                       {"role": "assistant", "content": r["answer"]}])
    msgs = fake_llm.calls[-1][1]
    assert "TRASCRIZIONE COMPLETA" in msgs[0]["content"][0]["text"]
    assert len(msgs[-1]["content"]) == 1


def test_ask_with_small_context_picks_relevant_passages(transcript, fake_llm):
    fake_llm.context_chars = 800
    a = Analyzer(fake_llm, transcript)
    a.ask("Quanto è il budget del preventivo?")
    text = fake_llm.calls[-1][1][-1]["content"][0]["text"]
    assert text.startswith("PASSAGGI PERTINENTI")
    assert "40.000 euro" in text and len(text) < 900


def test_custom_templates(tmp_path, fake_llm):
    store = TemplateStore(tmp_path / "t.json")
    t = create_template(fake_llm, store, "assemblea di condominio")
    assert t.id == "condominio" and not t.builtin
    t2 = create_template(fake_llm, store, "di nuovo")
    assert t2.id == "condominio-2"
    assert store.get("condominio").instructions == "## Spese"
    store.delete("condominio")
    with pytest.raises(NotFoundError):
        store.get("condominio")
