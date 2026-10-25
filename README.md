# Trascrizione

App personale per trascrivere registrazioni audio (riunioni, lezioni, interviste, chiamate) e lavorare sul contenuto: riassunti con template, keywords, estrazione strutturata con timestamp, mappa mentale e domande sulla registrazione.

> **Stato:** tappe 1-3 di 5: riga di comando, server con elaborazioni in background e interfaccia web per PC e telefono. Tappa 4 in corso: export Word e PDF disponibile.

## Come funziona

```
audio (mp3, m4a, wav)
   │  ffmpeg → WAV 16 kHz
   ▼
TRASCRIZIONE (sempre in locale)          ANALISI DEL TESTO (scegli ogni volta)
faster-whisper  o  whisper.cpp    ──►    Ollama (locale) · Gemini (cloud gratis) · Claude
+ pyannote per gli interlocutori         blocchi → appunti → riassunto finale
   │                                     keywords · estrazione JSON · mappa · chat
   ▼                                              │
data/recordings/<id>/  ◄──────────────────────────┘
  audio.m4a · transcript.json · analysis.json · meta.json
```

- **La trascrizione si fa una volta sola** e viene salvata. Riassunti con altri template, domande e mappe riusano il testo salvato.
- **Registrazioni lunghe:** la trascrizione viene divisa in blocchi, ogni blocco viene riassunto, poi si produce il riassunto finale dagli appunti.
- **Ogni elemento estratto** (decisioni, azioni, persone, date, cifre, domande aperte) è collegato al segmento d'origine, con timestamp e interlocutore. Claude indica solo l'id del segmento: il timestamp lo prende il programma dalla trascrizione, quindi non può essere inventato.
- **Se qualcosa si interrompe** (rete, credito, errore), rilanciando `analyze` si riparte dal punto in cui ci si era fermati.
- **Le chiavi API** stanno solo nel file `.env` sul tuo PC, mai nel browser.
- **Ogni volta scegli il motore di analisi** in base alla sensibilità dei dati (vedi sotto).

## Installazione su Windows

Apri **PowerShell** ed esegui i comandi uno alla volta.

### 1. Programmi necessari

```powershell
winget install Python.Python.3.12
winget install Git.Git
winget install Gyan.FFmpeg
```

Chiudi e riapri PowerShell dopo l'installazione, poi controlla che funzionino:

```powershell
python --version
ffmpeg -version
```

### 2. Scarica il progetto

```powershell
cd $HOME\Documents
git clone https://github.com/123456git-prog/trascrizione.git
cd trascrizione
```

Il repository è privato: la prima volta Git apre il browser per farti accedere a GitHub.

### 3. Ambiente Python e dipendenze

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-stt.txt
```

Se PowerShell blocca `Activate.ps1`, esegui una volta `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e riprova.
Ogni volta che riapri PowerShell, torna nella cartella e riattiva l'ambiente con `.\.venv\Scripts\Activate.ps1`.

### 4. Configurazione

```powershell
copy .env.example .env
notepad .env
```

Prepara i motori di analisi. Ogni volta che analizzi una registrazione il programma ti chiede quale usare.

| Motore | Costo | Velocità sul tuo PC | Privacy | Quando usarlo |
|---|---|---|---|---|
| **1. Ollama** (locale) | gratis | lento: 1-3 ore per 2 ore di audio | nulla esce dal PC | dati sensibili |
| **2. Gemini** (cloud) | gratis entro la quota | pochi minuti | il testo va a Google | solo dati **non** sensibili |
| **3. Claude** (cloud) | 0,50-1 € a registrazione | pochi minuti | il testo va ad Anthropic | facoltativo, qualità migliore |

**Ollama (locale):** installa Ollama da [ollama.com](https://ollama.com), poi esegui:

```powershell
ollama pull gemma3:4b
```

**Gemini (quota gratuita):** vai su [aistudio.google.com](https://aistudio.google.com), accedi con un account Google, clicca **Get API key** e poi **Create API key**. Incollala nel file `.env` in `GEMINI_API_KEY=`. La quota gratuita ha limiti di richieste al minuto e al giorno: se li superi, il programma aspetta e riprova da solo.

**Claude (facoltativo):** crea una chiave su [console.anthropic.com](https://console.anthropic.com) (Settings → API Keys), ricarica qualche euro di credito e incollala in `ANTHROPIC_API_KEY=`.

Per saltare la domanda puoi indicare il motore nel comando, per esempio `python -m app.cli --motore gemini analyze <id>`. Una registrazione già analizzata continua a usare lo stesso motore, a meno che tu non ne indichi un altro con `--motore`.

## Come provarlo

Inizia con un file breve (2-5 minuti) per verificare che tutto funzioni.

```powershell
# 1. solo trascrizione (gratis, nessun dato esce dal PC)
#    la prima volta scarica il modello: circa 1,6 GB
python -m app.cli process "C:\Users\TUONOME\Downloads\prova.m4a" --only-transcribe

# 2. elenco e trascrizione
python -m app.cli list
python -m app.cli show <id> transcript

# 3. analisi completa (riassunto, keywords, estrazione, mappa mentale)
python -m app.cli analyze <id> --template riunione

# 4. domande sulla registrazione (senza domanda si apre una chat)
python -m app.cli ask <id> "Quali decisioni sono state prese?"
python -m app.cli ask <id>

# 5. altro template, estrazione JSON, mappa mentale, export
python -m app.cli summary <id> --template lezione
python -m app.cli show <id> json
python -m app.cli show <id> mindmap
python -m app.cli export <id> -o riunione.docx   # oppure .pdf o .md
```

Basta l'inizio dell'id (per esempio `20261025`) se non è ambiguo.

Tempi misurati sul tuo PC (Ryzen 5 4500U): con `large-v3-turbo` la trascrizione procede circa in **tempo reale**, quindi 2 ore di audio richiedono circa 2 ore. Per una bozza veloce usa `--veloce`, che passa al modello `small`: circa 3 volte più rapido ma meno preciso.

### Tutti i comandi

| Comando | Cosa fa |
|---|---|
| `process FILE [--template T] [--title X] [--only-transcribe]` | importa, trascrive e analizza |
| `transcribe ID [--force]` | trascrive (o ritrascrive con `--force`) |
| `analyze ID [--template T]` | analisi completa, riprende da dove si era fermata |
| `summary ID --template T` | riassunto con un altro template |
| `ask ID ["domanda"]` | domande con citazioni `[#id]` dei punti della trascrizione |
| `templates` / `templates create "descrizione"` / `templates delete ID` | template di riassunto |
| `speakers ID [SPEAKER_00=Marco ...]` | mostra o rinomina gli interlocutori |
| `show ID [summary\|transcript\|json\|mindmap]` | mostra i risultati |
| `export ID [-f md\|docx\|pdf] [-o file] [--no-transcript]` | export in Markdown, Word o PDF |
| `list` / `delete ID` | archivio |

Opzioni globali, da mettere prima del comando: `--motore ollama|gemini|claude` e `--veloce`.

**Template predefiniti:** `riunione`, `intervista`, `lezione`, `vendita`. Per crearne uno tuo descrivilo a parole:

```powershell
python -m app.cli templates create "assemblea di condominio: spese approvate, votazioni, lavori e scadenze"
```

## Interfaccia web

```powershell
python -m app.server
```

Il server mostra due indirizzi: `http://localhost:8000` per il PC e `http://192.168.x.x:8000` per il telefono collegato allo stesso Wi-Fi. La prima volta Windows chiede se consentire l'accesso alla rete: scegli **Reti private**.

- Le elaborazioni lunghe girano in background, una alla volta, con l'avanzamento salvato. Se chiudi il server, alla riapertura riprendono da sole.
- **Consigliato:** imposta `APP_PASSWORD=` nel file `.env`, così chi usa il tuo Wi-Fi non può aprire le registrazioni.
- L'elenco completo delle API si trova su `http://localhost:8000/docs`.
- **Registrare dal browser** funziona sul PC (`http://localhost:8000`). Dal telefono il browser blocca il microfono sulle connessioni non cifrate: registra con l'app Registratore del telefono e usa **Carica**.
- Sul telefono puoi aggiungere l'app alla schermata Home (menu del browser → *Aggiungi a schermata Home*).

Cosa trovi nell'interfaccia: elenco con ricerca, caricamento o registrazione con conferma del consenso, avanzamento delle elaborazioni, pagina di dettaglio con player (velocità, ±15 s), trascrizione sincronizzata e modificabile (tocca una frase per ascoltarla), nomi degli interlocutori, schede Riassunto (template, keywords, argomenti), Estrazioni (con download JSON), Mappa mentale e Chiedi (risposte con orari cliccabili), template personalizzati, export in Word, PDF e Markdown.

L'interfaccia è già compilata in `web/dist`, quindi non serve installare altro. Per modificarla serve Node.js: `cd web`, `npm install`, `npm run dev` (con il server Python acceso), poi `npm run build`.

## Opzioni avanzate

### Riconoscimento degli interlocutori (in locale)

1. Crea un account gratuito su [huggingface.co](https://huggingface.co), poi un token in Settings → Access Tokens (tipo *Read*).
2. Accetta le condizioni d'uso di [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) e [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0).
3. Installa: `pip install -r requirements-diarization.txt` (circa 1 GB).
4. Nel file `.env` imposta `DIARIZATION=true` e `HF_TOKEN=...`.

Aggiunge circa 30-60 minuti per 2 ore di audio. L'audio non lascia il PC: da Hugging Face si scarica solo il modello.

### whisper.cpp con la grafica AMD (sperimentale)

whisper.cpp può usare la grafica Radeon tramite Vulkan. Serve una versione compilata con Vulkan e il modello `ggml-large-v3-turbo.bin`. Imposta `STT_ENGINE=whisper-cpp`, `WHISPER_CPP_BIN` e `WHISPER_CPP_MODEL`. Lo proveremo insieme e lo terremo solo se sul tuo PC è più veloce di faster-whisper.

## Test automatici

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

I test non usano servizi esterni: Claude, Ollama e i modelli di trascrizione sono simulati, mentre ffmpeg viene usato davvero.

## Privacy e consenso alla registrazione (GDPR)

> **Avviso:** registrare una persona e trattarne la voce e le parole significa trattare dati personali. Prima di registrare, informa i partecipanti e ottieni il loro consenso. Non registrare di nascosto.

In pratica:

- **Informa e chiedi il consenso** all'inizio della registrazione (meglio se resta registrato: "Vi informo che registro la riunione per prendere appunti, siete d'accordo?"). Per le lezioni, verifica le regole dell'istituto e chiedi il permesso al docente.
- **Usa le registrazioni solo per lo scopo dichiarato** (appunti, verbale) e non diffonderle.
- **Conserva il minimo necessario:** elimina audio e trascrizioni quando non servono più (`python -m app.cli delete ID`). Tutti i dati sono nella cartella `data/` del tuo PC.
- **Proteggi il PC:** password di accesso e, se possibile, cifratura del disco (BitLocker).
- **Dati sensibili** (salute, opinioni politiche, dati di minori, informazioni riservate di lavoro e simili): usa **solo** l'analisi locale (`--motore ollama`).

Dove vanno i dati:

| Fase | Dove avviene | Cosa esce dal PC |
|---|---|---|
| Trascrizione e interlocutori | sul tuo PC | nulla (si scaricano solo i modelli) |
| Analisi con Ollama | sul tuo PC | nulla |
| Analisi con Gemini | server di Google | il **testo** della trascrizione, non l'audio |
| Analisi con Claude | server di Anthropic | il **testo** della trascrizione, non l'audio |

**Gemini gratuito:** i termini di Google valgono per i servizi gratuiti. In generale Google può usare i contenuti per migliorare i propri prodotti e farli leggere a revisori umani. Per chi si trova nello Spazio Economico Europeo, in Svizzera o nel Regno Unito si applicano invece le regole dei servizi a pagamento, quindi i contenuti non vengono usati a quello scopo ([termini](https://ai.google.dev/gemini-api/terms)). Google stessa raccomanda comunque di non inviare informazioni sensibili ai servizi gratuiti: usalo solo per registrazioni non sensibili.

**Claude:** il testo viene inviato ad Anthropic (Stati Uniti). In base ai termini commerciali dell'API, i dati non vengono usati per addestrare i modelli.

Questo avviso è una guida pratica e non sostituisce una consulenza legale.
