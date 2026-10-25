"""Template di riassunto: quelli predefiniti e quelli creati dall'utente descrivendoli a parole."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from pydantic import BaseModel

from ..errors import NotFoundError


class Template(BaseModel):
    id: str
    name: str
    description: str
    instructions: str
    builtin: bool = False


BUILTIN: list[Template] = [
    Template(
        id="riunione", name="Riunione", builtin=True,
        description="Contesto, punti discussi, decisioni e prossimi passi",
        instructions=(
            "Struttura il riassunto con queste sezioni:\n"
            "## Contesto (2-3 frasi: scopo della riunione e partecipanti)\n"
            "## Punti discussi (un sottotitolo ### per ogni tema, con le posizioni emerse)\n"
            "## Decisioni prese\n"
            "## Prossimi passi (chi fa cosa ed entro quando)\n"
            "## Questioni aperte"
        ),
    ),
    Template(
        id="intervista", name="Intervista", builtin=True,
        description="Profilo dell'intervistato, temi, citazioni significative",
        instructions=(
            "Struttura il riassunto con queste sezioni:\n"
            "## Chi è l'intervistato e contesto dell'intervista\n"
            "## Temi principali (### per ogni tema, con le risposte essenziali)\n"
            "## Citazioni significative (testuali, tra virgolette)\n"
            "## Spunti e approfondimenti possibili"
        ),
    ),
    Template(
        id="lezione", name="Lezione", builtin=True,
        description="Appunti di studio: concetti, definizioni, esempi, domande di ripasso",
        instructions=(
            "Scrivi appunti di studio chiari e completi:\n"
            "## Argomento e obiettivi della lezione\n"
            "## Concetti chiave (### per concetto, spiegato in modo autonomo)\n"
            "## Definizioni e formule\n"
            "## Esempi fatti dal docente\n"
            "## Indicazioni pratiche (compiti, esame, materiali citati)\n"
            "## Domande di ripasso (5-8 domande)"
        ),
    ),
    Template(
        id="vendita", name="Chiamata commerciale", builtin=True,
        description="Esigenze del cliente, obiezioni, offerta, prossimi passi",
        instructions=(
            "Struttura il riassunto con queste sezioni:\n"
            "## Cliente e contesto\n"
            "## Esigenze e problemi espressi\n"
            "## Soluzioni e offerta presentate (prezzi e condizioni se citati)\n"
            "## Obiezioni e risposte\n"
            "## Livello di interesse e segnali d'acquisto\n"
            "## Prossimi passi concordati"
        ),
    ),
]


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "template"


class TemplateStore:
    def __init__(self, path: Path):
        self.path = path

    def _custom(self) -> list[Template]:
        if not self.path.exists():
            return []
        return [Template(**t) for t in json.loads(self.path.read_text(encoding="utf-8"))]

    def list(self) -> list[Template]:
        return BUILTIN + self._custom()

    def get(self, template_id: str) -> Template:
        for t in self.list():
            if t.id == template_id:
                return t
        raise NotFoundError(f"Template '{template_id}' non trovato. Disponibili: "
                            + ", ".join(t.id for t in self.list()))

    def save(self, template: Template) -> Template:
        custom = self._custom()
        existing = {t.id for t in self.list()}
        base, n = template.id, 2
        while template.id in existing:
            template.id = f"{base}-{n}"
            n += 1
        custom.append(template)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([t.model_dump() for t in custom], ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return template

    def delete(self, template_id: str) -> None:
        custom = [t for t in self._custom() if t.id != template_id]
        self.path.write_text(json.dumps([t.model_dump() for t in custom], ensure_ascii=False, indent=2),
                             encoding="utf-8")
