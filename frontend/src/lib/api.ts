export type Any = any;

async function handle(r: Response) {
  const text = await r.text();
  let body: Any = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { error: text }; }
  if (!r.ok) {
    const msg = body?.error || body?.detail || `Request failed (${r.status})`;
    const err: Any = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = r.status; err.body = body;
    throw err;
  }
  return body;
}

export const api = {
  get: (url: string) => fetch(url).then(handle),
  post: (url: string, body?: Any) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) }).then(handle),
  put: (url: string, body: Any) => fetch(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(handle),
  del: (url: string) => fetch(url, { method: "DELETE" }).then(handle),
  upload: (url: string, file: File, fields: Record<string, string> = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
    return fetch(url, { method: "POST", body: fd }).then(handle);
  },
  async job(jobId: string, onStep?: (steps: string[]) => void): Promise<Any> {
    for (let i = 0; i < 600; i++) {
      const j = await api.get(`/api/jobs/${jobId}`);
      onStep?.(j.steps || []);
      if (j.status === "COMPLETE") return j.result;
      if (j.status === "FAILED") throw new Error(j.error || "Analysis failed");
      await new Promise((r) => setTimeout(r, 450));
    }
    throw new Error("Timed out waiting for the analysis");
  },
};

export const fmt = {
  n: (v: Any, d = 0) => (v === null || v === undefined || Number.isNaN(Number(v))) ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }),
  n1: (v: Any) => fmt.n(v, 1),
  money: (v: Any) => (v === null || v === undefined || Number.isNaN(Number(v))) ? "—" : (Math.abs(v) >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : Math.abs(v) >= 1e4 ? `$${(v / 1e3).toFixed(0)}k` : `$${Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`),
  pct: (v: Any, d = 0) => (v === null || v === undefined || Number.isNaN(Number(v))) ? "—" : `${(Number(v) * 100).toFixed(d)}%`,
  range: (lo: Any, hi: Any, d = 0) => (lo === null || lo === undefined || hi === null || hi === undefined) ? "—" : `${fmt.n(lo, d)}–${fmt.n(hi, d)}`,
  date: (s: Any) => (s ? String(s).slice(0, 16).replace("T", " ") : "—"),
};

export function toCSV(rows: Any[], columns?: string[]): string {
  if (!rows.length) return "";
  const cols = columns || Object.keys(rows[0]).filter((k) => typeof rows[0][k] !== "object" || rows[0][k] === null);
  const esc = (v: Any) => { const s = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}

export function download(name: string, content: string | Blob, type = "text/csv") {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function exportSvgAsPng(container: HTMLElement | null, name: string) {
  const svg = container?.querySelector("svg");
  if (!svg) return;
  const xml = new XMLSerializer().serializeToString(svg);
  const img = new Image();
  const w = svg.clientWidth || 800, h = svg.clientHeight || 400;
  img.onload = () => {
    const c = document.createElement("canvas"); c.width = w * 2; c.height = h * 2;
    const g = c.getContext("2d")!; g.scale(2, 2); g.fillStyle = "#0C1220"; g.fillRect(0, 0, w, h); g.drawImage(img, 0, 0, w, h);
    c.toBlob((b) => b && download(name, b, "image/png"));
  };
  img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(xml)));
}

export const ls = {
  get<T>(k: string, d: T): T { try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : d; } catch { return d; } },
  set(k: string, v: Any) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ignore */ } },
};

export const CONF_COLOR: Record<string, string> = { "HIGH CONFIDENCE": "green", "MODERATE CONFIDENCE": "amber", "LOW CONFIDENCE": "red", "INSUFFICIENT EVIDENCE": "grey" };
export const STATUS_COLOR: Record<string, string> = { ACT: "green", TEST: "blue", REVIEW: "amber", WAIT: "grey", "DO NOT PRIORITISE": "red", "INSUFFICIENT DATA": "grey", producing: "green", idle: "grey", recently_stopped: "amber", never_produced: "grey", CONFIRMED: "green", "STRONG INFERENCE": "blue", HYPOTHESIS: "amber", UNVERIFIED: "grey", CALCULATED: "grey", MANUAL: "blue", ACCEPT: "green", MODIFY: "amber", REJECT: "red", DEFER: "grey", approved: "green", edited: "green", rejected: "red", unreadable: "grey", pending: "amber" };

/**
 * Live source names for the provenance registry, read once from the data context
 * so an "i" icon always names the data set actually in use rather than a constant.
 */
let _srcCache: { dataset: string; alberta: string } = { dataset: "—", alberta: "AER ST37 / Petrinex (public)" };
export function primeDataSource() {
  api.get("/api/data/context").then((c: Any) => {
    const ab = c?.alberta_public?.domains || {};
    _srcCache = {
      dataset: c?.dataset?.label || c?.dataset?.name || "—",
      alberta: [ab.wells?.source, ab.production?.source].filter(Boolean).join(" · ") || "AER / Petrinex (public)",
    };
  }).catch(() => {});
}
export const useDataSource = () => _srcCache;


/**
 * Intervention type names arrive from the data set as raw values
 * (pump_replacement, cleanout, …). Translate them through the same
 * key-with-fallback rule used for badges so an unknown type still renders.
 */
export function iType(t: (k: Any) => string, value: Any): string {
  if (value === null || value === undefined) return "";
  const raw = String(value);
  const key = "itype_" + raw.toLowerCase().trim().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  const out = t(key as Any);
  return out === key ? raw.replace(/_/g, " ") : out;
}
