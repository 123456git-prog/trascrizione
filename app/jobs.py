"""Coda delle elaborazioni lunghe, eseguite in background una alla volta.

Una alla volta perché la trascrizione usa tutto il processore. Lo stato e l'avanzamento sono
salvati in meta.json, così l'interfaccia li legge e un riavvio del server riprende i lavori in sospeso.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from .errors import AppError
from .search import SearchIndex
from .service import Service

log = logging.getLogger("trascrizione.jobs")

ACTIVE_STATES = {"in coda", "trascrizione", "analisi"}


class JobQueue:
    def __init__(self, service: Service, index: Optional[SearchIndex] = None):
        self.service = service
        self.index = index
        self._queue: "queue.Queue[str | None]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self.current: Optional[str] = None

    def start(self) -> None:
        # riprende i lavori interrotti da un riavvio
        for meta in reversed(self.service.store.list()):
            if meta.job and meta.status in ACTIVE_STATES:
                self.service.store.update_meta(meta.id, status="in coda", progress_message="In attesa")
                self._queue.put(meta.id)
        self._thread = threading.Thread(target=self._run, name="job-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(None)

    def submit(self, rec_id: str, kind: str, **params) -> None:
        """kind: "process" (trascrizione + analisi), "transcribe", "analyze", "summary"."""
        meta = self.service.store.meta(rec_id)
        if meta.job and meta.status in ACTIVE_STATES:
            raise AppError("C'è già un'elaborazione in corso per questa registrazione.")
        self.service.store.update_meta(rec_id, job={"kind": kind, **params}, status="in coda",
                                       progress=0.0, progress_message="In attesa", error=None)
        self._queue.put(rec_id)

    def position(self, rec_id: str) -> int:
        """0 = in lavorazione, 1.. = posizione in coda, -1 = non in coda."""
        if self.current == rec_id:
            return 0
        pending = list(self._queue.queue)
        return pending.index(rec_id) + 1 if rec_id in pending else -1

    def _run(self) -> None:
        while True:
            rec_id = self._queue.get()
            if rec_id is None:
                return
            self.current = rec_id
            try:
                self._execute(rec_id)
            except Exception as e:  # noqa: BLE001 - il worker non deve mai fermarsi
                log.exception("Elaborazione fallita per %s", rec_id)
                message = str(e) if isinstance(e, AppError) else f"Errore imprevisto: {e}"
                try:
                    self.service.store.update_meta(rec_id, status="errore", error=message, job=None)
                except AppError:
                    pass  # registrazione eliminata nel frattempo
            finally:
                self.current = None
                if self.index:
                    self.index.index(self.service.store, rec_id)

    def _execute(self, rec_id: str) -> None:
        svc = self.service
        try:
            job = svc.store.meta(rec_id).job
        except AppError:
            return  # eliminata mentre era in coda
        if not job:
            return
        kind = job["kind"]
        template = job.get("template") or "riunione"
        provider = job.get("provider")
        if kind in ("process", "transcribe"):
            svc.transcribe(rec_id, force=job.get("force", False), speakers=job.get("speakers"))
        if kind in ("process", "analyze"):
            svc.analyze(rec_id, template, provider=provider)
        if kind == "summary":
            svc.summary(rec_id, template, provider=provider, force=job.get("force", False))
        meta = svc.store.meta(rec_id)
        final = meta.status if meta.status in ("pronta", "trascritta") else "pronta"
        svc.store.update_meta(rec_id, job=None, status=final, progress=1.0, error=None)
