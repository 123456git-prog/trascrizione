import re

import pytest

from app import models as m
from app.models import Segment, Transcript


def make_transcript(n: int = 40, words: int = 12) -> Transcript:
    segs = []
    for i in range(n):
        text = f"Frase numero {i} " + " ".join(["parola"] * words)
        if i == 7:
            text = "Decidiamo di approvare il budget di 40.000 euro, Marco prepara il preventivo entro venerdì."
        segs.append(Segment(id=i, start=i * 5.0, end=i * 5.0 + 4.5, text=text,
                            speaker=f"SPEAKER_0{i % 2}"))
    return Transcript(duration=n * 5.0, engine="test", model="test", segments=segs)


class FakeLLM:
    """Restituisce risposte valide per ogni schema e registra le chiamate."""

    def __init__(self, fail_on: type | None = None):
        self.calls: list[tuple[str, list[dict], type]] = []
        self.fail_on = fail_on

    @staticmethod
    def _text(messages):
        parts = []
        for msg in messages:
            c = msg["content"]
            parts.extend(b["text"] for b in c) if isinstance(c, list) else parts.append(c)
        return "\n".join(parts)

    def structured(self, system, messages, schema):
        from app.errors import AnalysisError

        self.calls.append((system, messages, schema))
        if self.fail_on is schema:
            raise AnalysisError("errore simulato")
        ids = [int(x) for x in re.findall(r"\[#(\d+)", self._text(messages))] or [0]
        first, last = ids[0], ids[-1]
        if schema is m.ChunkNotes:
            return m.ChunkNotes(summary=f"Appunti {first}-{last}",
                                key_points=[m.KeyPoint(text="punto", segment_id=first),
                                            m.KeyPoint(text="fuori blocco", segment_id=9999)])
        if schema is m.SummaryOut:
            return m.SummaryOut(title="Riunione budget", markdown="## Contesto\nTesto")
        if schema is m.KeywordsOut:
            return m.KeywordsOut(keywords=["budget", "preventivo"],
                                 topics=[m.Topic(title="Budget", description="d", segment_ids=[last, first])])
        if schema is m.ExtractionOut:
            return m.ExtractionOut(
                decisions=[m.Decision(text="Approvato budget", segment_id=first)],
                action_items=[m.ActionItem(task="Preventivo", owner="Marco", due_date=None, segment_id=first)],
                people=[m.Person(name="Marco", role=None, segment_id=first)],
                dates=[], figures=[m.Figure(value="40.000 €", context="budget", segment_id=first)],
                open_questions=[])
        if schema is m.MindMapOut:
            return m.MindMapOut(markdown="# Riunione\n## Budget\n- 40.000 euro")
        if schema is m.ChatAnswer:
            return m.ChatAnswer(answer=f"Il budget è 40.000 euro [#{first}].", citations=[first])
        if schema is m.TemplateOut:
            return m.TemplateOut(name="Condominio", description="Assemblee", instructions="## Spese")
        raise AssertionError(schema)


@pytest.fixture
def transcript():
    return make_transcript()


@pytest.fixture
def fake_llm():
    return FakeLLM()
