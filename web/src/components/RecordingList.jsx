import { useCallback, useEffect, useRef, useState } from "react";
import { ACTIVE, api, formatDate, formatTime } from "../api.js";
import NewRecording from "./NewRecording.jsx";
import { Icon, StatusBadge } from "./ui.jsx";

export default function RecordingList() {
  const [items, setItems] = useState(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [sheet, setSheet] = useState(null); // null | "upload" | "record"
  const timer = useRef();

  const load = useCallback(async (q) => {
    try {
      setItems(await api.list(q));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => load(query.trim()), query ? 250 : 0);
  }, [query, load]);

  // aggiorna l'avanzamento finché c'è qualcosa in elaborazione
  useEffect(() => {
    if (!items?.some((r) => ACTIVE.includes(r.status))) return;
    const t = setInterval(() => load(query.trim()), 3000);
    return () => clearInterval(t);
  }, [items, query, load]);

  return (
    <main className="page">
      <header className="topbar">
        <h1>Registrazioni</h1>
        <a className="icon-btn" href="#/template" title="Template di riassunto">
          <Icon name="layers" />
        </a>
      </header>

      <div className="search">
        <Icon name="search" />
        <input
          type="search"
          placeholder="Cerca in titoli, riassunti e trascrizioni"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {error && <p className="error banner">{error}</p>}

      {items && items.length === 0 && (
        <div className="empty">
          {query ? (
            <p>Nessun risultato per “{query}”.</p>
          ) : (
            <>
              <p>Nessuna registrazione ancora.</p>
              <p className="muted">Carica un file audio o registra direttamente dal browser.</p>
            </>
          )}
        </div>
      )}

      <ul className="rec-list">
        {items?.map((r) => (
          <li key={r.id}>
            <a className="card rec-item" href={`#/r/${r.id}`}>
              <div className="rec-head">
                <strong className="rec-title">{r.title}</strong>
                <StatusBadge meta={r} />
              </div>
              <div className="muted small">
                {formatDate(r.created_at)} · {formatTime(r.duration)}
              </div>
              {r.snippet && <p className="snippet" dangerouslySetInnerHTML={{ __html: highlight(r.snippet) }} />}
              {ACTIVE.includes(r.status) && (
                <div className="progress" aria-label="avanzamento">
                  <div style={{ width: `${Math.round((r.progress || 0) * 100)}%` }} />
                  <span className="small muted">{r.progress_message}</span>
                </div>
              )}
            </a>
          </li>
        ))}
      </ul>

      <div className="fab-row">
        <button className="btn fab secondary" onClick={() => setSheet("upload")}>
          <Icon name="upload" /> Carica
        </button>
        <button className="btn fab primary" onClick={() => setSheet("record")}>
          <Icon name="mic" /> Registra
        </button>
      </div>

      {sheet && (
        <NewRecording
          mode={sheet}
          onClose={() => setSheet(null)}
          onCreated={(rec) => {
            setSheet(null);
            window.location.hash = `#/r/${rec.id}`;
          }}
        />
      )}
    </main>
  );
}

// lo snippet arriva come testo con i termini tra [ ]: lo rendiamo sicuro e lo evidenziamo
function highlight(snippet) {
  const esc = snippet.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  return esc.replace(/\[([^\]]+)\]/g, "<mark>$1</mark>");
}
