import { formatTime } from "../api.js";
import { AnalyzePanel } from "./SummaryTab.jsx";
import { Icon } from "./ui.jsx";

const SECTIONS = [
  ["decisions", "Decisioni", (i) => i.text],
  ["action_items", "Azioni da fare", (i) => (
    <>
      {i.task}
      <span className="meta-line">
        {i.owner ? <span className="tag ok">{i.owner}</span> : <span className="tag">responsabile?</span>}
        {i.due_date ? <span className="tag cloud">entro {i.due_date}</span> : null}
      </span>
    </>
  )],
  ["people", "Persone", (i) => (
    <>
      {i.name}
      {i.role && <span className="muted"> · {i.role}</span>}
    </>
  )],
  ["dates", "Date", (i) => (
    <>
      <strong>{i.text}</strong>
      {i.normalized && <span className="muted"> ({i.normalized})</span>} · {i.context}
    </>
  )],
  ["figures", "Cifre", (i) => (
    <>
      <strong>{i.value}</strong> · {i.context}
    </>
  )],
  ["open_questions", "Domande aperte", (i) => i.question],
];

export default function ExtractionTab({ id, analysis, seek, busy, onStarted }) {
  const ex = analysis?.extraction;
  if (!ex) return <AnalyzePanel id={id} analysis={analysis} busy={busy} onStarted={onStarted} />;

  function downloadJson() {
    const blob = new Blob([JSON.stringify(ex, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `estrazione-${id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="extraction">
      <div className="toolbar">
        <span className="small muted">Tocca l'orario per ascoltare il punto d'origine.</span>
        <button className="btn small ghost" onClick={downloadJson}>
          <Icon name="download" size={16} /> JSON
        </button>
      </div>
      {SECTIONS.map(([key, title, render]) => (
        <section key={key}>
          <h3>
            {title} <span className="count">{ex[key].length}</span>
          </h3>
          {ex[key].length === 0 ? (
            <p className="muted small">Nessun elemento.</p>
          ) : (
            <ul className="items">
              {ex[key].map((item, n) => (
                <li key={n} className="item">
                  <div className="item-body">{render(item)}</div>
                  {item.timestamp && (
                    <button className="ts" onClick={() => seek(item.start)} title={item.speaker || ""}>
                      {formatTime(item.start)}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
