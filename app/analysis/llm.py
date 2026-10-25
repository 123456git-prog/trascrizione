"""Client per l'API di Claude. È l'unico punto che parla con l'API: la chiave resta lato server."""

from __future__ import annotations

import os
from typing import Optional, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import AnalysisError

T = TypeVar("T", bound=BaseModel)


def user_message(text: str, context: Optional[str] = None) -> dict:
    """Messaggio utente; `context` (testo lungo e stabile, es. la trascrizione) viene messo in cache."""
    content: list[dict] = []
    if context:
        content.append({"type": "text", "text": context, "cache_control": {"type": "ephemeral"}})
    content.append({"type": "text", "text": text})
    return {"role": "user", "content": content}


class LLM(Protocol):
    def structured(self, system: str, messages: list[dict], schema: type[T]) -> T:
        """Restituisce un oggetto validato secondo `schema`."""
        ...


class ClaudeLLM:
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium", api_key: Optional[str] = None):
        try:
            import anthropic
        except ImportError:
            raise AnalysisError("Il pacchetto 'anthropic' non è installato: pip install -r requirements.txt")
        self._anthropic = anthropic
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise AnalysisError(
                "Manca ANTHROPIC_API_KEY. Creala su console.anthropic.com e inseriscila nel file .env."
            )
        self.client = anthropic.Anthropic(api_key=key, max_retries=4, timeout=600)
        self.model = model
        self.effort = effort

    def structured(self, system: str, messages: list[dict], schema: type[T]) -> T:
        a = self._anthropic
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=32000,
                system=system,
                messages=messages,
                thinking={"type": "adaptive"},
                # output strutturato: la risposta è JSON conforme allo schema
                output_config={"effort": self.effort,
                                "format": {"type": "json_schema", "schema": a.transform_schema(schema)}},
                # se un filtro di sicurezza blocca per errore la richiesta, l'API riprova su un altro modello
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                message = stream.get_final_message()
        except a.AuthenticationError:
            raise AnalysisError("Chiave API di Claude non valida. Controlla ANTHROPIC_API_KEY nel file .env.")
        except a.PermissionDeniedError:
            raise AnalysisError("La chiave API non ha i permessi necessari (o il credito è esaurito).")
        except a.RateLimitError:
            raise AnalysisError("Troppe richieste a Claude in poco tempo. Riprova tra qualche minuto.")
        except a.BadRequestError as e:
            raise AnalysisError(f"Richiesta rifiutata dall'API di Claude: {e.message}")
        except a.APIStatusError as e:
            raise AnalysisError(f"Errore dell'API di Claude ({e.status_code}). Riprova più tardi.")
        except a.APIConnectionError:
            raise AnalysisError("Impossibile raggiungere l'API di Claude. Controlla la connessione a internet.")

        if message.stop_reason == "refusal":
            raise AnalysisError("Claude ha rifiutato di elaborare questo contenuto.")
        if message.stop_reason == "max_tokens":
            raise AnalysisError("La risposta di Claude è stata troncata. Prova a ridurre CHUNK_CHARS.")
        text = "".join(block.text for block in message.content if block.type == "text")
        try:
            return schema.model_validate_json(text)
        except ValidationError:
            raise AnalysisError("Claude ha restituito una risposta non valida. Riprova.")
