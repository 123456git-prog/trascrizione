import { useEffect, useMemo, useRef, useState } from "react";
import { api, formatTime, speakerLabel } from "../api.js";
import { Icon } from "./ui.jsx";

export default function TranscriptView({ id, transcript, time, seek, onChange, stale }) {
  const [editing, setEditing] = useState(false);
  const [follow, setFollow] = useState(true);
  const [names, setNames] = useState(false);
  const container = useRef(null);
  const segments = transcript.segments;

  // segmento in riproduzione: l'ultimo iniziato prima del tempo corrente
  const activeId = useMemo(() => {
    let lo = 0;
    let hi = segments.length - 1;
    let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (segments[mid].start <= time + 0.05) {
        found = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    return found >= 0 ? segments[found].id : -1;
  }, [segments, time]);

  useEffect(() => {
    if (!follow || editing || activeId < 0) return;
    const node = container.current?.querySelector(`[data-sid="${activeId}"]`);
    node?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeId, follow, editing]);

  // blocchi consecutivi dello stesso interlocutore
  const blocks = useMemo(() => {
    const out = [];
    for (const s of segments) {
      const last = out[out.length - 1];
      if (last && last.speaker === s.speaker && s.start - last.segments.at(-1).end < 30) last.segments.push(s);
      else out.push({ speaker: s.speaker, segments: [s] });
    }
    return out;
  }, [segments]);

  const speakers = useMemo(() => [...new Set(segments.map((s) => s.speaker).filter(Boolean))], [segments]);

  return (
    <div className="transcript">
      <div className="toolbar">
        <label className="check small">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Segui l'audio
        </label>
        <div className="toolbar-right">
          {speakers.length > 0 && (
            <button className="btn small ghost" onClick={() => setNames(!names)}>
              Interlocutori
            </button>
          )}
          <button className={`btn small ${editing ? "primary" : "ghost"}`} onClick={() => setEditing(!editing)}>
            <Icon name="edit" size={16} /> {editing ? "Fine" : "Modifica"}
          </button>
        </div>
      </div>

      {stale && (
        <p className="small warn">Hai modificato la trascrizione: rigenera riassunto ed estrazioni per aggiornarli.</p>
      )}
      {names && <SpeakerNames id={id} transcript={transcript} speakers={speakers} onSaved={onChange} />}

      <div ref={container}>
        {blocks.map((b) => (
          <div className="t-block" key={b.segments[0].id}>
            <div className="t-meta">
              {b.speaker && <span className={`speaker sp-${speakers.indexOf(b.speaker) % 6}`}>{speakerLabel(transcript, b.speaker)}</span>}
              <button className="ts" onClick={() => seek(b.segments[0].start)}>
                {formatTime(b.segments[0].start)}
              </button>
            </div>
            <p className="t-text">
              {b.segments.map((s) =>
                editing ? (
                  <EditableSegment key={s.id} id={id} segment={s} onSaved={onChange} />
                ) : (
                  <span
                    key={s.id}
                    data-sid={s.id}
                    className={`seg ${s.id === activeId ? "active" : ""}`}
                    onClick={() => seek(s.start)}
                  >
                    {s.text}{" "}
                  </span>
                ),
              )}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function EditableSegment({ id, segment, onSaved }) {
  const [value, setValue] = useState(segment.text);
  const [state, setState] = useState("");

  async function save() {
    if (value.trim() === segment.text) return;
    setState("saving");
    try {
      await api.patchSegment(id, segment.id, { text: value });
      setState("saved");
      onSaved();
    } catch (e) {
      setState("");
      alert(e.message);
    }
  }

  return (
    <textarea
      className={`seg-edit ${state}`}
      value={value}
      rows={Math.max(1, Math.ceil(value.length / 60))}
      onChange={(e) => setValue(e.target.value)}
      onBlur={save}
      data-sid={segment.id}
    />
  );
}

function SpeakerNames({ id, transcript, speakers, onSaved }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(speakers.map((s) => [s, transcript.speaker_names?.[s] || ""])),
  );

  async function save(e) {
    e.preventDefault();
    try {
      await api.patch(id, { speaker_names: values });
      onSaved();
    } catch (err) {
      alert(err.message);
    }
  }

  return (
    <form className="card speakers" onSubmit={save}>
      {speakers.map((s, i) => {
        const sample = transcript.segments.find((x) => x.speaker === s);
        return (
          <label key={s} className="field">
            <span className={`speaker sp-${i % 6}`}>{speakerLabel({}, s)}</span>
            <input
              placeholder="Nome"
              value={values[s]}
              onChange={(e) => setValues({ ...values, [s]: e.target.value })}
            />
            <span className="small muted">“{sample?.text.slice(0, 70)}…”</span>
          </label>
        );
      })}
      <button className="btn primary small">Salva nomi</button>
    </form>
  );
}
