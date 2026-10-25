"""Testi dei prompt inviati a Claude."""

BASE_SYSTEM = (
    "Lavori su trascrizioni automatiche di registrazioni audio (riunioni, lezioni, interviste, chiamate). "
    "Ogni riga della trascrizione inizia con [#id hh:mm:ss] e, se noto, il nome dell'interlocutore. "
    "La trascrizione automatica può contenere errori di riconoscimento: interpreta con buon senso, "
    "ma non inventare fatti, nomi o cifre che non compaiono. Quando ti viene chiesto un segment_id, "
    "usa l'id della riga in cui l'informazione viene detta. Scrivi sempre in italiano."
)

CHUNK_NOTES = (
    "Questo è il blocco {index} di {total} di una registrazione più lunga.\n"
    "Scrivi un riassunto dettagliato del blocco (circa il 10-15% della lunghezza originale), conservando "
    "nomi, cifre, decisioni e sfumature importanti, e un elenco dei punti chiave con il segment_id "
    "della riga dove ciascuno viene detto."
)

FINAL_SUMMARY = (
    "Qui sopra ci sono gli appunti dei blocchi consecutivi di un'unica registrazione (durata {duration}).\n"
    "Produci il riassunto finale dell'intera registrazione seguendo questo template:\n\n"
    "### Template: {name}\n{instructions}\n\n"
    "Usa Markdown. Sii fedele al contenuto: se una sezione del template non ha materiale, scrivi "
    "'Non emerso dalla registrazione'. Inizia direttamente con la prima sezione, senza titolo generale."
)

KEYWORDS = (
    "Qui sopra ci sono gli appunti di una registrazione, con i segment_id dei punti chiave.\n"
    "Estrai 8-15 keywords (parole o brevi espressioni, in ordine di importanza) e 3-8 argomenti "
    "principali. Per ogni argomento indica un titolo, una descrizione di una o due frasi e i segment_id "
    "dei punti in cui se ne parla (presi dagli appunti)."
)

EXTRACTION = (
    "Estrai dalla trascrizione qui sopra, in modo esaustivo ma senza inventare:\n"
    "- decisions: decisioni prese o concordate\n"
    "- action_items: azioni da fare, con responsabile (owner) e scadenza (due_date) se dette\n"
    "- people: persone nominate o che parlano, con ruolo se emerge\n"
    "- dates: date e riferimenti temporali significativi\n"
    "- figures: cifre, importi, quantità, percentuali\n"
    "- open_questions: domande rimaste senza risposta o temi da chiarire\n"
    "Ogni elemento deve avere il segment_id della riga di origine. Liste vuote se non c'è nulla."
)

MINDMAP = (
    "Trasforma il riassunto qui sopra in una mappa mentale: un elenco Markdown che inizia con "
    "'# ' seguito dal tema centrale, poi rami principali '## ' (3-7) e sotto ciascuno voci '- ' "
    "brevi (massimo 8 parole), con al più due livelli di indentazione."
)

CUSTOM_TEMPLATE = (
    "L'utente vuole un nuovo template di riassunto e lo descrive così:\n\"{description}\"\n\n"
    "Crea il template: un nome breve, una descrizione di una riga, e le istruzioni che verranno date "
    "a un assistente per strutturare il riassunto (sezioni con '## ' e cosa mettere in ciascuna)."
)

CHAT_SYSTEM = (
    BASE_SYSTEM + " Rispondi alle domande dell'utente usando solo il contenuto della trascrizione. "
    "Cita i punti a supporto inserendo [#id] subito dopo l'affermazione (es. 'Il budget è 40.000 euro [#123].'). "
    "Se la risposta non è nella registrazione, dillo chiaramente."
)
