"""Analisi del testo: riassunto a blocchi, keywords, estrazione strutturata, mappa mentale, chat."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from ..models import (ChatAnswer, ChunkNotes, ExtractionOut, KeywordsOut, MindMapOut, Segment,
                      SummaryOut, TemplateOut, Transcript, format_ts)
from . import prompts
from .chunking import chunk_segments
from .llm import LLM, user_message
from .templates import Template, TemplateStore, slugify

ProgressFn = Callable[[float, str], None]


def _noop(fraction: float, message: str) -> None:
    pass


class Analyzer:
    """Lavora su una trascrizione; `cache` è il dizionario salvato in analysis.json."""

    def __init__(self, llm: LLM, transcript: Transcript, cache: Optional[dict] = None,
                 chunk_chars: int = 40000, workers: int = 3):
        self.llm = llm
        self.t = transcript
        self.cache = cache if cache is not None else {}
        self.chunks = chunk_segments(transcript, chunk_chars)
        self.workers = max(1, workers)

    # --- utilità ---

    def _map(self, fn, items):
        if self.workers == 1 or len(items) == 1:
            return [fn(i) for i in items]
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(fn, items))

    def _ref(self, segment_id: Optional[int]) -> dict:
        """Collega un elemento al punto d'origine: timestamp e interlocutore presi dalla trascrizione."""
        seg = self.t.segment(segment_id) if segment_id is not None else None
        if seg is None:
            return {"segment_id": None, "start": None, "timestamp": None, "speaker": None}
        return {"segment_id": seg.id, "start": seg.start, "timestamp": format_ts(seg.start),
                "speaker": self.t.speaker_label(seg.speaker) or None}

    def _resolve(self, item: dict, chunk: Optional[list[Segment]] = None) -> dict:
        sid = item.get("segment_id")
        if chunk and sid is not None and not (chunk[0].id <= sid <= chunk[-1].id):
            sid = None  # id fuori dal blocco: non affidabile
        return {**item, **self._ref(sid)}

    # --- 1. appunti per blocco (map) ---

    def notes(self, progress: ProgressFn = _noop) -> list[dict]:
        if self.cache.get("chunks") and len(self.cache["chunks"]) == len(self.chunks):
            return self.cache["chunks"]
        total = len(self.chunks)
        done = 0

        def run(indexed):
            nonlocal done
            index, chunk = indexed
            out = self.llm.structured(
                prompts.BASE_SYSTEM,
                [user_message(prompts.CHUNK_NOTES.format(index=index + 1, total=total),
                              context=self.t.render(chunk))],
                ChunkNotes,
            )
            done += 1
            progress(done / total, f"Appunti blocco {done} di {total}")
            return {
                "index": index, "start": chunk[0].start, "end": chunk[-1].end,
                "summary": out.summary,
                "key_points": [self._resolve(kp.model_dump(), chunk) for kp in out.key_points],
            }

        self.cache["chunks"] = self._map(run, list(enumerate(self.chunks)))
        return self.cache["chunks"]

    def _notes_text(self) -> str:
        parts = []
        for c in self.notes():
            points = "\n".join(f"- [#{kp['segment_id']}] {kp['text']}" if kp["segment_id"] is not None
                               else f"- {kp['text']}" for kp in c["key_points"])
            parts.append(f"## Blocco {c['index'] + 1} ({format_ts(c['start'])} - {format_ts(c['end'])})\n"
                         f"{c['summary']}\n\nPunti chiave:\n{points}")
        return "\n\n".join(parts)

    # --- 2. riassunto finale (reduce) ---

    def summary(self, template: Template, force: bool = False) -> dict:
        summaries = self.cache.setdefault("summaries", {})
        if template.id in summaries and not force:
            return summaries[template.id]
        out = self.llm.structured(
            prompts.BASE_SYSTEM,
            [user_message(prompts.FINAL_SUMMARY.format(duration=format_ts(self.t.duration), name=template.name,
                                                       instructions=template.instructions),
                          context=self._notes_text())],
            SummaryOut,
        )
        summaries[template.id] = {"template": template.id, "template_name": template.name,
                                  "title": out.title, "markdown": out.markdown}
        self.cache["last_template"] = template.id
        return summaries[template.id]

    # --- 3. keywords e argomenti ---

    def keywords(self, force: bool = False) -> dict:
        if "keywords" in self.cache and not force:
            return self.cache["keywords"]
        out = self.llm.structured(prompts.BASE_SYSTEM,
                                  [user_message(prompts.KEYWORDS, context=self._notes_text())], KeywordsOut)
        topics = []
        for topic in out.topics:
            refs = [self._ref(sid) for sid in topic.segment_ids]
            refs = sorted((r for r in refs if r["segment_id"] is not None), key=lambda r: r["start"])
            topics.append({"title": topic.title, "description": topic.description, "refs": refs})
        self.cache["keywords"] = {"keywords": out.keywords, "topics": topics}
        return self.cache["keywords"]

    # --- 4. estrazione strutturata, per blocco ---

    def extraction(self, progress: ProgressFn = _noop, force: bool = False) -> dict:
        if "extraction" in self.cache and not force:
            return self.cache["extraction"]
        total = len(self.chunks)
        done = 0

        def run(chunk):
            nonlocal done
            out = self.llm.structured(prompts.BASE_SYSTEM,
                                      [user_message(prompts.EXTRACTION, context=self.t.render(chunk))],
                                      ExtractionOut)
            done += 1
            progress(done / total, f"Estrazione blocco {done} di {total}")
            return chunk, out

        merged: dict[str, list[dict]] = {k: [] for k in ExtractionOut.model_fields}
        for chunk, out in self._map(run, self.chunks):
            for key in merged:
                merged[key].extend(self._resolve(item.model_dump(), chunk) for item in getattr(out, key))
        merged["people"] = _dedupe_people(merged["people"])
        self.cache["extraction"] = merged
        return merged

    # --- 5. mappa mentale dal riassunto ---

    def mindmap(self, template: Template, force: bool = False) -> str:
        maps = self.cache.setdefault("mindmaps", {})
        if template.id in maps and not force:
            return maps[template.id]
        summary = self.summary(template)
        out = self.llm.structured(
            prompts.BASE_SYSTEM,
            [user_message(prompts.MINDMAP, context=f"# {summary['title']}\n\n{summary['markdown']}")],
            MindMapOut,
        )
        maps[template.id] = out.markdown
        return out.markdown

    # --- 6. chiedi alla registrazione ---

    def _chat_context(self, question: str) -> tuple[str, bool]:
        """Trascrizione intera se ci sta nel contesto del modello, altrimenti i passaggi più pertinenti."""
        full = self.t.render()
        limit = getattr(self.llm, "context_chars", None)
        if not limit or len(full) <= limit:
            return "TRASCRIZIONE COMPLETA:\n" + full, True
        words = {w for w in re.findall(r"\w+", question.lower()) if len(w) > 3}
        window = max(1, len(self.t.segments) * (limit // 8) // max(len(full), 1))
        scored = []
        for i in range(0, len(self.t.segments), window):
            segs = self.t.segments[i:i + window]
            text = " ".join(s.text.lower() for s in segs)
            scored.append((sum(text.count(w) for w in words), i, segs))
        picked, size = [], 0
        for score, i, segs in sorted(scored, key=lambda x: -x[0]):
            chunk = self.t.render(segs)
            if size + len(chunk) > limit:
                continue
            picked.append((i, chunk))
            size += len(chunk)
        text = "\n...\n".join(chunk for _, chunk in sorted(picked))
        return "PASSAGGI PERTINENTI DELLA TRASCRIZIONE:\n" + text, False

    def ask(self, question: str, history: Optional[list[dict]] = None) -> dict:
        """`history`: lista di {"role": "user"|"assistant", "content": str} dei turni precedenti."""
        history = history or []
        context, full = self._chat_context(question)
        messages: list[dict] = []
        for i, turn in enumerate(history):
            if i == 0 and full:
                # trascrizione nel primo messaggio: il prefisso resta identico e la cache funziona
                messages.append(user_message(turn["content"], context=context))
            else:
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append(user_message(question, context=context if not (history and full) else None))
        out = self.llm.structured(prompts.CHAT_SYSTEM, messages, ChatAnswer)
        cited = sorted({int(m) for m in re.findall(r"\[#(\d+)\]", out.answer)} | set(out.citations))
        refs = [r for r in (self._ref(sid) for sid in cited) if r["segment_id"] is not None]
        for r in refs:
            r["text"] = self.t.segment(r["segment_id"]).text
        return {"answer": out.answer, "citations": refs}

    def run_all(self, template: Template, progress: ProgressFn = _noop,
                save: Callable[[dict], None] = lambda cache: None) -> None:
        """Analisi completa. Dopo ogni passo la cache viene salvata: se qualcosa fallisce,
        rilanciando si riparte dal punto in cui ci si era fermati senza ripagare i passi già fatti."""
        steps = [
            (0.05, 0.45, "Appunti per blocco", lambda p: self.notes(p)),
            (0.50, 0.10, "Riassunto finale", lambda p: self.summary(template)),
            (0.60, 0.05, "Keywords e argomenti", lambda p: self.keywords()),
            (0.65, 0.25, "Estrazione strutturata", lambda p: self.extraction(p)),
            (0.90, 0.10, "Mappa mentale", lambda p: self.mindmap(template)),
        ]
        for start, span, label, step in steps:
            progress(start, label)
            step(lambda f, m, start=start, span=span: progress(start + span * f, m))
            save(self.cache)
        progress(1.0, "Analisi completata")


def _dedupe_people(people: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for p in people:
        key = p["name"].strip().lower()
        if key not in seen:
            seen[key] = p
        elif not seen[key].get("role") and p.get("role"):
            seen[key] = {**seen[key], "role": p["role"]}
    return list(seen.values())


def create_template(llm: LLM, store: TemplateStore, description: str) -> Template:
    out = llm.structured(prompts.BASE_SYSTEM,
                         [user_message(prompts.CUSTOM_TEMPLATE.format(description=description))], TemplateOut)
    return store.save(Template(id=slugify(out.name), name=out.name, description=out.description,
                               instructions=out.instructions))
