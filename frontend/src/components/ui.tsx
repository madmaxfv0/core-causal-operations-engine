import React, { createContext, useContext, useEffect, useRef, useState } from "react";

import { Any, api, CONF_COLOR, STATUS_COLOR, fmt } from "../lib/api";
import { useT } from "../lib/i18n";
import { Floating, HoverCard, LAYER, useAnchorRect } from "./overlay";

export const Icon = ({ name, size = 18 }: { name: string; size?: number }) => {
  const p: Record<string, React.ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></>,
    wells: <><path d="M4 21h16" /><path d="M8 21V9l4-5 4 5v12" /><path d="M8 13h8" /></>,
    ghost: <><path d="M3 17l5-6 4 4 5-8 4 5" /><path d="M3 21h18" /></>,
    idle: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    network: <><circle cx="5" cy="6" r="2.5" /><circle cx="19" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M7 7.5l3.5 8M17 7.5l-3.5 8M7.5 6h9" /></>,
    memory: <><path d="M4 4h16v16H4z" /><path d="M8 9h8M8 13h5" /></>,
    water: <><path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" /></>,
    plan: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></>,
    archive: <><path d="M4 7h16v13H4z" /><path d="M2 4h20v3H2z" /><path d="M10 12h4" /></>,
    lab: <><path d="M9 3h6M10 3v6L4 20h16l-6-11V3" /><path d="M7 16h10" /></>,
    data: <><ellipse cx="12" cy="6" rx="8" ry="3" /><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>,
    log: <><path d="M6 3h9l5 5v13H6z" /><path d="M14 3v6h6M9 13h6M9 17h6" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>,
    why: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 1-1 1.7M12 17h.01" /></>,
    arrow: <><path d="M7 17L17 7M8 7h9v9" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
    x: <><path d="M6 6l12 12M18 6L6 18" /></>,
    play: <><path d="M7 4l12 8-12 8z" /></>,
    reset: <><path d="M3 12a9 9 0 1 0 3-6.7" /><path d="M3 4v5h5" /></>,
    sparkle: <><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /></>,
    chev: <><path d="M9 6l6 6-6 6" /></>,
    lock: <><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>,
    check: <><path d="M5 12l5 5L20 7" /></>,
    upload: <><path d="M12 16V4M6 10l6-6 6 6" /><path d="M4 20h16" /></>,
    download: <><path d="M12 4v12M6 10l6 6 6-6" /><path d="M4 20h16" /></>,
    present: <><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M12 16v4M8 20h8" /></>,
    map: <><path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.4" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{p[name] || p.info}</svg>;
};

export function Card({ title, children, action, className = "", subtitle, corner }: { title?: React.ReactNode; children?: React.ReactNode; action?: React.ReactNode; className?: string; subtitle?: React.ReactNode; corner?: { to?: string; onClick?: () => void; label: string } }) {
  return (
    <section className={`glass relative p-5 ${className}`}>
      {(title || action) && (
        <div className="flex items-start justify-between gap-3 mb-3 pr-8">
          <div><h2 className="text-[17px]">{title}</h2>{subtitle && <div className="subtle text-[12px] mt-0.5">{subtitle}</div>}</div>
          {action}
        </div>
      )}
      {corner && (corner.to ? <a className="corner-btn" href={corner.to} aria-label={corner.label} title={corner.label}><Icon name="arrow" size={16} /></a> : <button className="corner-btn" onClick={corner.onClick} aria-label={corner.label} title={corner.label}><Icon name="arrow" size={16} /></button>)}
      {children}
    </section>
  );
}

export function Badge({ label, color, small }: { label: Any; color?: string; small?: boolean }) {
  const { t } = useT();
  if (label === null || label === undefined) return null;
  const c = color || CONF_COLOR[label] || STATUS_COLOR[label] || "grey";
  // Backend status/confidence values are translated here, once, for the whole app.
  // Unknown values fall through unchanged so nothing is ever blanked out.
  const key = "bdg_" + String(label).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  const translated = t(key as Any);
  const text = translated === key ? String(label).replace(/_/g, " ") : translated;
  return <span className={`badge ${c}`} style={small ? { fontSize: 10, padding: "2px 7px" } : undefined}>{text}</span>;
}

export function Provenance({ data, label }: { data: Any; label?: string }) {
  const { t } = useT();
  if (!data) return null;
  const render = (v: Any, depth = 0): React.ReactNode => {
    if (v === null || v === undefined) return <span className="faint">—</span>;
    if (typeof v !== "object") return <span>{typeof v === "number" ? fmt.n(v, Math.abs(v) < 10 ? 3 : 0) : String(v)}</span>;
    if (Array.isArray(v)) return <span>{v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ")}</span>;
    if ("value" in v && "source" in v) return <span>{render(v.value)} <span className="faint">{v.unit}</span> <Badge label={v.source} small /></span>;
    return <div style={{ marginLeft: depth ? 10 : 0 }}>{Object.entries(v).map(([k, x]) => <div key={k} className="flex gap-2 py-0.5"><span className="faint min-w-[120px]">{k.replace(/_/g, " ")}</span><span className="flex-1">{render(x, depth + 1)}</span></div>)}</div>;
  };
  // Rendered through HoverCard: portalled to <body>, position: fixed, flip/shift
  // collision handling, and pinned on click so the values can be read.
  return (
    <HoverCard
      side="bottom" align="end" width={380} layer={LAYER.popover} label={label || t("provenance")}
      content={<div><div className="mb-2 font-semibold">{label || t("provenance")}</div><div style={{ maxHeight: 340, overflow: "auto" }}>{render(data)}</div></div>}
    >
      <span className="btn ghost icon" style={{ padding: 3 }} aria-label={label || t("provenance")}><Icon name="info" size={14} /></span>
    </HoverCard>
  );
}

export function Kpi({ label, value, unit, sub, badge, provenance, spark, trend, small }: { label: React.ReactNode; value: Any; unit?: string; sub?: React.ReactNode; badge?: React.ReactNode; provenance?: Any; spark?: number[]; trend?: number | null; small?: boolean }) {
  return (
    <div className="glass-inner p-4 flex flex-col gap-1 min-w-0">
      <div className="flex items-start justify-between gap-2"><span className="subtle text-[12px] leading-tight min-w-0">{label}</span><span className="flex items-center gap-1 shrink-0 max-w-[55%] overflow-hidden">{badge}{provenance && <Provenance data={provenance} />}</span></div>
      {trend !== undefined && trend !== null && <span className={`badge ${trend >= 0 ? "green" : "red"}`} style={{ alignSelf: "flex-start", fontSize: 10 }}>{trend >= 0 ? "↑" : "↓"} {Math.abs(trend).toFixed(1)}%</span>}
      <div className={small ? "text-[22px] font-semibold tracking-tight" : "kpi-value"}>{value}{unit && <span className="kpi-unit">{unit}</span>}</div>
      {sub && <div className="faint text-[12px] leading-tight">{sub}</div>}
      {spark && spark.length > 1 && <Sparkline data={spark} />}
    </div>
  );
}

export function Sparkline({ data, color = "#F2B632", height = 34 }: { data: number[]; color?: string; height?: number }) {
  const w = 160, h = height;
  const vals = data.filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
  if (vals.length < 2) return null;
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const pts = vals.map((v, i) => [(i / (vals.length - 1)) * w, h - 4 - ((v - min) / span) * (h - 8)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const id = "sg" + Math.random().toString(36).slice(2, 7);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none" className="mt-1" aria-hidden="true">
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity="0.35" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      <path d={`${d} L${w},${h} L0,${h} Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 4px ${color}88)` }} />
    </svg>
  );
}

export function Drawer({ open, onClose, title, children, width = 720 }: { open: boolean; onClose: () => void; title?: React.ReactNode; children?: React.ReactNode; width?: number }) {
  const { t } = useT();
  useEffect(() => { const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; if (open) document.addEventListener("keydown", h); return () => document.removeEventListener("keydown", h); }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 flex justify-end" style={{ zIndex: LAYER.drawer }} role="dialog" aria-modal="true">
      <div className="absolute inset-0" style={{ background: "rgba(5,8,16,0.55)" }} onClick={onClose} />
      <div className="glass-strong relative h-full overflow-auto drawer-enter m-3" style={{ width: `min(${width}px, 96vw)` }}>
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-4" style={{ background: "rgba(16,22,36,0.9)", backdropFilter: "blur(12px)", borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
          <h2>{title}</h2>
          <button className="btn ghost icon" onClick={onClose} aria-label={t("close")}><Icon name="x" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

// toasts
const ToastCtx = createContext<(msg: string, kind?: "ok" | "err") => void>(() => {});
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<{ id: number; msg: string; kind: string }[]>([]);
  const push = (msg: string, kind: "ok" | "err" = "ok") => { const id = Date.now() + Math.random(); setItems((s) => [...s, { id, msg, kind }]); setTimeout(() => setItems((s) => s.filter((i) => i.id !== id)), 3800); };
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-5 right-5 flex flex-col gap-2" style={{ zIndex: LAYER.toast }} aria-live="polite">
        {items.map((i) => <div key={i.id} className={`glass-strong px-4 py-3 text-[13px] fade-in flex items-center gap-2 ${i.kind === "err" ? "text-[#FFB3A8]" : ""}`}><Icon name={i.kind === "err" ? "info" : "check"} size={16} />{i.msg}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

export function Progress({ steps, label }: { steps: string[]; label?: string }) {
  return (
    <div className="glass-inner p-4 fade-in">
      <div className="flex items-center gap-2 mb-2"><span className="inline-block w-2 h-2 rounded-full bg-amber animate-pulse" /><span className="text-[13px]">{label || "Running"}</span></div>
      <ol className="text-[12px] subtle space-y-1">{steps.map((s, i) => <li key={i} className={i === steps.length - 1 ? "text-ink" : ""}>{i < steps.length - 1 ? "✓ " : "› "}{s}</li>)}</ol>
    </div>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: { key: string; label: React.ReactNode }[]; value: string; onChange: (k: string) => void }) {
  return (
    <div className="flex gap-1 flex-wrap" role="tablist">
      {tabs.map((tb) => <button key={tb.key} role="tab" aria-selected={value === tb.key} className={`chip ${value === tb.key ? "amber" : ""}`} onClick={() => onChange(tb.key)}>{tb.label}</button>)}
    </div>
  );
}

export function Empty({ text, actions }: { text: string; actions?: React.ReactNode }) {
  return <div className="glass-inner p-8 text-center subtle"><div className="mb-3">{text}</div>{actions && <div className="flex justify-center gap-2">{actions}</div>}</div>;
}

export function Skeleton({ h = 120 }: { h?: number }) { return <div className="skeleton" style={{ height: h }} />; }

export function ErrorBox({ error, onRetry }: { error: Any; onRetry?: () => void }) {
  const { t } = useT();
  const body = error?.body || {};
  return <div className="glass-inner p-5 fade-in"><div className="text-[#FFB3A8] font-medium mb-1">{t("error")}</div><div className="subtle text-[13px]">{String(error?.message || error)}</div>{body.hint && <div className="faint text-[12px] mt-1">{body.hint}</div>}{onRetry && <button className="btn sm mt-3" onClick={onRetry}>{t("retry")}</button>}</div>;
}

export function useFetch<T = Any>(url: string | null, deps: Any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Any>(null);
  const [loading, setLoading] = useState(!!url);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    setLoading(true); setError(null);
    api.get(url).then((d) => { if (alive) { setData(d); setLoading(false); } }).catch((e) => { if (alive) { setError(e); setLoading(false); } });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, tick, ...deps]);
  return { data, error, loading, reload: () => setTick((x) => x + 1), setData };
}

// human-in-the-loop decision modal
export function DecisionButtons({ recommendationId, wellId, action, confidence, module, inputs, onDone, compact }: { recommendationId: string; wellId: string; action: string; confidence?: string; module: string; inputs?: Any; onDone?: (d: Any) => void; compact?: boolean }) {
  const { t } = useT();
  const toast = useToast();
  const [open, setOpen] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const reasons = ["Operational constraint", "Safety concern", "Known field condition", "Model missing information", "Cost assumption incorrect", "Intervention unavailable", "Engineering judgement", "Other"];
  const submit = async (decision: string) => {
    setBusy(true);
    try {
      const d = await api.post("/api/decisions", { recommendation_id: recommendationId, well_id: wellId, action, decision, reason: reason || null, notes: notes || null, inputs: inputs || {}, confidence, module });
      toast(`${t("decision_saved")}: ${decision} ${wellId}`); setOpen(null); setReason(""); setNotes(""); onDone?.(d);
    } catch (e: Any) { toast(e.message, "err"); } finally { setBusy(false); }
  };
  return (
    <div>
      <div className="flex gap-2 flex-wrap">
        <button className={`btn primary ${compact ? "sm" : ""}`} onClick={() => submit("ACCEPT")} disabled={busy}>{t("accept")}</button>
        <button className={`btn ${compact ? "sm" : ""}`} onClick={() => setOpen("MODIFY")} disabled={busy}>{t("modify")}</button>
        <button className={`btn danger ${compact ? "sm" : ""}`} onClick={() => setOpen("REJECT")} disabled={busy}>{t("reject")}</button>
        <button className={`btn ghost ${compact ? "sm" : ""}`} onClick={() => submit("DEFER")} disabled={busy}>{t("defer")}</button>
      </div>
      {open && (
        <div className="glass-inner p-4 mt-3 fade-in">
          <div className="text-[13px] mb-2 font-medium">{open === "REJECT" ? t("reject") : t("modify")} — {wellId}</div>
          <select value={reason} onChange={(e) => setReason(e.target.value)} className="w-full mb-2" aria-label={t("reason")}><option value="">{t("reason")}…</option>{reasons.map((r) => <option key={r} value={r}>{r}</option>)}</select>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="w-full mb-2" rows={2} placeholder={t("notes")} />
          <div className="flex gap-2"><button className="btn primary sm" disabled={busy || (open === "REJECT" && !reason)} onClick={() => submit(open)}>{t("confirm")}</button><button className="btn ghost sm" onClick={() => setOpen(null)}>{t("cancel")}</button></div>
        </div>
      )}
    </div>
  );
}

export function LabeledValue({ label, value, sub }: { label: React.ReactNode; value: React.ReactNode; sub?: React.ReactNode }) {
  return <div><div className="faint text-[11px]">{label}</div><div className="text-[14px] font-medium">{value}</div>{sub && <div className="faint text-[11px]">{sub}</div>}</div>;
}

export function RangeText({ lo, mid, hi, unit, d = 0 }: { lo: Any; mid: Any; hi: Any; unit?: string; d?: number }) {
  const { t } = useT();
  return <span><span className="font-semibold">{fmt.n(mid, d)}</span>{unit && <span className="faint text-[11px]"> {unit}</span>} <span className="faint text-[11px]">· {t("range")} {fmt.range(lo, hi, d)}</span></span>;
}
