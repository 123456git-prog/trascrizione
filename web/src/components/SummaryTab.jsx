import { useEffect, useState } from "react";
import { api, formatTime } from "../api.js";
import Markdown from "./Markdown.jsx";
import { EnginePicker, Icon } from "./ui.jsx";

export function useTemplates() {
  const [templates, setTemplates] = useState([]);
  useEffect(() => {
    api.templates().then(setTemplates).catch(() => {});
  }, []);
  return templates;
}

// Pannello per avviare l'analisi quando non c'è ancora, o per rifarla.
export function AnalyzePanel({ id, analysis, onStarted, busy, title = "Analizza la registrazione" }) {
  const templates = useTemplates();
  const [providers, setProviders] = useState([]);
  const [engine, setEngine] = useState(analysis?.provider || "");
  const [template, setTemplate] = useState("riunione");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .providers()
      .then((list) => {
        setProviders(list);
        if (!engine) setEngine((list.find((p) => p.available && p.sensitive_ok) || list.find((p) => p.available))?.id || "");
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function start() {
    setError("");
    try {
      await api.analyze(id, { template, provider: engine, force: !!analysis?.summaries });
      onStarted();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="card form">
      <h3>{title}</h3>
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
      </div>
      {error && <p className="error">{error}</p>}
      <button className="btn primary" disabled={busy || !engine} onClick={start}>
        {busy ? "Elaborazione in corso…" : "Avvia analisi"}
      </button>
    </div>
  );
}

export default function SummaryTab({ id, analysis, seek, busy, onStarted }) {
  const templates = useTemplates();
  const summaries = analysis?.summaries || {};
  const [selected, setSelected] = useState(analysis?.last_template || Object.keys(summaries)[0] || "riunione");
  const [error, setError] = useState("");
  const [redo, setRedo] = useState(false);

  if (!Object.keys(summaries).length || redo)
    return <AnalyzePanel id={id} analysis={analysis} busy={busy} onStarted={() => (setRedo(false), onStarted())} />;

  const current = summaries[selected];
  const kw = analysis.keywords;

  async function generate() {
    setError("");
    try {
      await api.summary(id, { template: selected, provider: analysis.provider });
      onStarted();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="summary">
      <div className="toolbar">
        <select value={selected} onChange={(e) => setSelected(e.target.value)} aria-label="Template">
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
              {summaries[t.id] ? "" : " (da generare)"}
            </option>
          ))}
        </select>
        <button className="btn small ghost" onClick={() => setRedo(true)} title="Rifai l'analisi completa">
          <Icon name="refresh" size={16} /> Rianalizza
        </button>
      </div>

      {current ? (
        <article className="card">
          <h2 className="summary-title">{current.title}</h2>
          <Markdown text={current.markdown} />
        </article>
      ) : (
        <div className="card center">
          <p>Riassunto “{templates.find((t) => t.id === selected)?.name}” non ancora generato.</p>
          {error && <p className="error">{error}</p>}
          <button className="btn primary" disabled={busy} onClick={generate}>
            {busy ? "Elaborazione in corso…" : "Genera"}
          </button>
          <p className="small muted">Riusa gli appunti già calcolati: è veloce.</p>
        </div>
      )}

      {kw && (
        <>
          <h3>Keywords</h3>
          <div className="chips">
            {kw.keywords.map((k) => (
              <span className="chip" key={k}>
                {k}
              </span>
            ))}
          </div>
          <h3>Argomenti principali</h3>
          <ul className="topics">
            {kw.topics.map((t) => (
              <li key={t.title} className="card">
                <strong>{t.title}</strong>
                <p>{t.description}</p>
                <div className="chips">
                  {t.refs.slice(0, 6).map((r) => (
                    <button key={r.segment_id} className="ts" onClick={() => seek(r.start)}>
                      {formatTime(r.start)}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
