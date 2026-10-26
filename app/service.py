"""Flusso completo di una registrazione: conversione → trascrizione → interlocutori → analisi.

Usato sia dalla riga di comando sia (nella tappa 2) dal server web in background.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable, Optional

from . import audio
from .analysis.llm import LLM, ClaudeLLM
from .analysis.pipeline import Analyzer
from .analysis.templates import TemplateStore
from .config import Settings
from .errors import AppError
from .models import Transcript
from .storage import RecordingStore
from .stt import assign_speakers, get_diarizer, get_engine

ProgressFn = Callable[[float, str], None]


class Service:
    def __init__(self, settings: Settings, llm: Optional[LLM] = None):
        self.settings = settings
        self.store = RecordingStore(settings.recordings_dir)
        self.templates = TemplateStore(settings.templates_file)
        self._llm = llm

    def llm_for(self, provider: Optional[str] = None) -> LLM:
        if self._llm is not None:
            return self._llm
        provider = provider or self.settings.llm_provider
        if provider == "claude":
            return ClaudeLLM(self.settings.claude_model, self.settings.claude_effort)
        if provider == "ollama":
            from .analysis.ollama import OllamaLLM

            return OllamaLLM(self.settings.ollama_model, self.settings.ollama_url, self.settings.ollama_num_ctx)
        if provider == "gemini":
            from .analysis.gemini import GeminiLLM

            return GeminiLLM(self.settings.gemini_model, self.settings.gemini_api_key)
        raise AppError(f"Motore di analisi sconosciuto: '{provider}' (usa ollama, gemini oppure claude)")

    @property
    def llm(self) -> LLM:
        return self.llm_for()

    def _progress(self, rec_id: str, status: str, progress: Optional[ProgressFn]) -> ProgressFn:
        def report(fraction: float, message: str) -> None:
            self.store.update_meta(rec_id, status=status, progress=round(fraction, 3), progress_message=message)
            if progress:
                progress(fraction, message)
        return report

    def import_audio(self, path: Path, title: Optional[str] = None) -> str:
        audio.check_file(path)
        meta = self.store.create(path, title)
        try:
            # si misura la copia in archivio: se va sistemata (webm del browser) l'originale resta intatto
            duration = audio.probe_duration(self.store.audio_path(meta.id))
        except Exception:
            self.store.delete(meta.id)
            raise
        self.store.update_meta(meta.id, duration=duration)
        return meta.id

    def transcribe(self, rec_id: str, progress: Optional[ProgressFn] = None, force: bool = False,
                   speakers: Optional[int] = None) -> Transcript:
        """speakers: quante persone parlano, se noto (migliora molto il riconoscimento)."""
        if self.store.has_transcript(rec_id) and not force:
            return self.store.transcript(rec_id)  # si trascrive una sola volta
        report = self._progress(rec_id, "trascrizione", progress)
        meta = self.store.meta(rec_id)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                report(0.0, "Conversione audio")
                wav = audio.to_wav16k(self.store.audio_path(rec_id), Path(tmp) / "audio16k.wav")
                engine = get_engine(self.settings)
                diarizer = get_diarizer(self.settings, speakers)
                share = 0.8 if diarizer else 1.0
                transcript = engine.transcribe(wav, meta.duration, lambda f, m: report(share * f, m))
                if not transcript.segments:
                    raise AppError("Nessun parlato riconosciuto nel file audio.")
                if diarizer:
                    turns = diarizer.diarize(wav, lambda f, m: report(0.8 + 0.2 * f, m))
                    transcript = assign_speakers(transcript, turns)
            if force and self.store.has_transcript(rec_id):
                # testo nuovo: l'analisi va rifatta, si tiene solo il motore scelto
                old = self.store.analysis(rec_id)
                self.store.save_analysis(rec_id, {"provider": old["provider"]} if old.get("provider") else {})
            self.store.save_transcript(rec_id, transcript)
            self.store.update_meta(rec_id, status="trascritta", progress=1.0, progress_message="Trascrizione salvata",
                                   error=None)
            return transcript
        except AppError as e:
            self.store.update_meta(rec_id, status="errore", error=str(e))
            raise

    def analyzer(self, rec_id: str, provider: Optional[str] = None) -> Analyzer:
        cache = self.store.analysis(rec_id)
        # di default si continua con il motore usato la prima volta per questa registrazione
        provider = provider or cache.get("provider") or self.settings.llm_provider
        if cache.get("provider") and cache["provider"] != provider:
            cache = {}  # cambio di motore: si rifà l'analisi da zero
        local = provider == "ollama"
        analyzer = Analyzer(self.llm_for(provider), self.store.transcript(rec_id), cache,
                            self.settings.ollama_chunk_chars if local else self.settings.chunk_chars,
                            # Ollama lavora una richiesta alla volta; la quota gratuita di Gemini ha pochi RPM
                            self.settings.analysis_workers if provider == "claude" else 1)
        analyzer.cache["provider"] = provider
        return analyzer

    def analyze(self, rec_id: str, template_id: str = "riunione", progress: Optional[ProgressFn] = None,
                provider: Optional[str] = None) -> dict:
        template = self.templates.get(template_id)
        analyzer = self.analyzer(rec_id, provider)
        report = self._progress(rec_id, "analisi", progress)
        try:
            analyzer.run_all(template, report, save=lambda cache: self.store.save_analysis(rec_id, cache))
        except AppError as e:
            self.store.update_meta(rec_id, status="errore", error=str(e))
            raise
        title = analyzer.cache["summaries"][template.id]["title"]
        meta = self.store.meta(rec_id)
        # il titolo generato sostituisce il nome del file, a meno che l'utente ne abbia dato uno
        new_title = title if meta.title == Path(meta.original_filename).stem else meta.title
        self.store.update_meta(rec_id, status="pronta", title=new_title, error=None)
        return analyzer.cache

    def summary(self, rec_id: str, template_id: str, provider: Optional[str] = None, force: bool = False,
                progress: Optional[ProgressFn] = None) -> dict:
        """Riassunto (e mappa mentale) con un altro template: riusa gli appunti dei blocchi già calcolati."""
        template = self.templates.get(template_id)
        analyzer = self.analyzer(rec_id, provider)
        report = self._progress(rec_id, "analisi", progress)
        try:
            analyzer.notes(lambda f, m: report(0.7 * f, m))
            self.store.save_analysis(rec_id, analyzer.cache)
            report(0.7, f"Riassunto {template.name}")
            result = analyzer.summary(template, force=force)
            self.store.save_analysis(rec_id, analyzer.cache)
            report(0.9, "Mappa mentale")
            analyzer.mindmap(template, force=force)
            analyzer.cache["last_template"] = template.id
            self.store.save_analysis(rec_id, analyzer.cache)
        except AppError as e:
            self.store.update_meta(rec_id, status="errore", error=str(e))
            raise
        self.store.update_meta(rec_id, status="pronta", progress=1.0, error=None)
        return result

    def process(self, path: Path, title: Optional[str] = None, template_id: str = "riunione",
                progress: Optional[ProgressFn] = None, provider: Optional[str] = None) -> str:
        self.templates.get(template_id)  # verifica subito che il template esista
        rec_id = self.import_audio(path, title)
        self.transcribe(rec_id, progress)
        self.analyze(rec_id, template_id, progress, provider)
        return rec_id
