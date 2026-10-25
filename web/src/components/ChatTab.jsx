import { useEffect, useRef, useState } from "react";
import { api, formatTime } from "../api.js";
import { EnginePicker, Icon } from "./ui.jsx";

const SUGGESTIONS = ["Quali decisioni sono state prese?", "Chi deve fare cosa, ed entro quando?", "Quali punti sono rimasti aperti?"];

export default function ChatTab({ id, analysis, seek }) {
  const [messages, setMessages] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem(`chat-${id}`)) || [];
    } catch {
      return [];
    }
  });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [providers, setProviders] = useState([]);
  const [engine, setEngine] = useState(analysis?.provider || "");
  const end = useRef(null);

  useEffect(() => {
    api
      .providers()
      .then((list) => {
        setProviders(list);
        if (!engine) setEngine((list.find((p) => p.available && p.sensitive_ok) || list.find((p) => p.available))?.id || "");
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    try {
      sessionStorage.setItem(`chat-${id}`, JSON.stringify(messages));
    } catch {
      /* storage non disponibile */
    }
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, id]);

  async function send(question) {
    question = question.trim();
    if (!question || busy) return;
    setError("");
    setInput("");
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((m) => [...m, { role: "user", content: question }]);
    setBusy(true);
    try {
      const r = await api.ask(id, { question, history, provider: engine });
      setMessages((m) => [...m, { role: "assistant", content: r.answer, citations: r.citations }]);
    } catch (e) {
      setError(e.message);
      setMessages((m) => m.slice(0, -1));
      setInput(question);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      {!analysis?.provider && providers.length > 0 && (
        <div className="field">
          <span>Motore per le risposte</span>
          <EnginePicker providers={providers} value={engine} onChange={setEngine} />
        </div>
      )}
      {messages.length === 0 && (
        <div className="chips suggestions">
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip" onClick={() => send(s)}>
              {s}
            </button>
          ))}
        </div>
      )}
      <div className="messages">
        {messages.map((m, n) => (
          <div key={n} className={`msg ${m.role}`}>
            {m.role === "assistant" ? <Answer text={m.content} citations={m.citations || []} seek={seek} /> : m.content}
          </div>
        ))}
        {busy && <div className="msg assistant typing">Sto leggendo la registrazione…</div>}
        <div ref={end} />
      </div>
      {error && <p className="error">{error}</p>}
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Chiedi qualcosa sulla registrazione" />
        <button className="icon-btn primary" disabled={busy || !input.trim() || !engine} aria-label="Invia">
          <Icon name="send" />
        </button>
      </form>
      {messages.length > 0 && (
        <button className="btn small ghost" onClick={() => setMessages([])}>
          Nuova conversazione
        </button>
      )}
    </div>
  );
}

// Le citazioni [#id] diventano orari cliccabili.
function Answer({ text, citations, seek }) {
  const byId = Object.fromEntries(citations.map((c) => [c.segment_id, c]));
  const parts = text.split(/(\[#\d+\])/g);
  return (
    <>
      <p>
        {parts.map((p, i) => {
          const m = /^\[#(\d+)\]$/.exec(p);
          if (!m) return <span key={i}>{p}</span>;
          const c = byId[m[1]];
          return c ? (
            <button key={i} className="ts inline" onClick={() => seek(c.start)} title={c.text}>
              {formatTime(c.start)}
            </button>
          ) : null;
        })}
      </p>
      {citations.length > 0 && (
        <details className="sources">
          <summary className="small">Fonti ({citations.length})</summary>
          {citations.map((c) => (
            <button key={c.segment_id} className="source" onClick={() => seek(c.start)}>
              <span className="ts">{formatTime(c.start)}</span> {c.speaker ? <strong>{c.speaker}: </strong> : null}
              {c.text}
            </button>
          ))}
        </details>
      )}
    </>
  );
}
