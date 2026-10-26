"""Configurazione letta da variabili d'ambiente (o dal file .env nella cartella del progetto)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv è opzionale
    pass


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sì", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "data")).resolve())
    language: str = field(default_factory=lambda: os.getenv("LANGUAGE", "it"))

    # Motore di trascrizione: "faster-whisper" (CPU, installazione semplice) o "whisper-cpp" (Vulkan/AMD)
    stt_engine: str = field(default_factory=lambda: os.getenv("STT_ENGINE", "faster-whisper"))
    whisper_model: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL", "large-v3-turbo"))
    whisper_device: str = field(default_factory=lambda: os.getenv("WHISPER_DEVICE", "cpu"))
    whisper_compute_type: str = field(default_factory=lambda: os.getenv("WHISPER_COMPUTE_TYPE", "int8"))
    whisper_threads: int = field(default_factory=lambda: _int("WHISPER_THREADS", 0))
    whisper_cpp_bin: str = field(default_factory=lambda: os.getenv("WHISPER_CPP_BIN", "whisper-cli"))
    whisper_cpp_model: str = field(default_factory=lambda: os.getenv("WHISPER_CPP_MODEL", ""))
    # Parole difficili (nomi, sigle) che aiutano il riconoscimento, separate da virgola
    whisper_vocabulary: str = field(default_factory=lambda: os.getenv("WHISPER_VOCABULARY", ""))

    # Riconoscimento interlocutori in locale: "sherpa" (leggero, nessun account) o "pyannote"
    # (più pesante, serve un token gratuito di Hugging Face)
    diarization: bool = field(default_factory=lambda: _bool("DIARIZATION", True))
    diarization_engine: str = field(default_factory=lambda: os.getenv("DIARIZATION_ENGINE", "sherpa"))
    # usata solo se il numero di persone non è noto: più alta = meno interlocutori distinti
    diarization_threshold: float = field(default_factory=lambda: float(os.getenv("DIARIZATION_THRESHOLD", "0.4")))
    hf_token: str = field(default_factory=lambda: os.getenv("HF_TOKEN", ""))
    diarization_model: str = field(
        default_factory=lambda: os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1")
    )

    # Analisi del testo: "ollama" (locale, gratis, lento), "gemini" (cloud, quota gratuita,
    # solo dati non sensibili) o "claude" (API a pagamento)
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "ollama"))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma3:4b"))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    ollama_num_ctx: int = field(default_factory=lambda: _int("OLLAMA_NUM_CTX", 16384))
    ollama_chunk_chars: int = field(default_factory=lambda: _int("OLLAMA_CHUNK_CHARS", 12000))
    claude_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-opus-5-5"))
    claude_effort: str = field(default_factory=lambda: os.getenv("CLAUDE_EFFORT", "medium"))
    # Dimensione dei blocchi per le registrazioni lunghe (caratteri, circa 4 caratteri per token)
    chunk_chars: int = field(default_factory=lambda: _int("CHUNK_CHARS", 40000))
    analysis_workers: int = field(default_factory=lambda: _int("ANALYSIS_WORKERS", 3))

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def templates_file(self) -> Path:
        return self.data_dir / "templates.json"


def get_settings() -> Settings:
    return Settings()
