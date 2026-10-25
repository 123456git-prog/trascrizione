import { useMemo } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

// Il testo arriva da un modello linguistico: viene sempre ripulito prima di mostrarlo.
export default function Markdown({ text, className = "" }) {
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(text || "", { breaks: false })), [text]);
  return <div className={`md ${className}`} dangerouslySetInnerHTML={{ __html: html }} />;
}
