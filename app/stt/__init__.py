"""Livello di trascrizione (speech-to-text). Per aggiungere un motore, implementa SpeechToText."""

from __future__ import annotations

from ..config import Settings
from ..errors import TranscriptionError
from .base import Diarizer, SpeechToText, assign_speakers


def get_engine(settings: Settings) -> SpeechToText:
    if settings.stt_engine == "faster-whisper":
        from .faster_whisper_engine import FasterWhisperEngine

        return FasterWhisperEngine(settings.whisper_model, settings.language, settings.whisper_device,
                                   settings.whisper_compute_type, settings.whisper_threads,
                                   settings.whisper_vocabulary)
    if settings.stt_engine == "whisper-cpp":
        from .whisper_cpp_engine import WhisperCppEngine

        return WhisperCppEngine(settings.whisper_cpp_bin, settings.whisper_cpp_model, settings.language,
                                settings.whisper_threads, settings.whisper_vocabulary)
    raise TranscriptionError(f"Motore di trascrizione sconosciuto: '{settings.stt_engine}'")


def get_diarizer(settings: Settings, speakers: int | None = None) -> Diarizer | None:
    """speakers: numero di persone che parlano, se noto (1 = nessun riconoscimento)."""
    if not settings.diarization or speakers == 1:
        return None
    if settings.diarization_engine == "pyannote":
        from .diarization import PyannoteDiarizer

        return PyannoteDiarizer(settings.diarization_model, settings.hf_token, speakers)
    if settings.diarization_engine == "sherpa":
        from .sherpa_diarization import SherpaDiarizer

        return SherpaDiarizer(settings.models_dir, speakers, settings.diarization_threshold)
    raise TranscriptionError(f"Motore di riconoscimento interlocutori sconosciuto: '{settings.diarization_engine}'")


__all__ = ["get_engine", "get_diarizer", "assign_speakers", "SpeechToText", "Diarizer"]
