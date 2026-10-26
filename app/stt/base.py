"""Interfaccia comune dei motori di trascrizione: si possono sostituire senza toccare il resto."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Protocol

from ..models import Transcript

# progress(frazione 0..1, messaggio)
ProgressFn = Callable[[float, str], None]


def no_progress(fraction: float, message: str) -> None:
    pass


# Whisper imita lo stile del testo che riceve come suggerimento: una frase italiana ben punteggiata
# lo spinge a mettere punti, virgole e domande. Senza, large-v3-turbo tende a omettere la punteggiatura.
STYLE_PROMPT = "Buongiorno a tutti. Allora, cominciamo: oggi parliamo del progetto, d'accordo? Sì, certo. Va bene."


def build_prompt(vocabulary: str) -> str:
    vocabulary = vocabulary.strip().rstrip(".")
    return f"{STYLE_PROMPT} Termini: {vocabulary}." if vocabulary else STYLE_PROMPT


class SpeechToText(Protocol):
    name: str

    def transcribe(self, wav_path: Path, duration: float, progress: ProgressFn = no_progress) -> Transcript:
        """Trascrive un WAV mono 16 kHz e restituisce segmenti con timestamp (senza interlocutori)."""
        ...


class Diarizer(Protocol):
    def diarize(self, wav_path: Path, progress: ProgressFn = no_progress) -> list[tuple[float, float, str]]:
        """Restituisce turni (inizio, fine, etichetta interlocutore)."""
        ...


def assign_speakers(transcript: Transcript, turns: list[tuple[float, float, str]]) -> Transcript:
    """Assegna a ogni segmento l'interlocutore che si sovrappone di più nel tempo."""
    if not turns:
        return transcript
    turns = sorted(turns)
    for seg in transcript.segments:
        best: Optional[str] = None
        best_overlap = 0.0
        for start, end, speaker in turns:
            if start >= seg.end:
                break
            overlap = min(end, seg.end) - max(start, seg.start)
            if overlap > best_overlap:
                best, best_overlap = speaker, overlap
        if best is None:
            # nessuna sovrapposizione: prendi il turno più vicino
            mid = (seg.start + seg.end) / 2
            best = min(turns, key=lambda t: min(abs(t[0] - mid), abs(t[1] - mid)))[2]
        seg.speaker = best
    # rinumera le etichette in ordine di prima apparizione (SPEAKER_00, SPEAKER_01...)
    mapping: dict[str, str] = {}
    for seg in transcript.segments:
        if seg.speaker not in mapping:
            mapping[seg.speaker] = f"SPEAKER_{len(mapping):02d}"
        seg.speaker = mapping[seg.speaker]
    return transcript
