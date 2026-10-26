"""Riconoscimento degli interlocutori in locale con pyannote."""

from __future__ import annotations

import wave
from pathlib import Path

from ..errors import TranscriptionError
from .base import ProgressFn, no_progress


class PyannoteDiarizer:
    def __init__(self, model: str, hf_token: str, num_speakers: int | None = None):
        self.model = model
        self.num_speakers = num_speakers if num_speakers and num_speakers > 1 else None
        self.hf_token = hf_token
        self._pipeline = None

    def _load(self):
        if self._pipeline is not None:
            return self._pipeline
        if not self.hf_token:
            raise TranscriptionError(
                "Per riconoscere gli interlocutori serve HF_TOKEN (gratuito, vedi README). "
                "In alternativa imposta DIARIZATION=false."
            )
        try:
            from pyannote.audio import Pipeline
        except ImportError:
            raise TranscriptionError(
                "pyannote.audio non è installato. Esegui: pip install -r requirements-diarization.txt "
                "oppure imposta DIARIZATION=false."
            )
        try:
            try:
                pipeline = Pipeline.from_pretrained(self.model, token=self.hf_token)
            except TypeError:  # pyannote 3.x usa use_auth_token
                pipeline = Pipeline.from_pretrained(self.model, use_auth_token=self.hf_token)
        except Exception as e:  # noqa: BLE001
            raise TranscriptionError(
                f"Impossibile caricare il modello '{self.model}'. Hai accettato le condizioni d'uso "
                f"su huggingface.co? Dettaglio: {e}"
            )
        if pipeline is None:
            raise TranscriptionError(
                f"Accesso negato al modello '{self.model}': accetta le condizioni d'uso su huggingface.co."
            )
        self._pipeline = pipeline
        return pipeline

    def diarize(self, wav_path: Path, progress: ProgressFn = no_progress) -> list[tuple[float, float, str]]:
        pipeline = self._load()
        import numpy as np
        import torch

        # carichiamo noi il WAV: evita problemi di decodifica audio di torchaudio su Windows
        with wave.open(str(wav_path), "rb") as w:
            rate = w.getframerate()
            frames = w.readframes(w.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        audio = {"waveform": torch.from_numpy(samples).unsqueeze(0), "sample_rate": rate}

        progress(0.0, "Riconoscimento interlocutori in corso")
        try:
            output = pipeline(audio, num_speakers=self.num_speakers) if self.num_speakers else pipeline(audio)
        except Exception as e:  # noqa: BLE001
            raise TranscriptionError(f"Errore nel riconoscimento interlocutori: {e}")
        annotation = getattr(output, "speaker_diarization", output)  # pyannote 4 restituisce un oggetto
        turns = [(round(t.start, 2), round(t.end, 2), str(label))
                 for t, _, label in annotation.itertracks(yield_label=True)]
        progress(1.0, f"Trovati {len({t[2] for t in turns})} interlocutori")
        return turns
