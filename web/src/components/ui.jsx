// Piccoli componenti condivisi: icone (SVG inline, nessuna libreria esterna) e badge di stato.

const PATHS = {
  search: "M11 4a7 7 0 1 0 4.4 12.4l4.1 4.1 1.4-1.4-4.1-4.1A7 7 0 0 0 11 4Zm0 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10Z",
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Zm-7 9h2a5 5 0 0 0 10 0h2a7 7 0 0 1-6 6.9V21h-2v-2.1A7 7 0 0 1 5 12Z",
  upload: "M12 3 7 8l1.4 1.4L11 6.8V16h2V6.8l2.6 2.6L17 8l-5-5ZM5 18v2h14v-2H5Z",
  back: "M15.4 5.4 14 4l-8 8 8 8 1.4-1.4L8.8 12l6.6-6.6Z",
  play: "M8 5v14l11-7L8 5Z",
  pause: "M7 5h4v14H7V5Zm6 0h4v14h-4V5Z",
  rewind: "M11 7v10l-7-5 7-5Zm9 0v10l-7-5 7-5Z",
  forward: "M13 7v10l7-5-7-5ZM4 7v10l7-5-7-5Z",
  edit: "M4 17.2V20h2.8l8.3-8.3-2.8-2.8L4 17.2ZM17.7 7.1a1 1 0 0 0 0-1.4l-1.4-1.4a1 1 0 0 0-1.4 0l-1.1 1.1 2.8 2.8 1.1-1.1Z",
  trash: "M9 3h6l1 2h4v2H4V5h4l1-2Zm-3 6h12l-1 12H7L6 9Z",
  download: "M11 4h2v8.2l2.6-2.6L17 11l-5 5-5-5 1.4-1.4 2.6 2.6V4ZM5 18h14v2H5v-2Z",
  send: "M3 20.5 21 12 3 3.5 3 10l12 2-12 2v6.5Z",
  layers: "M12 3 2 8l10 5 10-5-10-5Zm-8.2 9L2 13l10 5 10-5-1.8-1-8.2 4.1L3.8 12Zm0 4L2 17l10 5 10-5-1.8-1-8.2 4.1L3.8 16Z",
  close: "M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19l5.6-5.6 5.6 5.6 1.4-1.4-5.6-5.6L19 6.4 17.6 5 12 10.6 6.4 5Z",
  stop: "M6 6h12v12H6V6Z",
  refresh: "M12 5a7 7 0 0 0-6.9 6h2A5 5 0 0 1 16 8.3L13.5 11H20V4.5L17.4 7A7 7 0 0 0 12 5Zm6.9 8h-2A5 5 0 0 1 8 15.7l2.5-2.7H4v6.5L6.6 17A7 7 0 0 0 18.9 13Z",
};

export function Icon({ name, size = 20 }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d={PATHS[name]} fill="currentColor" />
    </svg>
  );
}

const LABELS = {
  caricata: "caricata",
  "in coda": "in coda",
  trascrizione: "trascrizione…",
  trascritta: "trascritta",
  analisi: "analisi…",
  pronta: "pronta",
  errore: "errore",
};

export function StatusBadge({ meta }) {
  if (meta.status === "pronta") return null;
  const pos = meta.queue_position > 0 ? ` (${meta.queue_position}°)` : "";
  return (
    <span className={`badge badge-${meta.status.replace(" ", "-")}`} title={meta.error || ""}>
      {LABELS[meta.status] || meta.status}
      {meta.status === "in coda" ? pos : ""}
    </span>
  );
}

export function Sheet({ title, onClose, children }) {
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="sheet-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Chiudi">
            <Icon name="close" />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

// Scelta del motore di analisi, con l'avvertenza sui dati sensibili.
export function EnginePicker({ providers, value, onChange }) {
  return (
    <div className="engines">
      {providers.map((p) => (
        <label key={p.id} className={`engine ${value === p.id ? "selected" : ""} ${p.available ? "" : "disabled"}`}>
          <input
            type="radio"
            name="engine"
            value={p.id}
            checked={value === p.id}
            disabled={!p.available}
            onChange={() => onChange(p.id)}
          />
          <span className="engine-text">
            <strong>{p.label}</strong>
            <span className="small">{p.description}</span>
            {!p.available && <span className="small warn">{p.reason}</span>}
          </span>
          {p.sensitive_ok ? <span className="tag ok">privato</span> : <span className="tag cloud">cloud</span>}
        </label>
      ))}
    </div>
  );
}
