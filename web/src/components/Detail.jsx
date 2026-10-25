import { useCallback, useEffect, useRef, useState } from "react";
import { ACTIVE, api, formatDate, formatTime } from "../api.js";
import Player from "./Player.jsx";
import TranscriptView from "./TranscriptView.jsx";
import SummaryTab from "./SummaryTab.jsx";
import ExtractionTab from "./ExtractionTab.jsx";
import MindMapTab from "./MindMapTab.jsx";
import ChatTab from "./ChatTab.jsx";
import { Icon, Sheet, StatusBadge } from "./ui.jsx";

const TABS = [
  ["transcript", "Trascrizione"],
  ["summary", "Riassunto"],
  ["extraction", "Estrazioni"],
  ["mindmap", "Mappa"],
  ["chat", "Chiedi"],
];

export default function Detail({ id }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState(() => sessionStorage.getItem("tab") || "transcript");
  const [time, setTime] = useState(0);
  const [editingTitle, setEditingTitle] = useState(false);
  const [exporting, setExporting] = useState(false);
  const audio = useRef(null);

  const load = useCallback(async () => {
    try {
      setData(await api.get(id));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // durante l'elaborazione legge solo lo stato; a fine lavoro ricarica tutto
  const active = data && ACTIVE.includes(data.meta.status);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(async () => {
      try {
        const meta = await api.status(id);
        if (ACTIVE.includes(meta.status)) setData((d) => ({ ...d, meta }));
        else load();
      } catch {
        /* riprova al prossimo giro */
      }
    }, 2500);
    return () => clearInterval(t);
  }, [active, id, load]);

  useEffect(() => {
    try {
      sessionStorage.setItem("tab", tab);
    } catch {
      /* storage non disponibile */
    }
  }, [tab]);

  const seek = useCallback((seconds, play = true) => {
    const a = audio.current;
    if (!a || seconds == null) return;
    a.currentTime = seconds;
    if (play) a.play().catch(() => {});
  }, []);

  if (error && !data)
    return (
      <main className="page">
        <BackBar />
        <p className="error banner">{error}</p>
      </main>
    );
  if (!data) return <main className="page"><BackBar /></main>;

  const { meta, transcript, analysis } = data;

  async function saveTitle(e) {
    e.preventDefault();
    const title = new FormData(e.target).get("title");
    await api.patch(id, { title }).catch((err) => alert(err.message));
    setEditingTitle(false);
    load();
  }

  async function remove() {
    if (!confirm(`Eliminare definitivamente “${meta.title}”? Audio, trascrizione e analisi verranno cancellati.`)) return;
    try {
      await api.remove(id);
      window.location.hash = "#/";
    } catch (e) {
      alert(e.message);
    }
  }

  return (
    <main className="page detail">
      <BackBar>
        <button className="icon-btn" onClick={() => setExporting(true)} title="Esporta">
          <Icon name="download" />
        </button>
        <button className="icon-btn" onClick={remove} title="Elimina">
          <Icon name="trash" />
        </button>
      </BackBar>

      <section className="detail-head">
        {editingTitle ? (
          <form onSubmit={saveTitle} className="title-form">
            <input name="title" defaultValue={meta.title} autoFocus />
            <button className="btn primary small">Salva</button>
          </form>
        ) : (
          <h1 onClick={() => setEditingTitle(true)} title="Tocca per rinominare">
            {meta.title}
          </h1>
        )}
        <div className="muted small">
          {formatDate(meta.created_at)} · {formatTime(meta.duration)}
          {transcript?.engine && ` · ${transcript.model}`}
          {analysis?.provider && ` · analisi: ${analysis.provider}`} <StatusBadge meta={meta} />
        </div>
        {active && (
          <div className="progress big">
            <div style={{ width: `${Math.round((meta.progress || 0) * 100)}%` }} />
            <span className="small">
              {meta.status === "in coda" && meta.queue_position > 1
                ? `In coda: ${meta.queue_position - 1} prima di questa`
                : meta.progress_message || "In elaborazione"}
            </span>
          </div>
        )}
        {meta.status === "errore" && <ErrorBox meta={meta} transcript={transcript} id={id} onRetry={load} />}
      </section>

      <nav className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </nav>

      <section className="tab-body">
        {!transcript ? (
          <p className="muted empty">La trascrizione non è ancora pronta.</p>
        ) : tab === "transcript" ? (
          <TranscriptView id={id} transcript={transcript} time={time} seek={seek} onChange={load} stale={analysis?.stale} />
        ) : tab === "summary" ? (
          <SummaryTab id={id} analysis={analysis} seek={seek} busy={active} onStarted={load} />
        ) : tab === "extraction" ? (
          <ExtractionTab id={id} analysis={analysis} seek={seek} busy={active} onStarted={load} />
        ) : tab === "mindmap" ? (
          <MindMapTab analysis={analysis} />
        ) : (
          <ChatTab id={id} analysis={analysis} seek={seek} />
        )}
      </section>

      {exporting && <ExportSheet id={id} analysis={analysis} onClose={() => setExporting(false)} />}

      <Player ref={audio} src={api.audioUrl(id)} duration={meta.duration} onTime={setTime} />
    </main>
  );
}

function ExportSheet({ id, analysis, onClose }) {
  const [withTranscript, setWithTranscript] = useState(true);
  const summaries = analysis?.summaries || {};
  const [template, setTemplate] = useState(analysis?.last_template || Object.keys(summaries)[0] || "");
  const url = (format) => `${api.exportUrl(id, format, template)}&transcript=${withTranscript}`;
  return (
    <Sheet title="Esporta" onClose={onClose}>
      <div className="form">
        {Object.keys(summaries).length > 1 && (
          <label className="field">
            <span>Riassunto da includere</span>
            <select value={template} onChange={(e) => setTemplate(e.target.value)}>
              {Object.entries(summaries).map(([k, s]) => (
                <option key={k} value={k}>
                  {s.template_name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="check">
          <input type="checkbox" checked={withTranscript} onChange={(e) => setWithTranscript(e.target.checked)} />
          <span>Includi la trascrizione completa</span>
        </label>
        <div className="export-buttons">
          {[["docx", "Word"], ["pdf", "PDF"], ["md", "Markdown"]].map(([f, label]) => (
            <a key={f} className="btn secondary" href={url(f)} download>
              <Icon name="download" size={18} /> {label}
            </a>
          ))}
        </div>
      </div>
    </Sheet>
  );
}

function BackBar({ children }) {
  return (
    <header className="topbar">
      <a className="icon-btn" href="#/" aria-label="Indietro">
        <Icon name="back" />
      </a>
      <div className="topbar-actions">{children}</div>
    </header>
  );
}

function ErrorBox({ meta, transcript, id, onRetry }) {
  async function retry() {
    try {
      if (transcript) await api.analyze(id, { template: "riunione" });
      else await api.transcribe(id);
      onRetry();
    } catch (e) {
      alert(e.message);
    }
  }
  return (
    <div className="error banner">
      <p>{meta.error}</p>
      <button className="btn small secondary" onClick={retry}>
        <Icon name="refresh" /> Riprova
      </button>
    </div>
  );
}

