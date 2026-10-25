"""Ricerca a testo libero su tutte le registrazioni (SQLite FTS5, ignora maiuscole e accenti)."""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

from .errors import NotFoundError
from .storage import RecordingStore


class SearchIndex:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5("
                "rec_id UNINDEXED, title, summary, transcript, tokenize='unicode61 remove_diacritics 2')"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def index(self, store: RecordingStore, rec_id: str) -> None:
        try:
            meta = store.meta(rec_id)
        except NotFoundError:
            return self.remove(rec_id)
        transcript = store.transcript(rec_id).plain_text() if store.has_transcript(rec_id) else ""
        analysis = store.analysis(rec_id)
        summary = "\n".join(s["title"] + "\n" + s["markdown"] for s in analysis.get("summaries", {}).values())
        keywords = " ".join(analysis.get("keywords", {}).get("keywords", []))
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM docs WHERE rec_id = ?", (rec_id,))
            db.execute("INSERT INTO docs (rec_id, title, summary, transcript) VALUES (?, ?, ?, ?)",
                       (rec_id, meta.title, summary + "\n" + keywords, transcript))

    def remove(self, rec_id: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM docs WHERE rec_id = ?", (rec_id,))

    def rebuild(self, store: RecordingStore) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM docs")
        for meta in store.list():
            self.index(store, meta.id)

    def search(self, query: str, limit: int = 50) -> list[dict]:
        # ogni parola diventa un prefisso: "preven" trova "preventivo"
        terms = [t for t in re.findall(r"\w+", query, flags=re.UNICODE)]
        if not terms:
            return []
        fts_query = " ".join(f'"{t}"*' for t in terms)
        with self._connect() as db:
            rows = db.execute(
                "SELECT rec_id, snippet(docs, -1, '[', ']', '…', 14) FROM docs WHERE docs MATCH ? "
                "ORDER BY bm25(docs, 0, 10.0, 3.0, 1.0) LIMIT ?",
                (fts_query, limit),
            ).fetchall()
        return [{"id": rec_id, "snippet": snippet} for rec_id, snippet in rows]
