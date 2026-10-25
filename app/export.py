"""Export di una registrazione in Markdown (Word e PDF arriveranno nella tappa 4)."""

from __future__ import annotations

from .models import Transcript, format_ts
from .storage import RecordingMeta


def _ts(item: dict) -> str:
    return f" _({item['timestamp']})_" if item.get("timestamp") else ""


def to_markdown(meta: RecordingMeta, transcript: Transcript, analysis: dict,
                template_id: str | None = None, include_transcript: bool = True) -> str:
    out = [f"# {meta.title}", "",
           f"Data: {meta.created_at[:10]} · Durata: {format_ts(meta.duration)} · File: {meta.original_filename}", ""]

    summaries = analysis.get("summaries", {})
    template_id = template_id or analysis.get("last_template") or next(iter(summaries), None)
    if template_id and template_id in summaries:
        s = summaries[template_id]
        out += [f"## Riassunto ({s['template_name']})", "", s["markdown"].replace("\n## ", "\n### "), ""]

    kw = analysis.get("keywords")
    if kw:
        out += ["## Keywords", "", ", ".join(kw["keywords"]), "", "## Argomenti principali", ""]
        for t in kw["topics"]:
            when = ", ".join(r["timestamp"] for r in t["refs"][:3])
            out.append(f"- **{t['title']}**: {t['description']}" + (f" _({when})_" if when else ""))
        out.append("")

    ex = analysis.get("extraction")
    if ex:
        sections = [
            ("Decisioni", ex["decisions"], lambda i: i["text"]),
            ("Azioni da fare", ex["action_items"], lambda i: i["task"]
             + (f" — **{i['owner']}**" if i.get("owner") else "")
             + (f" — entro {i['due_date']}" if i.get("due_date") else "")),
            ("Persone", ex["people"], lambda i: i["name"] + (f" ({i['role']})" if i.get("role") else "")),
            ("Date", ex["dates"], lambda i: f"{i['text']}: {i['context']}"),
            ("Cifre", ex["figures"], lambda i: f"{i['value']}: {i['context']}"),
            ("Domande aperte", ex["open_questions"], lambda i: i["question"]),
        ]
        for title, items, fmt in sections:
            if items:
                out += [f"## {title}", ""] + [f"- {fmt(i)}{_ts(i)}" for i in items] + [""]

    if include_transcript:
        out += ["## Trascrizione", ""]
        last = None
        for seg in transcript.segments:
            who = transcript.speaker_label(seg.speaker)
            if who and who != last:
                out += ["", f"**{who}** [{format_ts(seg.start)}]"]
                last = who
                out.append(seg.text)
            else:
                out.append(f"[{format_ts(seg.start)}] {seg.text}" if not who else seg.text)
    return "\n".join(out).strip() + "\n"
