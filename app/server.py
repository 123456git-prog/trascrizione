"""Server web: API per l'interfaccia, elaborazioni in background, file statici dell'interfaccia.

Avvio:  python -m app.server        (poi apri http://localhost:8000, o dal telefono l'indirizzo mostrato)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import shutil
import socket
import sys
import tempfile
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .analysis.pipeline import create_template
from .config import Settings, get_settings
from .errors import AppError, NotFoundError
from .export import to_markdown
from .jobs import JobQueue
from .search import SearchIndex
from .service import Service

log = logging.getLogger("trascrizione.server")
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
COOKIE = "trascrizione_auth"


class TemplateIn(BaseModel):
    description: str
    provider: Optional[str] = None


class AnalyzeIn(BaseModel):
    template: str = "riunione"
    provider: Optional[str] = None
    force: bool = False


class TranscribeIn(BaseModel):
    force: bool = False
    speakers: int = 0  # 0 = non noto


class AskIn(BaseModel):
    question: str
    history: list[dict] = []
    provider: Optional[str] = None


class RecordingPatch(BaseModel):
    title: Optional[str] = None
    speaker_names: Optional[dict[str, str]] = None


class SegmentPatch(BaseModel):
    text: Optional[str] = None
    speaker: Optional[str] = None


class LoginIn(BaseModel):
    password: str


def _token(password: str) -> str:
    return hashlib.sha256(("trascrizione:" + password).encode()).hexdigest()


def create_app(settings: Optional[Settings] = None, service: Optional[Service] = None,
               start_worker: bool = True) -> FastAPI:
    settings = settings or get_settings()
    service = service or Service(settings)
    index = SearchIndex(settings.data_dir / "search.db")
    jobs = JobQueue(service, index)
    password = os.getenv("APP_PASSWORD", "")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        index.rebuild(service.store)
        if start_worker:
            jobs.start()
        yield
        jobs.stop()

    app = FastAPI(title="Trascrizione", lifespan=lifespan)
    app.state.service, app.state.jobs, app.state.index = service, jobs, index

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        code = 404 if isinstance(exc, NotFoundError) else 400
        return JSONResponse({"detail": str(exc)}, status_code=code)

    # --- accesso protetto da password (facoltativo, consigliato se usi il telefono in rete) ---

    def auth(request: Request) -> None:
        if not password:
            return
        if hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(password)):
            return
        raise HTTPException(401, "Accesso richiesto")

    @app.post("/api/login")
    def login(body: LoginIn, response: Response):
        if not password or hmac.compare_digest(body.password, password):
            response.set_cookie(COOKIE, _token(password), httponly=True, samesite="strict",
                                max_age=60 * 60 * 24 * 90)
            return {"ok": True}
        raise HTTPException(401, "Password errata")

    @app.get("/api/session")
    def session(request: Request):
        needs = bool(password) and not hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(password))
        return {"authenticated": not needs, "password_required": bool(password)}

    api = Depends(auth)

    # --- registrazioni ---

    def summary_of(meta) -> dict:
        data = meta.model_dump()
        data["queue_position"] = jobs.position(meta.id)
        return data

    @app.get("/api/recordings", dependencies=[api])
    def list_recordings(q: str = ""):
        metas = {m.id: m for m in service.store.list()}
        if not q.strip():
            return [summary_of(m) for m in metas.values()]
        results = []
        for hit in index.search(q):
            if hit["id"] in metas:
                results.append({**summary_of(metas[hit["id"]]), "snippet": hit["snippet"]})
        return results

    @app.post("/api/recordings", dependencies=[api], status_code=201)
    def upload(file: UploadFile = File(...), title: str = Form(""), template: str = Form("riunione"),
               provider: str = Form(""), analyze: bool = Form(True), speakers: int = Form(0)):
        suffix = Path(file.filename or "audio.webm").suffix.lower() or ".webm"
        service.templates.get(template)
        with tempfile.TemporaryDirectory() as tmp:
            # conserva il nome originale: diventa il titolo provvisorio
            name = Path(file.filename or f"Registrazione{suffix}").name
            path = Path(tmp) / name
            with path.open("wb") as out:
                shutil.copyfileobj(file.file, out, length=1024 * 1024)
            if path.suffix.lower() != suffix:
                path = path.rename(path.with_suffix(suffix))
            rec_id = service.import_audio(path, title.strip() or None)
        jobs.submit(rec_id, "process" if analyze else "transcribe", template=template, provider=provider or None,
                    speakers=speakers or None)
        return summary_of(service.store.meta(rec_id))

    @app.get("/api/recordings/{rec_id}", dependencies=[api])
    def get_recording(rec_id: str):
        meta = service.store.meta(rec_id)
        transcript = service.store.transcript(rec_id).model_dump() if service.store.has_transcript(rec_id) else None
        return {"meta": summary_of(meta), "transcript": transcript, "analysis": service.store.analysis(rec_id)}

    @app.get("/api/recordings/{rec_id}/status", dependencies=[api])
    def get_status(rec_id: str):
        return summary_of(service.store.meta(rec_id))

    @app.patch("/api/recordings/{rec_id}", dependencies=[api])
    def patch_recording(rec_id: str, body: RecordingPatch):
        if body.title is not None:
            if not body.title.strip():
                raise AppError("Il titolo non può essere vuoto.")
            service.store.update_meta(rec_id, title=body.title.strip())
        if body.speaker_names is not None:
            t = service.store.transcript(rec_id)
            t.speaker_names = {k: v.strip() for k, v in body.speaker_names.items() if v.strip()}
            service.store.save_transcript(rec_id, t)
        index.index(service.store, rec_id)
        return summary_of(service.store.meta(rec_id))

    @app.patch("/api/recordings/{rec_id}/segments/{segment_id}", dependencies=[api])
    def patch_segment(rec_id: str, segment_id: int, body: SegmentPatch):
        """Correzione manuale della trascrizione. Le analisi già fatte restano, segnate come da aggiornare."""
        t = service.store.transcript(rec_id)
        seg = t.segment(segment_id)
        if seg is None:
            raise NotFoundError("Segmento non trovato.")
        if body.text is not None:
            seg.text = body.text.strip()
        if body.speaker is not None:
            seg.speaker = body.speaker or None
        service.store.save_transcript(rec_id, t)
        analysis = service.store.analysis(rec_id)
        if analysis:
            analysis["stale"] = True
            service.store.save_analysis(rec_id, analysis)
        index.index(service.store, rec_id)
        return seg.model_dump()

    @app.delete("/api/recordings/{rec_id}", dependencies=[api], status_code=204)
    def delete_recording(rec_id: str):
        if jobs.current == rec_id:
            raise AppError("La registrazione è in elaborazione: attendi che finisca prima di eliminarla.")
        service.store.delete(rec_id)
        index.remove(rec_id)

    @app.get("/api/recordings/{rec_id}/audio", dependencies=[api])
    def audio(rec_id: str):
        # FileResponse gestisce le richieste "Range": il player può saltare a qualsiasi punto
        return FileResponse(service.store.audio_path(rec_id))

    # --- elaborazioni ---

    @app.post("/api/recordings/{rec_id}/transcribe", dependencies=[api], status_code=202)
    def transcribe(rec_id: str, body: TranscribeIn = TranscribeIn()):
        cache = service.store.analysis(rec_id)
        if body.force and cache.get("summaries"):
            # ritrascrizione: poi si rifà anche l'analisi, con lo stesso motore e template di prima
            jobs.submit(rec_id, "process", force=True, speakers=body.speakers or None,
                        provider=cache.get("provider"), template=cache.get("last_template") or "riunione")
        else:
            jobs.submit(rec_id, "transcribe", force=body.force, speakers=body.speakers or None)
        return summary_of(service.store.meta(rec_id))

    @app.post("/api/recordings/{rec_id}/analyze", dependencies=[api], status_code=202)
    def analyze(rec_id: str, body: AnalyzeIn):
        service.templates.get(body.template)
        if body.force:
            # rianalisi completa (es. dopo aver corretto la trascrizione)
            service.store.save_analysis(rec_id, {})
        jobs.submit(rec_id, "analyze", template=body.template, provider=body.provider)
        return summary_of(service.store.meta(rec_id))

    @app.post("/api/recordings/{rec_id}/summary", dependencies=[api], status_code=202)
    def summary(rec_id: str, body: AnalyzeIn):
        service.templates.get(body.template)
        jobs.submit(rec_id, "summary", template=body.template, provider=body.provider, force=body.force)
        return summary_of(service.store.meta(rec_id))

    @app.post("/api/recordings/{rec_id}/ask", dependencies=[api])
    def ask(rec_id: str, body: AskIn):
        if not body.question.strip():
            raise AppError("Scrivi una domanda.")
        analyzer = service.analyzer(rec_id, body.provider)
        history = [{"role": h["role"], "content": h["content"]} for h in body.history
                   if h.get("role") in ("user", "assistant") and h.get("content")]
        return analyzer.ask(body.question.strip(), history)

    @app.get("/api/recordings/{rec_id}/export", dependencies=[api])
    def export(rec_id: str, format: str = "md", template: Optional[str] = None, transcript: bool = True):
        meta = service.store.meta(rec_id)
        md = to_markdown(meta, service.store.transcript(rec_id), service.store.analysis(rec_id), template,
                         include_transcript=transcript)
        from urllib.parse import quote

        from .export_docs import to_docx, to_pdf

        formats = {
            "md": (lambda: md.encode("utf-8"), "text/markdown; charset=utf-8"),
            "docx": (lambda: to_docx(md),
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "pdf": (lambda: to_pdf(md), "application/pdf"),
        }
        if format not in formats:
            raise AppError("Formato non supportato: usa md, docx o pdf.")
        render, media_type = formats[format]
        ascii_name = "".join(c if c.isascii() and (c.isalnum() or c in " -_") else "_" for c in meta.title)
        disposition = (f'attachment; filename="{ascii_name.strip() or rec_id}.{format}"; '
                       f"filename*=UTF-8''{quote(meta.title + '.' + format)}")
        return Response(render(), media_type=media_type, headers={"Content-Disposition": disposition})

    # --- template e motori ---

    @app.get("/api/templates", dependencies=[api])
    def templates():
        return [t.model_dump() for t in service.templates.list()]

    @app.post("/api/templates", dependencies=[api], status_code=201)
    def new_template(body: TemplateIn):
        if len(body.description.strip()) < 10:
            raise AppError("Descrivi il template con qualche parola in più.")
        return create_template(service.llm_for(body.provider), service.templates, body.description.strip()).model_dump()

    @app.delete("/api/templates/{template_id}", dependencies=[api], status_code=204)
    def delete_template(template_id: str):
        if service.templates.get(template_id).builtin:
            raise AppError("I template predefiniti non si possono eliminare.")
        service.templates.delete(template_id)

    @app.get("/api/providers", dependencies=[api])
    def providers():
        return provider_status(settings)

    @app.get("/api/info", dependencies=[api])
    def info(request: Request):
        # indirizzo da aprire sul telefono: cambia se cambi rete Wi-Fi, per questo si calcola ogni volta
        port = request.url.port or 80
        return {"lan_url": f"http://{_lan_address()}:{port}"}

    @app.get("/api/health")
    def health():
        return {"ok": True}

    if WEB_DIST.exists():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    return app


def provider_status(settings: Settings) -> list[dict]:
    def ollama_ok() -> tuple[bool, str]:
        try:
            with urllib.request.urlopen(f"{settings.ollama_url.rstrip('/')}/api/tags", timeout=2) as r:
                models = [m["name"] for m in json.loads(r.read()).get("models", [])]
        except Exception:  # noqa: BLE001
            return False, "Ollama non è avviato"
        if not any(m.split(":")[0] == settings.ollama_model.split(":")[0] for m in models):
            return False, f"Modello mancante: esegui 'ollama pull {settings.ollama_model}'"
        return True, ""

    ok, reason = ollama_ok()
    return [
        {"id": "ollama", "label": "Locale (Ollama)", "description": "Gratis, lento, adatto ai dati sensibili",
         "sensitive_ok": True, "available": ok, "reason": reason},
        {"id": "gemini", "label": "Gemini", "description": "Gratis e veloce, solo dati NON sensibili",
         "sensitive_ok": False, "available": bool(settings.gemini_api_key),
         "reason": "" if settings.gemini_api_key else "Manca GEMINI_API_KEY nel file .env"},
        {"id": "claude", "label": "Claude", "description": "A pagamento, qualità migliore",
         "sensitive_ok": False, "available": bool(os.getenv("ANTHROPIC_API_KEY")),
         "reason": "" if os.getenv("ANTHROPIC_API_KEY") else "Manca ANTHROPIC_API_KEY nel file .env"},
    ]


def _lan_address() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def main() -> None:
    import uvicorn

    settings = get_settings()
    hidden = sys.stdout is None
    if hidden:  # avvio nascosto (pythonw): niente console, si scrive su un file di log
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        log_file = open(settings.data_dir / "server.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log_file
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    if _already_running(port):
        print(f"L'app è già accesa: apri http://localhost:{port}")
        return
    print(f"\nApri nel browser:  http://localhost:{port}")
    if host == "0.0.0.0":
        print(f"Dal telefono (stessa rete Wi-Fi):  http://{_lan_address()}:{port}")
        if not os.getenv("APP_PASSWORD"):
            print("Consiglio: imposta APP_PASSWORD nel file .env per proteggere l'accesso dalla rete.")
    if not hidden:
        print("Lascia aperta questa finestra: chiudendola l'app si spegne.\n")
    uvicorn.run(create_app(settings), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
