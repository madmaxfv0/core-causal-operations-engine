import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Any, api, ls } from "../lib/api";
import { Lang, useT } from "../lib/i18n";
import { Badge, Icon, useToast } from "./ui";
import { Dropdown, HoverCard, LAYER, Tip } from "./overlay";
import { DataContextChip } from "./DataContext";
import { DataModeSwitch } from "./DataMode";

type Meta = Any;
const AppCtx = createContext<{ meta: Meta; field: string; setField: (f: string) => void; role: string; setRole: (r: string) => void; reloadMeta: () => void; openCopilot: (q?: string) => void }>({ meta: null, field: "", setField: () => {}, role: "prod", setRole: () => {}, reloadMeta: () => {}, openCopilot: () => {} });
export const useApp = () => useContext(AppCtx);

const NAV = [
  { to: "/", icon: "grid", key: "nav_overview" },
  // Always one click away from anywhere in the app — no hover flyout to hunt through.
  // The Alberta map is also still reachable from the Wells group below, unchanged.
  { to: "/map", icon: "map", key: "nav_alberta_map" },
  { to: "/wells", icon: "wells", key: "nav_wells", group: "nav_field", children: [["/wells", "nav_wells"], ["/map", "Alberta map"], ["/ghost", "nav_ghost"], ["/idle", "nav_idle"], ["/network", "nav_network"]] },
  { to: "/interventions", icon: "memory", key: "nav_memory", group: "nav_interventions", children: [["/interventions", "nav_memory"], ["/interventions/compare", "nav_compare"]] },
  { to: "/water", icon: "water", key: "nav_water_econ", group: "nav_water", children: [["/water", "nav_water_econ"]] },
  { to: "/portfolio", icon: "plan", key: "nav_portfolio", group: "nav_planning", children: [["/portfolio", "nav_portfolio"], ["/portfolio/scenarios", "nav_scenarios"]] },
  { to: "/archive", icon: "archive", key: "nav_archive", group: "nav_intelligence", children: [["/archive", "nav_archive"], ["/archive/ask", "nav_ask"]] },
  { to: "/model-lab", icon: "lab", key: "nav_modellab", group: "nav_validation", children: [["/model-lab", "nav_modellab"], ["/model-lab/blind", "nav_blind"], ["/quality", "nav_quality"]] },
  { to: "/decisions", icon: "log", key: "nav_decisions", group: "nav_governance", children: [["/decisions", "nav_decisions"], ["/runs", "nav_runs"], ["/settings", "nav_settings"]] },
  { to: "/why", icon: "why", key: "nav_why" },
];

const ROLE_HOME: Record<string, string> = { exec: "/", prod: "/wells", field: "/idle", ds: "/model-lab", admin: "/" };

export function Shell({ children }: { children: React.ReactNode }) {
  const { t, lang, setLang } = useT();
  const nav = useNavigate();
  const loc = useLocation();
  const toast = useToast();
  const [meta, setMeta] = useState<Meta>(null);
  const [field, setFieldState] = useState<string>(ls.get("core.field", ""));
  const [role, setRoleState] = useState<string>(ls.get("core.role", "prod"));
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Any>(null);
  const [copilot, setCopilot] = useState<{ open: boolean; q: string; answer?: Any; busy?: boolean }>({ open: false, q: "" });
  const searchRef = useRef<HTMLDivElement>(null);
  const reloadMeta = () => api.get("/api/meta").then(setMeta).catch(() => {});
  useEffect(() => { reloadMeta(); }, []);
  useEffect(() => { const h = (e: MouseEvent) => { if (searchRef.current && !searchRef.current.contains(e.target as Node)) setResults(null); }; document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  const setField = (f: string) => { setFieldState(f); ls.set("core.field", f); };
  const setRole = (r: string) => { setRoleState(r); ls.set("core.role", r); nav(ROLE_HOME[r] || "/"); };
  const doSearch = async () => { if (!q.trim()) return; setResults(await api.get(`/api/search?q=${encodeURIComponent(q)}`)); };
  const openCopilot = (question?: string) => { setCopilot({ open: true, q: question || copilot.q }); if (question) askCopilot(question); };
  const askCopilot = async (question: string) => { setCopilot((c) => ({ ...c, open: true, q: question, busy: true })); try { const a = await api.post("/api/copilot/ask", { question }); setCopilot((c) => ({ ...c, answer: a, busy: false })); } catch (e: Any) { toast(e.message, "err"); setCopilot((c) => ({ ...c, busy: false })); } };
  const presenting = loc.pathname.startsWith("/present");
  const isSynthetic = meta?.data_mode?.includes("SYNTHETIC");
  return (
    <AppCtx.Provider value={{ meta, field, setField, role, setRole, reloadMeta, openCopilot }}>
      {/* Chart paint servers, defined once at document level.
          Recharts silently drops a custom <Defs/> component passed as a chart child, which
          left every area fill pointing at a missing gradient id and rendering solid black.
          SVG paint references resolve document-wide, so defining them here fixes all charts. */}
      <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }} focusable="false">
        <defs>
          <linearGradient id="gAmber" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#F2B632" stopOpacity={0.55} />
            <stop offset="100%" stopColor="#F2B632" stopOpacity={0.04} />
          </linearGradient>
          <linearGradient id="gBlue" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4F6BE8" stopOpacity={0.5} />
            <stop offset="100%" stopColor="#4F6BE8" stopOpacity={0.03} />
          </linearGradient>
          <linearGradient id="gBand" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#B7C4FF" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#B7C4FF" stopOpacity={0.06} />
          </linearGradient>
          <linearGradient id="gGreen" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5CC489" stopOpacity={0.45} />
            <stop offset="100%" stopColor="#5CC489" stopOpacity={0.03} />
          </linearGradient>
          <pattern id="hatch" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" stroke="#E4614F" strokeWidth="2.5" strokeOpacity="0.7" />
          </pattern>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2.2" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
      </svg>
      {presenting ? <>{children}</> : (
        <div className="flex min-h-screen">
          <nav className="glass flex flex-col items-center py-3 gap-1 m-3 mr-0 sticky top-3 self-start" style={{ width: 64, height: "calc(100vh - 24px)" }} aria-label={t("x_primary")}>
            <NavLink to="/" className="mb-3 mt-1" aria-label="CORE"><img src="/favicon.svg" width="34" height="34" alt="CORE" style={{ borderRadius: 10 }} /></NavLink>
            {NAV.map((n) => {
              const active = n.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(n.to) || (n.children || []).some(([p]) => loc.pathname === p);
              const tip = n.group
                ? <div className="rail-label"><b>{t(n.group as Any)}</b>{(n.children || []).map(([p, k]) => <div key={p} className={loc.pathname === p ? "text-amber" : "subtle"}>{t(k as Any)}</div>)}</div>
                : <span className="rail-label">{t(n.key as Any)}</span>;
              return (
                <HoverCard key={n.to} content={tip} side="right" align="center" width="auto" pinnable={false} layer={LAYER.tooltip}>
                  <NavLink to={n.to} className={`rail-btn ${active ? "active" : ""}`} aria-label={t(n.key as Any)}>
                    <Icon name={n.icon} />
                  </NavLink>
                </HoverCard>
              );
            })}
            <span className="flex-1" />
            <Tip label={t("g_title")} side="right"><NavLink to="/guide" className={`rail-btn ${loc.pathname === "/guide" ? "active" : ""}`} aria-label={t("g_title")}><Icon name="why" /></NavLink></Tip>
            <Tip label={t("presentation")} side="right"><NavLink to="/present" className="rail-btn" aria-label={t("presentation")}><Icon name="present" /></NavLink></Tip>
            <Tip label={t("nav_settings")} side="right"><NavLink to="/settings" className={`rail-btn ${loc.pathname === "/settings" ? "active" : ""}`} aria-label={t("nav_settings")}><Icon name="settings" /></NavLink></Tip>
          </nav>
          <div className="flex-1 min-w-0 p-3 pl-4">
            <header className="flex flex-wrap items-center gap-2 mb-4">
              <div className="chip"><Icon name="sparkle" size={15} /><span className="font-semibold">CORE</span><span className="faint hidden md:inline">{t("x_core_full")}</span></div>
              <DataModeSwitch />
              <DataContextChip onChanged={reloadMeta} />
              <select className="chip" value={field} onChange={(e) => setField(e.target.value)} aria-label={t("field")} style={{ paddingRight: 28 }}><option value="">{t("field_all")}</option>{(meta?.fields || []).map((f: string) => <option key={f} value={f}>{f}</option>)}</select>
              {meta && <span className="chip faint">{meta.date_range?.[0]} → {meta.date_range?.[1]}</span>}
              <div ref={searchRef} className="relative flex-1 min-w-[220px] max-w-[440px]">
                <span className="absolute left-3 top-2.5 faint"><Icon name="search" size={15} /></span>
                <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && doSearch()} placeholder={t("search_placeholder")} className="w-full pl-9" aria-label={t("search")} />
                <Dropdown open={!!results} onClose={() => setResults(null)} anchorRef={searchRef}>
                  <div className="text-[13px]">
                    {results && !results.wells.length && !results.interventions.length && !results.documents.length && <div className="subtle">{t("no_results")}</div>}
                    {(results?.wells || []).map((w: Any) => <button key={w.well_id} className="block w-full text-left py-1.5 px-2 rounded-lg hover:bg-white/10" onClick={() => { nav(`/wells/${w.well_id}`); setResults(null); }}><span className="font-medium">{w.well_id}</span> <span className="faint">{w.field} · {w.status}</span></button>)}
                    {(results?.interventions || []).map((i: Any) => <button key={i.intervention_id} className="block w-full text-left py-1.5 px-2 rounded-lg hover:bg-white/10" onClick={() => { nav(`/interventions/${i.intervention_id}`); setResults(null); }}><span className="font-medium">{i.intervention_id}</span> <span className="faint">{i.well_id} · {i.type} · {i.date}</span></button>)}
                    {(results?.documents || []).map((d: Any) => <button key={d.document_id} className="block w-full text-left py-1.5 px-2 rounded-lg hover:bg-white/10" onClick={() => { nav(`/archive?doc=${d.document_id}`); setResults(null); }}><span className="font-medium">{d.file_name}</span> <span className="faint">{d.well_id} · {d.intervention_type}</span></button>)}
                  </div>
                </Dropdown>
              </div>
              <select className="chip" value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label={t("language")}><option value="en">EN</option><option value="ru">RU</option><option value="az">AZ</option></select>
              <select className="chip" value={role} onChange={(e) => setRole(e.target.value)} aria-label={t("role")}><option value="exec">{t("role_exec")}</option><option value="prod">{t("role_prod")}</option><option value="field">{t("role_field")}</option><option value="ds">{t("role_ds")}</option><option value="admin">{t("role_admin")}</option></select>
              <button className="btn" onClick={() => openCopilot()} aria-label={t("copilot")}><Icon name="sparkle" size={15} />{t("copilot")}</button>
            </header>
            {meta?.evidence_stale && loc.pathname !== "/settings" && <div className="glass-inner px-4 py-2 mb-3 text-[12px] flex items-center gap-3"><Badge label="stale" color="amber" /><span>{t("stale")}</span><NavLink to="/settings" className="btn sm">{t("rebuild")}</NavLink></div>}
            <main className="fade-in" key={loc.pathname}>{children}</main>
          </div>
          {copilot.open && (
            <aside className="glass-strong fixed right-3 bottom-3 top-3 flex flex-col drawer-enter" style={{ width: "min(440px, 94vw)", zIndex: LAYER.drawer }} aria-label={t("copilot")}>
              <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}><div className="flex items-center gap-2"><Icon name="sparkle" size={16} /><b>{t("copilot")}</b></div><button className="btn ghost icon" onClick={() => setCopilot({ ...copilot, open: false })} aria-label={t("close")}><Icon name="x" /></button></div>
              <div className="p-4 flex-1 overflow-auto text-[13px]">
                <div className="faint mb-3">{t("x_copilot_note")}</div>
                <div className="flex flex-wrap gap-1 mb-3">{["Why is SYN-050 ranked above SYN-032?", "What happened the last times we did water shutoff?", "Why was SYN-031 flagged?"].map((s) => <button key={s} className="chip" style={{ fontSize: 11 }} onClick={() => askCopilot(s)}>{s}</button>)}</div>
                {copilot.busy && <div className="skeleton" style={{ height: 80 }} />}
                {copilot.answer && !copilot.busy && (
                  <div className="glass-inner p-3 space-y-2 fade-in">
                    <div>{copilot.answer.answer_rephrased || copilot.answer.answer}</div>
                    {copilot.answer.recommendation && <div><div className="faint">{t("x_recommendation")}</div>{copilot.answer.recommendation}</div>}
                    {copilot.answer.evidence && <div><div className="faint">{t("x_evidence")}</div><ul className="list-disc ml-4">{(Array.isArray(copilot.answer.evidence) ? copilot.answer.evidence : []).map((e: Any, i: number) => <li key={i}>{typeof e === "string" ? e : JSON.stringify(e)}</li>)}</ul></div>}
                    {copilot.answer.uncertainty && <div><div className="faint">{t("x_uncertainty")}</div>{copilot.answer.uncertainty}</div>}
                    {copilot.answer.comparable_wells?.length > 0 && <div><div className="faint">{t("x_comparable")}</div>{copilot.answer.comparable_wells.map((w: string) => <button key={w} className="chip mr-1 mb-1" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => nav(`/wells/${w}`)}>{w}</button>)}</div>}
                    {copilot.answer.economic_assumptions && <div><div className="faint">{t("x_econ_assump")}</div>{copilot.answer.economic_assumptions}</div>}
                    {copilot.answer.source_documents?.length > 0 && <div><div className="faint">{t("x_src_docs")}</div>{copilot.answer.source_documents.map((d: Any) => <button key={d.document_id} className="chip mr-1 mb-1" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => nav(`/archive?doc=${d.document_id}`)}>{d.file_name}</button>)}</div>}
                    <div className="faint text-[11px]">mode: {copilot.answer.mode}</div>
                  </div>
                )}
              </div>
              <div className="p-3 flex gap-2" style={{ borderTop: "1px solid rgba(255,255,255,0.1)" }}><input className="flex-1" value={copilot.q} onChange={(e) => setCopilot({ ...copilot, q: e.target.value })} onKeyDown={(e) => e.key === "Enter" && askCopilot(copilot.q)} placeholder={t("x_why_rank")} /><button className="btn primary" onClick={() => askCopilot(copilot.q)} disabled={copilot.busy || !copilot.q.trim()}>Ask</button></div>
            </aside>
          )}
        </div>
      )}
    </AppCtx.Provider>
  );
}
