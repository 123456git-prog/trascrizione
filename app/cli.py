"""Prototipo da riga di comando.

Esempi:
    python -m app.cli process riunione.m4a --template riunione
    python -m app.cli list
    python -m app.cli show <id>
    python -m app.cli ask <id> "Chi deve preparare il preventivo?"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import get_settings
from .errors import AppError
from .export import to_markdown
from .models import format_ts
from .service import Service

CONSENT_NOTICE = (
    "Promemoria: registra e trascrivi solo con il consenso delle persone coinvolte (GDPR). Vedi README."
)


PROVIDERS = [
    ("ollama", "Locale con Ollama: gratis, lento, adatto ai dati sensibili (nulla esce dal PC)"),
    ("gemini", "Gemini in cloud: gratis e veloce, SOLO per dati non sensibili"),
    ("claude", "Claude: a pagamento, qualità migliore"),
]


def choose_provider(service: Service, args, rec_id: str | None = None) -> str:
    """Il motore di analisi si sceglie ogni volta: da --motore, da quello già usato, o chiedendo."""
    if args.motore:
        return args.motore
    if rec_id:
        previous = service.store.analysis(rec_id).get("provider")
        if previous:
            return previous
    default = service.settings.llm_provider
    if not sys.stdin.isatty():
        return default
    print("\nCon quale motore vuoi analizzare il testo?")
    for i, (key, label) in enumerate(PROVIDERS, 1):
        print(f"  {i}. {label}" + ("  [predefinito]" if key == default else ""))
    while True:
        answer = input("Scelta (invio = predefinito): ").strip()
        if not answer:
            return default
        if answer in {"1", "2", "3"}:
            return PROVIDERS[int(answer) - 1][0]
        print("Scrivi 1, 2 o 3.")


class ProgressPrinter:
    def __init__(self):
        self.last = ""
        self.started = time.monotonic()

    def __call__(self, fraction: float, message: str) -> None:
        elapsed = int(time.monotonic() - self.started)
        bar = "#" * int(fraction * 30)
        line = f"\r[{bar:<30}] {fraction * 100:5.1f}%  {message[:60]:<60} {format_ts(elapsed)}"
        if line != self.last:
            sys.stdout.write(line)
            sys.stdout.flush()
            self.last = line

    def done(self) -> None:
        sys.stdout.write("\n")


def _print_summary(service: Service, rec_id: str, template_id: str | None) -> None:
    meta = service.store.meta(rec_id)
    analysis = service.store.analysis(rec_id)
    print(to_markdown(meta, service.store.transcript(rec_id), analysis, template_id, include_transcript=False))


def cmd_process(service: Service, args) -> None:
    print(CONSENT_NOTICE)
    provider = None if args.only_transcribe else choose_provider(service, args)
    p = ProgressPrinter()
    rec_id = service.import_audio(Path(args.file), args.title)
    print(f"Registrazione creata: {rec_id}")
    try:
        service.transcribe(rec_id, p, speakers=args.persone)
        p.done()
        if args.only_transcribe:
            print(f"Trascrizione salvata. Per analizzarla: python -m app.cli analyze {rec_id}")
            return
        service.analyze(rec_id, args.template, p, provider)
        p.done()
    except AppError:
        p.done()
        print(f"Puoi riprendere da dove si è interrotto con: python -m app.cli analyze {rec_id}", file=sys.stderr)
        raise
    _print_summary(service, rec_id, args.template)


def cmd_transcribe(service: Service, args) -> None:
    rec_id = service.store.resolve_id(args.id)
    p = ProgressPrinter()
    t = service.transcribe(rec_id, p, force=args.force, speakers=args.persone)
    p.done()
    print(f"{len(t.segments)} segmenti, durata {format_ts(t.duration)}, motore {t.engine} ({t.model})")


def cmd_analyze(service: Service, args) -> None:
    rec_id = service.store.resolve_id(args.id)
    provider = choose_provider(service, args, rec_id)
    p = ProgressPrinter()
    if not service.store.has_transcript(rec_id):
        service.transcribe(rec_id, p)
        p.done()
    service.analyze(rec_id, args.template, p, provider)
    p.done()
    _print_summary(service, rec_id, args.template)


def cmd_list(service: Service, args) -> None:
    metas = service.store.list()
    if not metas:
        print("Nessuna registrazione. Inizia con: python -m app.cli process <file audio>")
    for m in metas:
        state = m.status + (f" ({m.error})" if m.status == "errore" and m.error else "")
        print(f"{m.id}  {format_ts(m.duration)}  {state:<12}  {m.title}")


def cmd_show(service: Service, args) -> None:
    rec_id = service.store.resolve_id(args.id)
    if args.what == "transcript":
        t = service.store.transcript(rec_id)
        for seg in t.segments:
            who = t.speaker_label(seg.speaker)
            print(f"[{format_ts(seg.start)}] {who + ': ' if who else ''}{seg.text}")
    elif args.what == "json":
        print(json.dumps(service.store.analysis(rec_id).get("extraction", {}), ensure_ascii=False, indent=2))
    elif args.what == "mindmap":
        maps = service.store.analysis(rec_id).get("mindmaps", {})
        print("\n\n".join(maps.values()) or "Mappa mentale non ancora generata.")
    else:
        _print_summary(service, rec_id, args.template)


def cmd_summary(service: Service, args) -> None:
    """Nuovo riassunto con un altro template: riusa gli appunti dei blocchi già calcolati."""
    rec_id = service.store.resolve_id(args.id)
    s = service.summary(rec_id, args.template, choose_provider(service, args, rec_id), force=args.force)
    print(f"# {s['title']}\n\n{s['markdown']}")


def cmd_ask(service: Service, args) -> None:
    rec_id = service.store.resolve_id(args.id)
    analyzer = service.analyzer(rec_id, choose_provider(service, args, rec_id))
    history: list[dict] = []
    question = args.question
    if not question:
        print("Chiedi alla registrazione (riga vuota per uscire).")
    while True:
        if not question:
            try:
                question = input("\nDomanda> ").strip()
            except EOFError:
                break
            if not question:
                break
        result = analyzer.ask(question, history)
        print("\n" + result["answer"])
        if result["citations"]:
            print("\nFonti:")
            for c in result["citations"]:
                print(f"  [#{c['segment_id']} {c['timestamp']}] {c['text'][:100]}")
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": result["answer"]}]
        if args.question:
            break
        question = None


def cmd_templates(service: Service, args) -> None:
    if args.action == "create":
        if not args.text:
            raise AppError('Descrivi il template, es.: templates create "riunione di condominio con spese e votazioni"')
        from .analysis.pipeline import create_template

        t = create_template(service.llm_for(choose_provider(service, args)), service.templates, " ".join(args.text))
        print(f"Creato template '{t.id}': {t.name}\n{t.description}\n\n{t.instructions}")
    elif args.action == "delete":
        service.templates.delete(args.text[0])
        print("Template eliminato.")
    else:
        for t in service.templates.list():
            print(f"{t.id:<20} {t.name:<22} {'' if t.builtin else '(personale) '}{t.description}")


def cmd_speakers(service: Service, args) -> None:
    rec_id = service.store.resolve_id(args.id)
    t = service.store.transcript(rec_id)
    if not args.names:
        speakers = sorted({s.speaker for s in t.segments if s.speaker})
        for sp in speakers:
            first = next(s for s in t.segments if s.speaker == sp)
            print(f"{sp}  →  {t.speaker_label(sp):<20} es. [{format_ts(first.start)}] {first.text[:60]}")
        return
    for pair in args.names:
        if "=" not in pair:
            raise AppError("Usa il formato SPEAKER_00=Marco")
        key, name = pair.split("=", 1)
        t.speaker_names[key.strip()] = name.strip()
    service.store.save_transcript(rec_id, t)
    print("Nomi salvati. Rilancia 'analyze' per usarli nelle analisi successive.")


def cmd_export(service: Service, args) -> None:
    from .export_docs import to_docx, to_pdf

    rec_id = service.store.resolve_id(args.id)
    md = to_markdown(service.store.meta(rec_id), service.store.transcript(rec_id), service.store.analysis(rec_id),
                     args.template, include_transcript=not args.no_transcript)
    out = Path(args.output or f"{rec_id}.{args.format}")
    fmt = out.suffix.lstrip(".").lower() if args.output else args.format
    if fmt == "md":
        out.write_text(md, encoding="utf-8")
    elif fmt == "docx":
        out.write_bytes(to_docx(md))
    elif fmt == "pdf":
        out.write_bytes(to_pdf(md))
    else:
        raise AppError("Formato non supportato: usa .md, .docx o .pdf")
    print(f"Esportato in {out.resolve()}")


def cmd_delete(service: Service, args) -> None:
    rec_id = service.store.resolve_id(args.id)
    meta = service.store.meta(rec_id)
    if not args.yes:
        answer = input(f"Eliminare definitivamente '{meta.title}' (audio, trascrizione e analisi)? [s/N] ")
        if answer.strip().lower() not in {"s", "si", "sì"}:
            print("Annullato.")
            return
    service.store.delete(rec_id)
    print("Registrazione eliminata.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Trascrizione e analisi di registrazioni")
    parser.add_argument("--veloce", action="store_true", help="trascrizione con un modello più piccolo (bozza rapida)")
    parser.add_argument("--motore", choices=[p[0] for p in PROVIDERS],
                        help="motore di analisi: ollama (locale), gemini (cloud gratis) o claude (a pagamento)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("process", help="importa un audio, trascrive e analizza")
    p.add_argument("file")
    p.add_argument("--title")
    p.add_argument("--template", default="riunione")
    p.add_argument("--only-transcribe", action="store_true", help="solo trascrizione, senza Claude")
    p.add_argument("--persone", type=int, help="quante persone parlano, se lo sai (migliora gli interlocutori)")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("transcribe", help="trascrive una registrazione già importata")
    p.add_argument("id")
    p.add_argument("--force", action="store_true", help="ritrascrivi anche se già fatto")
    p.add_argument("--persone", type=int, help="quante persone parlano, se lo sai (migliora gli interlocutori)")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("analyze", help="analizza (o riprende l'analisi di) una registrazione")
    p.add_argument("id")
    p.add_argument("--template", default="riunione")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("summary", help="genera il riassunto con un altro template")
    p.add_argument("id")
    p.add_argument("--template", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_summary)

    sub.add_parser("list", help="elenco delle registrazioni").set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="mostra riassunto, trascrizione, json o mappa mentale")
    p.add_argument("id")
    p.add_argument("what", nargs="?", default="summary", choices=["summary", "transcript", "json", "mindmap"])
    p.add_argument("--template")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("ask", help="fai domande sulla registrazione")
    p.add_argument("id")
    p.add_argument("question", nargs="?")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("templates", help="elenca, crea o elimina template di riassunto")
    p.add_argument("action", nargs="?", default="list", choices=["list", "create", "delete"])
    p.add_argument("text", nargs="*")
    p.set_defaults(func=cmd_templates)

    p = sub.add_parser("speakers", help="mostra o rinomina gli interlocutori (SPEAKER_00=Marco)")
    p.add_argument("id")
    p.add_argument("names", nargs="*")
    p.set_defaults(func=cmd_speakers)

    p = sub.add_parser("delete", help="elimina definitivamente una registrazione")
    p.add_argument("id")
    p.add_argument("--yes", "-y", action="store_true", help="non chiedere conferma")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("export", help="esporta in Markdown, Word o PDF")
    p.add_argument("id")
    p.add_argument("--format", "-f", choices=["md", "docx", "pdf"], default="md")
    p.add_argument("--output", "-o", help="file di destinazione (il formato si deduce dall'estensione)")
    p.add_argument("--no-transcript", action="store_true", help="senza la trascrizione completa")
    p.add_argument("--template")
    p.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # accenti corretti nel terminale di Windows
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if args.veloce:
        settings.whisper_model = "small"
    try:
        args.func(Service(settings), args)
    except AppError as e:
        print(f"\nErrore: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrotto. Il lavoro già salvato non va perso.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
