import { useEffect, useState } from "react";
import { api } from "../api.js";
import { EnginePicker, Icon } from "./ui.jsx";

export default function Templates() {
  const [templates, setTemplates] = useState([]);
  const [description, setDescription] = useState("");
  const [providers, setProviders] = useState([]);
  const [engine, setEngine] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);

  const load = () => api.templates().then(setTemplates).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    api
      .providers()
      .then((list) => {
        setProviders(list);
        // la descrizione di un template non contiene dati personali: va bene anche un motore cloud
        setEngine(list.find((p) => p.available && !p.sensitive_ok)?.id || list.find((p) => p.available)?.id || "");
      })
      .catch(() => {});
  }, []);

  async function create(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const t = await api.createTemplate(description, engine);
      setDescription("");
      setOpen(t.id);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(t) {
    if (!confirm(`Eliminare il template “${t.name}”?`)) return;
    await api.deleteTemplate(t.id).catch((err) => alert(err.message));
    load();
  }

  return (
    <main className="page">
      <header className="topbar">
        <a className="icon-btn" href="#/" aria-label="Indietro">
          <Icon name="back" />
        </a>
        <h1>Template di riassunto</h1>
      </header>

      <form className="card form" onSubmit={create}>
        <h3>Nuovo template</h3>
        <label className="field">
          <span>Descrivi a parole che riassunto vuoi</span>
          <textarea
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="es. Assemblea di condominio: spese approvate con importi, votazioni con esito, lavori da fare e scadenze"
          />
        </label>
        <div className="field">
          <span>Motore</span>
          <EnginePicker providers={providers} value={engine} onChange={setEngine} />
        </div>
        {error && <p className="error">{error}</p>}
        <button className="btn primary" disabled={busy || description.trim().length < 10 || !engine}>
          {busy ? "Creazione…" : "Crea template"}
        </button>
      </form>

      <ul className="template-list">
        {templates.map((t) => (
          <li key={t.id} className="card">
            <button className="template-head" onClick={() => setOpen(open === t.id ? null : t.id)}>
              <span>
                <strong>{t.name}</strong>
                <span className="small muted"> {t.description}</span>
              </span>
              {t.builtin ? <span className="tag">predefinito</span> : <span className="tag ok">tuo</span>}
            </button>
            {open === t.id && (
              <>
                <pre className="instructions">{t.instructions}</pre>
                {!t.builtin && (
                  <button className="btn small danger" onClick={() => remove(t)}>
                    <Icon name="trash" size={16} /> Elimina
                  </button>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
