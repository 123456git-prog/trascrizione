"""Divisione della trascrizione in blocchi per le registrazioni lunghe."""

from __future__ import annotations

from ..models import Segment, Transcript


def chunk_segments(transcript: Transcript, max_chars: int) -> list[list[Segment]]:
    """Divide in blocchi consecutivi di al massimo `max_chars` caratteri (senza spezzare le frasi)."""
    chunks: list[list[Segment]] = []
    current: list[Segment] = []
    size = 0
    for seg in transcript.segments:
        line = len(transcript.render_line(seg)) + 1
        if current and size + line > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(seg)
        size += line
    if current:
        chunks.append(current)
    return chunks
