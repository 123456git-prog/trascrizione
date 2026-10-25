"""Archivio su disco: una cartella per registrazione con audio, trascrizione e analisi."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from .errors import NotFoundError
from .models import Transcript


class RecordingMeta(BaseModel):
    id: str
    title: str
    created_at: str
    original_filename: str
    audio_file: str
    duration: float = 0.0
    status: str = "caricata"  # caricata | trascrizione | analisi | pronta | errore
    progress: float = 0.0
    progress_message: str = ""
    error: Optional[str] = None


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # scrittura atomica: un'interruzione non lascia file a metà


class RecordingStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def dir(self, rec_id: str) -> Path:
        path = self.root / rec_id
        if not path.is_dir():
            raise NotFoundError(f"Registrazione '{rec_id}' non trovata.")
        return path

    def create(self, audio_src: Path, title: Optional[str] = None) -> RecordingMeta:
        rec_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        folder = self.root / rec_id
        folder.mkdir(parents=True)
        audio_name = "audio" + audio_src.suffix.lower()
        shutil.copy2(audio_src, folder / audio_name)
        meta = RecordingMeta(
            id=rec_id,
            title=title or audio_src.stem,
            created_at=datetime.now().isoformat(timespec="seconds"),
            original_filename=audio_src.name,
            audio_file=audio_name,
        )
        self.save_meta(meta)
        return meta

    def list(self) -> list[RecordingMeta]:
        metas = []
        for folder in sorted(self.root.iterdir(), reverse=True):
            if (folder / "meta.json").exists():
                metas.append(RecordingMeta(**json.loads((folder / "meta.json").read_text(encoding="utf-8"))))
        return metas

    def resolve_id(self, prefix: str) -> str:
        """Accetta anche un prefisso dell'id, comodo da riga di comando."""
        matches = [m.id for m in self.list() if m.id.startswith(prefix)]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise NotFoundError(f"Nessuna registrazione con id '{prefix}'.")
        raise NotFoundError(f"L'id '{prefix}' è ambiguo: " + ", ".join(matches))

    def meta(self, rec_id: str) -> RecordingMeta:
        return RecordingMeta(**json.loads((self.dir(rec_id) / "meta.json").read_text(encoding="utf-8")))

    def save_meta(self, meta: RecordingMeta) -> None:
        _write_json(self.root / meta.id / "meta.json", meta.model_dump())

    def update_meta(self, rec_id: str, **fields: Any) -> RecordingMeta:
        meta = self.meta(rec_id).model_copy(update=fields)
        self.save_meta(meta)
        return meta

    def audio_path(self, rec_id: str) -> Path:
        return self.dir(rec_id) / self.meta(rec_id).audio_file

    # --- trascrizione: salvata una volta sola ---

    def has_transcript(self, rec_id: str) -> bool:
        return (self.dir(rec_id) / "transcript.json").exists()

    def transcript(self, rec_id: str) -> Transcript:
        path = self.dir(rec_id) / "transcript.json"
        if not path.exists():
            raise NotFoundError("La registrazione non è ancora stata trascritta.")
        return Transcript(**json.loads(path.read_text(encoding="utf-8")))

    def save_transcript(self, rec_id: str, transcript: Transcript) -> None:
        _write_json(self.dir(rec_id) / "transcript.json", transcript.model_dump())

    # --- analisi ---

    def analysis(self, rec_id: str) -> dict:
        path = self.dir(rec_id) / "analysis.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def save_analysis(self, rec_id: str, data: dict) -> None:
        _write_json(self.dir(rec_id) / "analysis.json", data)

    def delete(self, rec_id: str) -> None:
        shutil.rmtree(self.dir(rec_id))
