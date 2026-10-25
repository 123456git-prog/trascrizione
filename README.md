# Trascrizione

App personale per trascrivere registrazioni audio (riunioni, lezioni, interviste, chiamate) e lavorare sul contenuto: riassunti con template, keywords, estrazione strutturata con timestamp, mappa mentale e domande sulla registrazione.

> **Stato:** tappa 1 di 5, prototipo da riga di comando. L'interfaccia web arriva nelle tappe successive.

## Come funziona

```
audio (mp3, m4a, wav)
   │  ffmpeg → WAV 16 kHz
   ▼
TRASCRIZIONE (sempre in locale)          ANALISI DEL TESTO (sostituibile)
faster-whisper  o  whisper.cpp    ──►    Claude (API)  o  Ollama (locale, gratis)
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

Scegli il motore di analisi:

- **Claude (consigliato per la qualità):** crea una chiave su [console.anthropic.com](https://console.anthropic.com) (Settings → API Keys), ricarica qualche euro di credito e incollala in `ANTHROPIC_API_KEY=`. Costo indicativo: 0,50-1 € per una registrazione di 2 ore con `claude-opus-5-5`. Con `CLAUDE_MODEL=claude-haiku-5-5` il costo scende a pochi centesimi, con qualità più bassa.
- **Ollama (gratis, tutto in locale):** installa Ollama da [ollama.com](https://ollama.com), poi esegui `ollama pull gemma3:4b` e imposta `LLM_PROVIDER=ollama`. Su un portatile con 8 GB di RAM è lento (1-3 ore di analisi per 2 ore di audio) e meno preciso, ma nessun dato esce dal PC.

Puoi anche scegliere caso per caso con `--motore claude` oppure `--motore ollama`.

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
python -m app.cli export <id> -o riunione.md
```

Basta l'inizio dell'id (per esempio `20261025`) se non è ambiguo.

Tempi indicativi sul tuo PC (Ryzen 5 4500U): con `large-v3-turbo` la trascrizione di 2 ore di audio richiede **2-3 ore**. Per una bozza veloce usa `--veloce`, che passa al modello `small`: circa 3 volte più rapido ma meno preciso.

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
| `export ID [-o file.md]` | export in Markdown (Word e PDF nella tappa 4) |
| `list` / `delete ID` | archivio |

Opzioni globali, da mettere prima del comando: `--motore claude|ollama` e `--veloce`.

**Template predefiniti:** `riunione`, `intervista`, `lezione`, `vendita`. Per crearne uno tuo descrivilo a parole:

```powershell
python -m app.cli templates create "assemblea di condominio: spese approvate, votazioni, lavori e scadenze"
```

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
- **Categorie particolari di dati** (salute, opinioni politiche, dati di minori e simili) richiedono ancora più cautela: per queste usa l'analisi locale (`--motore ollama`).

Dove vanno i dati:

| Fase | Dove avviene | Cosa esce dal PC |
|---|---|---|
| Trascrizione e interlocutori | sul tuo PC | nulla (si scaricano solo i modelli) |
| Analisi con Ollama | sul tuo PC | nulla |
| Analisi con Claude | server di Anthropic | il **testo** della trascrizione, non l'audio |

Con Claude il testo viene inviato ad Anthropic (Stati Uniti). In base ai termini commerciali dell'API, i dati non vengono usati per addestrare i modelli. Per contenuti molto sensibili usa Ollama.

Questo avviso è una guida pratica e non sostituisce una consulenza legale.
