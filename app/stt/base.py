"""Interfaccia comune dei motori di trascrizione: si possono sostituire senza toccare il resto."""

from __future__ import annotations

import bisect
from pathlib import Path
from typing import Callable, Optional, Protocol

from ..models import Segment, Transcript, Word

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


def split_sentences(words: list[Word], max_seconds: float = 30.0) -> list[list[Word]]:
    """Divide le parole in frasi (dopo . ? !), con un limite di durata per le frasi senza fine."""
    out: list[list[Word]] = [[]]
    for w in words:
        current = out[-1]
        if current and w.end - current[0].start > max_seconds:
            out.append(current := [])
        current.append(w)
        if w.text.strip().endswith((".", "?", "!", "…")):
            out.append([])
    return [s for s in out if s]


def _speaker_at(starts: list[float], turns: list[tuple[float, float, str]], start: float, end: float) -> str:
    """Interlocutore che si sovrappone di più all'intervallo; se nessuno, il turno più vicino."""
    i = bisect.bisect_left(starts, end)  # turni che iniziano prima della fine dell'intervallo: [0, i)
    best: Optional[str] = None
    best_overlap = 0.0
    j = i - 1
    while j >= 0 and j >= i - 50:  # i turni precedenti che possono ancora sovrapporsi
        t_start, t_end, speaker = turns[j]
        overlap = min(t_end, end) - max(t_start, start)
        if overlap > best_overlap:
            best, best_overlap = speaker, overlap
        j -= 1
    if best is not None:
        return best
    mid = (start + end) / 2
    near = [turns[k] for k in (i - 1, i) if 0 <= k < len(turns)]
    return min(near, key=lambda t: min(abs(t[0] - mid), abs(t[1] - mid)))[2]


def _speaker_runs(words: list[Word], speakers: list[str]) -> list[tuple[str, list[Word]]]:
    runs: list[tuple[str, list[Word]]] = []
    for w, sp in zip(words, speakers):
        if runs and runs[-1][0] == sp:
            runs[-1][1].append(w)
        else:
            runs.append((sp, [w]))
    # cambi di voce di una o due parole brevissime sono quasi sempre rumore: si uniscono al vicino
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for k, (sp, ws) in enumerate(runs):
            if len(ws) <= 2 and ws[-1].end - ws[0].start < 0.6:
                target = k - 1 if k > 0 else k + 1
                tsp, tws = runs[target]
                runs[target] = (tsp, tws + ws if target < k else ws + tws)
                del runs[k]
                changed = True
                break
        # unisce run adiacenti rimasti con lo stesso interlocutore
        merged: list[tuple[str, list[Word]]] = []
        for sp, ws in runs:
            if merged and merged[-1][0] == sp:
                merged[-1][1].extend(ws)
            else:
                merged.append((sp, ws))
        runs = merged
    return runs


def assign_speakers(transcript: Transcript, turns: list[tuple[float, float, str]]) -> Transcript:
    """Assegna gli interlocutori. Con i tempi delle parole, un segmento in cui cambia voce viene diviso."""
    if not turns:
        return transcript
    turns = sorted(turns)
    starts = [t[0] for t in turns]
    out: list[Segment] = []
    for seg in transcript.segments:
        if not seg.words:
            seg.speaker = _speaker_at(starts, turns, seg.start, seg.end)
            out.append(seg)
            continue
        speakers = [_speaker_at(starts, turns, w.start, w.end) for w in seg.words]
        for sp, ws in _speaker_runs(seg.words, speakers):
            text = "".join(w.text for w in ws).strip()
            if text:
                out.append(Segment(id=0, start=round(ws[0].start, 2), end=round(ws[-1].end, 2), text=text,
                                   speaker=sp, words=ws))
    for i, seg in enumerate(out):
        seg.id = i
    transcript.segments = out
    # rinumera le etichette in ordine di prima apparizione (SPEAKER_00, SPEAKER_01...)
    mapping: dict[str, str] = {}
    for seg in transcript.segments:
        if seg.speaker not in mapping:
            mapping[seg.speaker] = f"SPEAKER_{len(mapping):02d}"
        seg.speaker = mapping[seg.speaker]
    return transcript
