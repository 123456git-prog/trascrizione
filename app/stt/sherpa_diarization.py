"""Riconoscimento degli interlocutori in locale con sherpa-onnx.

Leggero (circa 35 MB di modelli, nessun account da creare) e abbastanza veloce sul processore
anche per registrazioni di due ore. I modelli si scaricano da soli al primo utilizzo.
"""

from __future__ import annotations

import os
import tarfile
import tempfile
import urllib.request
import wave
from pathlib import Path
from typing import Optional

from ..errors import TranscriptionError
from .base import ProgressFn, no_progress

_RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_ARCHIVE = f"{_RELEASES}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
SEGMENTATION_FILE = "sherpa-onnx-pyannote-segmentation-3-0/model.onnx"
EMBEDDING_URL = f"{_RELEASES}/speaker-recongition-models/wespeaker_en_voxceleb_resnet34_LM.onnx"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, tmp.open("wb") as out:
            while chunk := r.read(1024 * 1024):
                out.write(chunk)
        tmp.replace(dest)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise TranscriptionError(
            f"Download del modello per gli interlocutori non riuscito ({e}). Controlla la connessione "
            "e riprova, oppure imposta DIARIZATION=false."
        )


class SherpaDiarizer:
    def __init__(self, models_dir: Path, num_speakers: Optional[int] = None, threshold: float = 0.4):
        self.models_dir = models_dir
        self.num_speakers = num_speakers if num_speakers and num_speakers > 1 else None
        self.threshold = threshold

    def _models(self) -> tuple[Path, Path]:
        segmentation = self.models_dir / SEGMENTATION_FILE
        if not segmentation.exists():
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "segmentation.tar.bz2"
                _download(SEGMENTATION_ARCHIVE, archive)
                with tarfile.open(archive) as tar:
                    tar.extractall(self.models_dir, filter="data")
        embedding = self.models_dir / Path(EMBEDDING_URL).name
        if not embedding.exists():
            _download(EMBEDDING_URL, embedding)
        return segmentation, embedding

    def diarize(self, wav_path: Path, progress: ProgressFn = no_progress) -> list[tuple[float, float, str]]:
        try:
            import numpy as np
            import sherpa_onnx
        except ImportError:
            raise TranscriptionError(
                "sherpa-onnx non è installato. Esegui: pip install -r requirements-stt.txt "
                "oppure imposta DIARIZATION=false."
            )
        progress(0.0, "Preparazione riconoscimento interlocutori")
        segmentation, embedding = self._models()
        threads = max(1, (os.cpu_count() or 2) - 1)
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation)),
                num_threads=threads,
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(embedding), num_threads=threads),
            clustering=sherpa_onnx.FastClusteringConfig(
                # con il numero di persone noto il risultato è molto più affidabile
                num_clusters=self.num_speakers or -1, threshold=self.threshold,
            ),
            min_duration_on=0.3,
            min_duration_off=0.5,
        )
        if not config.validate():
            raise TranscriptionError("Configurazione del riconoscimento interlocutori non valida.")
        sd = sherpa_onnx.OfflineSpeakerDiarization(config)

        with wave.open(str(wav_path), "rb") as w:
            if w.getframerate() != sd.sample_rate:
                raise TranscriptionError("Il riconoscimento interlocutori richiede audio a 16 kHz.")
            samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

        def on_progress(done: int, total: int) -> int:
            progress(done / max(total, 1), "Riconoscimento interlocutori")
            return 0

        try:
            result = sd.process(samples, callback=on_progress).sort_by_start_time()
        except Exception as e:  # noqa: BLE001
            raise TranscriptionError(f"Errore nel riconoscimento interlocutori: {e}")
        turns = [(round(r.start, 2), round(r.end, 2), f"SPEAKER_{r.speaker:02d}") for r in result]
        progress(1.0, f"Trovati {len({t[2] for t in turns})} interlocutori")
        return turns
