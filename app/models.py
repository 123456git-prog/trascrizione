"""Strutture dati condivise: trascrizione e risultati dell'analisi."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


def format_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# --- Trascrizione -----------------------------------------------------------


class Word(BaseModel):
    start: float
    end: float
    text: str  # con lo spazio iniziale, come lo restituisce Whisper


class Segment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    # tempi delle singole parole: servono solo per dividere i segmenti tra interlocutori, non si salvano
    words: Optional[list[Word]] = Field(default=None, exclude=True)


class Transcript(BaseModel):
    language: str = "it"
    duration: float = 0.0
    engine: str = ""
    model: str = ""
    segments: list[Segment] = Field(default_factory=list)
    # Nomi assegnati dall'utente agli interlocutori: {"SPEAKER_00": "Marco"}
    speaker_names: dict[str, str] = Field(default_factory=dict)

    def speaker_label(self, speaker: Optional[str]) -> str:
        if not speaker:
            return ""
        if speaker in self.speaker_names:
            return self.speaker_names[speaker]
        if speaker.startswith("SPEAKER_"):
            try:
                return f"Interlocutore {int(speaker.split('_')[1]) + 1}"
            except ValueError:
                pass
        return speaker

    def segment(self, segment_id: int) -> Optional[Segment]:
        if 0 <= segment_id < len(self.segments) and self.segments[segment_id].id == segment_id:
            return self.segments[segment_id]
        return next((s for s in self.segments if s.id == segment_id), None)

    def render_line(self, seg: Segment) -> str:
        """Riga usata nei prompt: l'id permette a Claude di citare il punto esatto."""
        who = self.speaker_label(seg.speaker)
        who = f" {who}:" if who else ""
        return f"[#{seg.id} {format_ts(seg.start)}]{who} {seg.text.strip()}"

    def render(self, segments: Optional[list[Segment]] = None) -> str:
        return "\n".join(self.render_line(s) for s in (segments if segments is not None else self.segments))

    def plain_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments)


# --- Risultati prodotti da Claude (schemi per l'output strutturato) ----------
# Claude restituisce solo segment_id: i timestamp vengono risolti dal codice,
# così non possono essere inventati.


class KeyPoint(BaseModel):
    text: str
    segment_id: int


class ChunkNotes(BaseModel):
    summary: str = Field(description="Riassunto dettagliato del blocco, in italiano")
    key_points: list[KeyPoint]


class SummaryOut(BaseModel):
    title: str = Field(description="Titolo breve e descrittivo della registrazione")
    markdown: str = Field(description="Riassunto in Markdown, strutturato secondo il template")


class Topic(BaseModel):
    title: str
    description: str
    segment_ids: list[int]


class KeywordsOut(BaseModel):
    keywords: list[str]
    topics: list[Topic]


class Decision(BaseModel):
    text: str
    segment_id: int


class ActionItem(BaseModel):
    task: str
    owner: Optional[str] = Field(description="Responsabile, null se non indicato")
    due_date: Optional[str] = Field(description="Scadenza come detta (o AAAA-MM-GG se chiara), null se assente")
    segment_id: int


class Person(BaseModel):
    name: str
    role: Optional[str] = Field(description="Ruolo o contesto, null se non noto")
    segment_id: int


class DateMention(BaseModel):
    text: str = Field(description="La data come è stata detta")
    normalized: Optional[str] = Field(description="AAAA-MM-GG se determinabile, altrimenti null")
    context: str
    segment_id: int


class Figure(BaseModel):
    value: str = Field(description="La cifra con unità di misura o valuta")
    context: str
    segment_id: int


class OpenQuestion(BaseModel):
    question: str
    segment_id: int


class ExtractionOut(BaseModel):
    decisions: list[Decision]
    action_items: list[ActionItem]
    people: list[Person]
    dates: list[DateMention]
    figures: list[Figure]
    open_questions: list[OpenQuestion]


class MindMapOut(BaseModel):
    markdown: str = Field(
        description="Mappa mentale come elenco Markdown annidato: '# Titolo' poi '## Ramo' e voci '- ' indentate"
    )


class ChatAnswer(BaseModel):
    answer: str = Field(description="Risposta in italiano con citazioni inline nel formato [#id]")
    citations: list[int] = Field(description="Gli id dei segmenti citati")


class TemplateOut(BaseModel):
    name: str
    description: str
    instructions: str
