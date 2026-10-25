"""Trascrizione locale con whisper.cpp (eseguibile esterno, può usare la GPU AMD via Vulkan)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..errors import TranscriptionError
from ..models import Segment, Transcript
from .base import ProgressFn, no_progress

_PROGRESS_RE = re.compile(r"progress\s*=\s*(\d+)%")


def parse_whisper_cpp_json(data: dict) -> list[Segment]:
    segments: list[Segment] = []
    for item in data.get("transcription", []):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        offsets = item.get("offsets", {})
        start = offsets.get("from", 0) / 1000
        end = offsets.get("to", 0) / 1000
        segments.append(Segment(id=len(segments), start=round(start, 2), end=round(end, 2), text=text))
    return segments


class WhisperCppEngine:
    name = "whisper-cpp"

    def __init__(self, binary: str, model_path: str, language: str, threads: int = 0, vocabulary: str = ""):
        self.binary = binary
        self.model_path = model_path
        self.language = language
        self.threads = threads
        self.vocabulary = vocabulary

    def transcribe(self, wav_path: Path, duration: float, progress: ProgressFn = no_progress) -> Transcript:
        binary = shutil.which(self.binary) or (self.binary if Path(self.binary).exists() else None)
        if not binary:
            raise TranscriptionError(
                f"Eseguibile whisper.cpp non trovato ('{self.binary}'). Imposta WHISPER_CPP_BIN nel file .env."
            )
        if not self.model_path or not Path(self.model_path).exists():
            raise TranscriptionError(
                "Modello whisper.cpp non trovato. Imposta WHISPER_CPP_MODEL con il percorso del file "
                "ggml (es. ggml-large-v3-turbo.bin)."
            )
        with tempfile.TemporaryDirectory() as tmp:
            out_base = Path(tmp) / "out"
            cmd = [binary, "-m", self.model_path, "-f", str(wav_path), "-l", self.language,
                   "-oj", "-of", str(out_base), "-pp"]
            if self.threads:
                cmd += ["-t", str(self.threads)]
            if self.vocabulary:
                cmd += ["--prompt", self.vocabulary]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
            tail: list[str] = []
            assert proc.stdout is not None
            for line in proc.stdout:
                tail = (tail + [line.rstrip()])[-20:]
                m = _PROGRESS_RE.search(line)
                if m:
                    pct = int(m.group(1))
                    progress(pct / 100, f"Trascrizione {pct}%")
            proc.wait()
            json_path = out_base.with_suffix(".json")
            if proc.returncode != 0 or not json_path.exists():
                raise TranscriptionError("whisper.cpp ha restituito un errore:\n" + "\n".join(tail[-8:]))
            data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
        return Transcript(language=self.language, duration=duration, engine=self.name,
                          model=Path(self.model_path).name, segments=parse_whisper_cpp_json(data))
