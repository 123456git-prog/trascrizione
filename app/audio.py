"""Conversione e controllo dei file audio tramite ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .errors import AudioError

SUPPORTED_EXTENSIONS = {".mp3", ".m4a", ".wav", ".webm", ".ogg", ".mp4", ".aac", ".flac"}


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise AudioError(
            f"'{tool}' non trovato. Installa ffmpeg (su Windows: 'winget install Gyan.FFmpeg') "
            "e riapri il terminale."
        )
    return path


def check_file(path: Path) -> None:
    if not path.exists():
        raise AudioError(f"File non trovato: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise AudioError(
            f"Formato '{path.suffix}' non supportato. Formati accettati: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
    if path.stat().st_size == 0:
        raise AudioError("Il file audio è vuoto.")


def probe_duration(path: Path) -> float:
    ffprobe = _require("ffprobe")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AudioError(f"Il file non sembra un audio valido: {result.stderr.strip()[:300]}")
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise AudioError("Impossibile leggere la durata del file audio.")


def to_wav16k(src: Path, dst: Path) -> Path:
    """Converte in WAV mono 16 kHz, il formato che si aspettano i modelli di trascrizione."""
    ffmpeg = _require("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not dst.exists():
        raise AudioError(f"Conversione audio non riuscita: {result.stderr.strip()[:300]}")
    return dst
