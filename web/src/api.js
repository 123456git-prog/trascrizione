// Client delle API del server Python. Nessuna chiave API passa mai dal browser.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(path, { credentials: "same-origin", ...options });
  } catch {
    throw new ApiError("Server non raggiungibile. È acceso? Sei sulla stessa rete Wi-Fi?", 0);
  }
  if (res.status === 401 && path !== "/api/login") {
    window.dispatchEvent(new Event("auth-required"));
  }
  if (!res.ok) {
    let detail = `Errore ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* risposta non JSON */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return null;
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.text();
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  session: () => request("/api/session"),
  login: (password) => request("/api/login", json("POST", { password })),
  list: (q = "") => request(`/api/recordings${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  get: (id) => request(`/api/recordings/${id}`),
  status: (id) => request(`/api/recordings/${id}/status`),
  remove: (id) => request(`/api/recordings/${id}`, { method: "DELETE" }),
  patch: (id, body) => request(`/api/recordings/${id}`, json("PATCH", body)),
  patchSegment: (id, sid, body) => request(`/api/recordings/${id}/segments/${sid}`, json("PATCH", body)),
  analyze: (id, body) => request(`/api/recordings/${id}/analyze`, json("POST", body)),
  summary: (id, body) => request(`/api/recordings/${id}/summary`, json("POST", body)),
  transcribe: (id, body = {}) => request(`/api/recordings/${id}/transcribe`, json("POST", body)),
  ask: (id, body) => request(`/api/recordings/${id}/ask`, json("POST", body)),
  templates: () => request("/api/templates"),
  createTemplate: (description, provider) =>
    request("/api/templates", json("POST", { description, provider })),
  deleteTemplate: (id) => request(`/api/templates/${id}`, { method: "DELETE" }),
  providers: () => request("/api/providers"),
  info: () => request("/api/info"),
  audioUrl: (id) => `/api/recordings/${id}/audio`,
  exportUrl: (id, format = "md", template) =>
    `/api/recordings/${id}/export?format=${format}${template ? `&template=${template}` : ""}`,

  // caricamento con avanzamento (fetch non lo espone, XMLHttpRequest sì)
  upload(file, fields, onProgress) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append("file", file, file.name);
      Object.entries(fields).forEach(([k, v]) => form.append(k, String(v)));
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/recordings");
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
      xhr.onload = () => {
        let body = {};
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* vuoto */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body);
        else reject(new ApiError(body.detail || `Errore ${xhr.status}`, xhr.status));
      };
      xhr.onerror = () => reject(new ApiError("Caricamento interrotto: controlla la connessione.", 0));
      xhr.send(form);
    });
  },
};

export function formatTime(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

export function formatDate(iso) {
  return new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric" });
}

export const ACTIVE = ["in coda", "trascrizione", "analisi"];

export function speakerLabel(transcript, speaker) {
  if (!speaker) return "";
  if (transcript.speaker_names?.[speaker]) return transcript.speaker_names[speaker];
  const m = /^SPEAKER_(\d+)$/.exec(speaker);
  return m ? `Interlocutore ${Number(m[1]) + 1}` : speaker;
}
