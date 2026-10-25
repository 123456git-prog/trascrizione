"""Analisi con Gemini (Google) usando la quota gratuita dell'API.

Da usare solo per registrazioni NON sensibili: il testo viene inviato ai server di Google.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import AnalysisError
from .schema import inline_schema

T = TypeVar("T", bound=BaseModel)



def _text_of(content) -> str:
    if isinstance(content, list):
        return "\n\n".join(block["text"] for block in content if block.get("type") == "text")
    return content


class GeminiLLM:
    def __init__(self, model: str = "gemini-3.8-flash", api_key: str = "", timeout: int = 600,
                 max_retries: int = 5, retry_delay: float = 15.0,
                 base_url: str = "https://generativelanguage.googleapis.com"):
        if not api_key:
            raise AnalysisError(
                "Manca GEMINI_API_KEY. Creala gratis su aistudio.google.com (Get API key) e inseriscila nel file .env."
            )
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.base_url = base_url.rstrip("/")

    def structured(self, system: str, messages: list[dict], schema: type[T]) -> T:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "model" if m["role"] == "assistant" else "user",
                          "parts": [{"text": _text_of(m["content"])}]} for m in messages],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": inline_schema(schema),
            },
        }
        data = self._post(body)
        try:
            candidate = data["candidates"][0]
        except (KeyError, IndexError):
            reason = data.get("promptFeedback", {}).get("blockReason", "risposta vuota")
            raise AnalysisError(f"Gemini non ha prodotto una risposta ({reason}).")
        if candidate.get("finishReason") == "MAX_TOKENS":
            raise AnalysisError("La risposta di Gemini è stata troncata. Prova a ridurre CHUNK_CHARS.")
        text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", [])
                       if not p.get("thought"))
        try:
            return schema.model_validate_json(text)
        except ValidationError:
            raise AnalysisError(f"Gemini ha restituito dati non validi (motivo: {candidate.get('finishReason')}).")

    def _post(self, body: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}/v1beta/models/{self.model}:generateContent", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        delay = self.retry_delay
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")
                if e.code in (429, 500, 503) and attempt < self.max_retries:
                    # la quota gratuita ha un limite di richieste al minuto: si aspetta e si riprova
                    time.sleep(delay)
                    delay = min(delay * 2, 120)
                    continue
                if e.code == 429:
                    raise AnalysisError("Quota gratuita di Gemini esaurita per ora. Riprova più tardi o domani.")
                if e.code in (400, 403) and "API key" in detail:
                    raise AnalysisError("Chiave Gemini non valida. Controlla GEMINI_API_KEY nel file .env.")
                if e.code == 404:
                    raise AnalysisError(f"Modello Gemini '{self.model}' non trovato. Controlla GEMINI_MODEL.")
                raise AnalysisError(f"Errore di Gemini ({e.code}): {detail[:300]}")
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay / 3)
                    continue
                raise AnalysisError(f"Impossibile raggiungere Gemini. Controlla la connessione ({e}).")
        raise AnalysisError("Gemini non risponde.")
