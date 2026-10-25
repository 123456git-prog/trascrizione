"""Schemi JSON semplificati per i modelli che non gestiscono bene $ref/$defs (Gemini, Ollama)."""

from __future__ import annotations

from pydantic import BaseModel


def inline_schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            # "title" come metadato (stringa) si toglie; come nome di campo (dict) resta
            return {k: resolve(v) for k, v in node.items() if not (k == "title" and isinstance(v, str))}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)
