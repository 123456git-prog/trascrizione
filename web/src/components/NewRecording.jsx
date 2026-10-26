import { useEffect, useRef, useState } from "react";
import { api, formatTime } from "../api.js";
import { EnginePicker, Icon, Sheet, SpeakersField } from "./ui.jsx";

const ACCEPT = ".mp3,.m4a,.wav,.webm,.ogg,.mp4,.aac,.flac,audio/*";

export default function NewRecording({ mode, onClose, onCreated }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [templates, setTemplates] = useState([]);
  const [template, setTemplate] = useState("riunione");
  const [providers, setProviders] = useState([]);
  const [engine, setEngine] = useState("");
  const [analyzeNow, setAnalyzeNow] = useState(true);
  const [speakers, setSpeakers] = useState(0);
  const [consent, setConsent] = useState(false);
  const [upload, setUpload] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.templates().then(setTemplates).catch(() => {});
    api
      .providers()
      .then((list) => {
        setProviders(list);
        // di default il motore locale: è l'unico adatto ai dati sensibili
        const first = list.find((p) => p.available && p.sensitive_ok) || list.find((p) => p.available);
        setEngine(first?.id || "");
        if (!first) setAnalyzeNow(false);
      })
      .catch(() => {});
  }, []);

  async function submit() {
    setError("");
    setUpload(0);
    try {
      const rec = await api.upload(
        file,
        { title, template, provider: engine, analyze: analyzeNow && !!engine, speakers },
        setUpload,
      );
      onCreated(rec);
    } catch (e) {
      setError(e.message);
      setUpload(null);
    }
  }

  const ready = file && consent && upload === null && (!analyzeNow || engine);

  return (
    <Sheet title={mode === "record" ? "Nuova registrazione" : "Carica un file audio"} onClose={onClose}>
      {mode === "record" ? (
        <Recorder onDone={setFile} />
      ) : (
        <label className="dropzone">
          <input type="file" accept={ACCEPT} onChange={(e) => setFile(e.target.files[0] || null)} hidden />
          <Icon name="upload" size={28} />
          <span>{file ? file.name : "Scegli un file (mp3, m4a, wav…)"}</span>
          {file && <span className="small muted">{(file.size / 1024 / 1024).toFixed(1)} MB</span>}
        </label>
      )}

      {file && (
        <div className="form">
          <label className="field">
            <span>Titolo (facoltativo, altrimenti lo propone l'analisi)</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="es. Riunione di reparto" />
          </label>

          <SpeakersField value={speakers} onChange={setSpeakers} />

          {providers.length > 0 && !providers.some((p) => p.available) && (
            <p className="small warn">
              Nessun motore di analisi è pronto (vedi README): per ora la registrazione verrà solo trascritta, potrai
              analizzarla dopo.
            </p>
          )}
          <label className="check">
            <input type="checkbox" checked={analyzeNow} onChange={(e) => setAnalyzeNow(e.target.checked)} />
            <span>Analizza subito dopo la trascrizione</span>
          </label>

          {analyzeNow && (
            <>
              <label className="field">
                <span>Template del riassunto</span>
                <select value={template} onChange={(e) => setTemplate(e.target.value)}>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="field">
                <span>Motore di analisi</span>
                <EnginePicker providers={providers} value={engine} onChange={setEngine} />
                {providers.find((p) => p.id === engine && !p.sensitive_ok) && (
                  <p className="small warn">Il testo verrà inviato a un servizio cloud: usalo solo se i dati non sono sensibili.</p>
                )}
              </div>
            </>
          )}

          <label className="check consent">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>
              Ho informato le persone registrate e ho il loro consenso alla registrazione e alla trascrizione (GDPR).
            </span>
          </label>

          {error && <p className="error">{error}</p>}
          {upload !== null && (
            <div className="progress">
              <div style={{ width: `${Math.round(upload * 100)}%` }} />
              <span className="small muted">Caricamento {Math.round(upload * 100)}%</span>
            </div>
          )}
          <button className="btn primary wide" disabled={!ready} onClick={submit}>
            Trascrivi
          </button>
          <p className="small muted center">La trascrizione avviene sul tuo PC e può richiedere tempo: puoi chiudere questa pagina.</p>
        </div>
      )}
    </Sheet>
  );
}

// Registrazione dal browser con MediaRecorder.
function Recorder({ onDone }) {
  const [state, setState] = useState("idle"); // idle | recording | paused | done
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [level, setLevel] = useState(0);
  const rec = useRef(null);

  useEffect(() => () => stopAll(), []);

  function stopAll() {
    const r = rec.current;
    if (!r) return;
    clearInterval(r.timer);
    cancelAnimationFrame(r.raf);
    r.stream?.getTracks().forEach((t) => t.stop());
    r.audioCtx?.close();
    r.wakeLock?.release?.();
  }

  async function start() {
    setError("");
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError(
        "Il browser permette di registrare solo su connessione sicura (o da http://localhost sul PC). " +
          "Dal telefono registra con l'app Registratore e poi usa “Carica”.",
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const type = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find((t) => MediaRecorder.isTypeSupported(t));
      const mr = new MediaRecorder(stream, type ? { mimeType: type, audioBitsPerSecond: 64000 } : undefined);
      const chunks = [];
      mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      mr.onstop = () => {
        const mime = mr.mimeType || "audio/webm";
        const ext = mime.includes("mp4") ? "m4a" : "webm";
        const stamp = new Date().toLocaleString("it-IT").replace(/[/:]/g, "-").replace(", ", " ");
        onDone(new File(chunks, `Registrazione ${stamp}.${ext}`, { type: mime }));
        setState("done");
        stopAll();
      };
      mr.start(10000); // salva un pezzo ogni 10 secondi
      const audioCtx = new AudioContext();
      const analyser = audioCtx.createAnalyser();
      audioCtx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      const r = { mr, stream, audioCtx, startedAt: Date.now(), offset: 0 };
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
        setLevel(peak / 128);
        r.raf = requestAnimationFrame(tick);
      };
      tick();
      r.timer = setInterval(() => {
        if (mr.state === "recording") setElapsed(r.offset + (Date.now() - r.startedAt) / 1000);
      }, 500);
      r.wakeLock = await navigator.wakeLock?.request("screen").catch(() => null); // evita lo spegnimento dello schermo
      rec.current = r;
      setState("recording");
    } catch (e) {
      setError(e.name === "NotAllowedError" ? "Permesso per il microfono negato." : `Microfono non disponibile: ${e.message}`);
    }
  }

  function pause() {
    const r = rec.current;
    if (r.mr.state === "recording") {
      r.mr.pause();
      r.offset += (Date.now() - r.startedAt) / 1000;
      setState("paused");
    } else {
      r.mr.resume();
      r.startedAt = Date.now();
      setState("recording");
    }
  }

  return (
    <div className="recorder">
      <div className={`rec-dot ${state === "recording" ? "on" : ""}`} style={{ "--level": level }} />
      <div className="rec-time">{formatTime(elapsed)}</div>
      {error && <p className="error">{error}</p>}
      <div className="rec-actions">
        {state === "idle" && (
          <button className="btn primary" onClick={start}>
            <Icon name="mic" /> Inizia
          </button>
        )}
        {(state === "recording" || state === "paused") && (
          <>
            <button className="btn secondary" onClick={pause}>
              <Icon name={state === "paused" ? "play" : "pause"} /> {state === "paused" ? "Riprendi" : "Pausa"}
            </button>
            <button className="btn danger" onClick={() => rec.current.mr.stop()}>
              <Icon name="stop" /> Termina
            </button>
          </>
        )}
        {state === "done" && <p className="muted">Registrazione pronta ({formatTime(elapsed)}).</p>}
      </div>
      {state === "idle" && !error && (
        <p className="small muted center">Prima di iniziare, informa i presenti che stai registrando.</p>
      )}
    </div>
  );
}
