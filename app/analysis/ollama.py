"""Analisi con un modello locale tramite Ollama: gratuita e senza che il testo esca dal PC.

Più lenta e meno precisa di Claude, soprattutto su un portatile senza GPU dedicata.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import AnalysisError

T = TypeVar("T", bound=BaseModel)


def _flatten(messages: list[dict]) -> list[dict]:
    """Converte i messaggi in formato Claude (blocchi di testo) in testo semplice per Ollama."""
    out = []
    for m in messages:
        content = m["content"]
        if isinstance(content, list):
            content = "\n\n".join(block["text"] for block in content if block.get("type") == "text")
        out.append({"role": m["role"], "content": content})
    return out


class OllamaLLM:
    # i modelli locali hanno un contesto limitato: il resto del codice si adatta a questo valore
    context_chars = 40000

    def __init__(self, model: str = "gemma3:4b", url: str = "http://localhost:11434", num_ctx: int = 16384,
                 timeout: int = 3600):
        self.model = model
        self.url = url.rstrip("/")
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.context_chars = int(num_ctx * 2.5)

    def structured(self, system: str, messages: list[dict], schema: type[T]) -> T:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + _flatten(messages),
            "format": schema.model_json_schema(),  # output vincolato allo schema JSON
            "stream": False,
            "options": {"num_ctx": self.num_ctx, "temperature": 0.2},
        }
        req = urllib.request.Request(f"{self.url}/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        last_error = ""
        for _ in range(2):  # un secondo tentativo se il JSON non è valido
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code == 404:
                    raise AnalysisError(f"Modello '{self.model}' non presente in Ollama. Esegui: ollama pull {self.model}")
                raise AnalysisError(f"Errore di Ollama ({e.code}): {detail}")
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                raise AnalysisError(f"Ollama non risponde su {self.url}. È installato e avviato? ({e})")
            try:
                return schema.model_validate_json(data["message"]["content"])
            except (ValidationError, KeyError) as e:
                last_error = str(e)[:200]
        raise AnalysisError(f"Il modello locale ha restituito dati non validi: {last_error}")
