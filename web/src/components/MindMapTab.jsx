import { useEffect, useRef, useState } from "react";
import { Transformer } from "markmap-lib";
import { Markmap } from "markmap-view";

const transformer = new Transformer();

export default function MindMapTab({ analysis }) {
  const maps = analysis?.mindmaps || {};
  const keys = Object.keys(maps);
  const [selected, setSelected] = useState(analysis?.last_template && maps[analysis.last_template] ? analysis.last_template : keys[0]);
  const svg = useRef(null);
  const mm = useRef(null);

  useEffect(() => {
    if (!svg.current || !maps[selected]) return;
    const { root } = transformer.transform(maps[selected]);
    if (!mm.current) mm.current = Markmap.create(svg.current, { autoFit: true, duration: 300, spacingVertical: 8 });
    mm.current.setData(root);
    mm.current.fit();
  }, [selected, maps]);

  useEffect(() => () => mm.current?.destroy(), []);

  if (!keys.length) return <p className="muted empty">La mappa mentale viene creata insieme al riassunto.</p>;

  return (
    <div className="mindmap">
      {keys.length > 1 && (
        <div className="toolbar">
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {keys.map((k) => (
              <option key={k} value={k}>
                {analysis.summaries?.[k]?.template_name || k}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="card mindmap-box">
        <svg ref={svg} />
      </div>
      <p className="small muted center">Trascina per spostarti, pizzica o usa la rotellina per lo zoom, tocca un nodo per chiuderlo.</p>
    </div>
  );
}
