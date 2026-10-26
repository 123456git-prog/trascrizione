"""Trascrizione locale con faster-whisper (CPU). Installazione semplice anche su Windows."""

from __future__ import annotations

from pathlib import Path

from ..errors import TranscriptionError
from ..models import Segment, Transcript, Word
from .base import ProgressFn, build_prompt, no_progress, split_sentences


class FasterWhisperEngine:
    name = "faster-whisper"

    def __init__(self, model: str, language: str, device: str = "cpu", compute_type: str = "int8",
                 threads: int = 0, vocabulary: str = ""):
        self.model_name = model
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self.threads = threads
        self.vocabulary = vocabulary
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise TranscriptionError(
                    "faster-whisper non è installato. Esegui: pip install -r requirements-stt.txt"
                )
            try:
                # al primo avvio scarica il modello (circa 1,6 GB per large-v3-turbo)
                self._model = WhisperModel(
                    self.model_name, device=self.device, compute_type=self.compute_type,
                    cpu_threads=self.threads,
                )
            except Exception as e:  # noqa: BLE001 - errori di rete/disco del downloader
                raise TranscriptionError(f"Impossibile caricare il modello '{self.model_name}': {e}")
        return self._model

    def transcribe(self, wav_path: Path, duration: float, progress: ProgressFn = no_progress) -> Transcript:
        model = self._load()
        progress(0.0, f"Modello {self.model_name} pronto")
        try:
            segments_iter, info = model.transcribe(
                str(wav_path),
                language=self.language,
                vad_filter=True,  # salta i silenzi, riduce le "allucinazioni"
                beam_size=5,
                word_timestamps=True,  # per dividere in frasi e tra interlocutori
                condition_on_previous_text=False,  # evita ripetizioni a catena nelle registrazioni lunghe
                # "hotwords" viene ripetuto in ogni finestra di 30 secondi; initial_prompt solo nella prima
                # (con condition_on_previous_text=False)
                hotwords=build_prompt(self.vocabulary),
            )
            total = duration or info.duration or 1.0
            segments: list[Segment] = []
            for s in segments_iter:
                words = [Word(start=w.start, end=w.end, text=w.word) for w in (getattr(s, "words", None) or [])]
                if words:
                    # un segmento di Whisper può contenere più frasi (e più persone): una frase per segmento
                    for sentence in split_sentences(words):
                        text = "".join(w.text for w in sentence).strip()
                        if text:
                            segments.append(Segment(id=len(segments), start=round(sentence[0].start, 2),
                                                    end=round(sentence[-1].end, 2), text=text, words=sentence))
                elif s.text.strip():
                    segments.append(Segment(id=len(segments), start=round(s.start, 2), end=round(s.end, 2),
                                            text=s.text.strip()))
                progress(min(s.end / total, 1.0), f"Trascritti {int(s.end // 60)} min su {int(total // 60)}")
        except TranscriptionError:
            raise
        except Exception as e:  # noqa: BLE001
            raise TranscriptionError(f"Errore durante la trascrizione: {e}")
        return Transcript(language=self.language, duration=total, engine=self.name,
                          model=self.model_name, segments=segments)
