import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bars, C, Tornado } from "../charts";
import { DataTable } from "../components/DataTable";
import { useApp } from "../components/Shell";
import { Badge, Card, Drawer, ErrorBox, Icon, Kpi, Skeleton, useFetch, useToast } from "../components/ui";
import { Any, api, download, fmt, ls, toCSV } from "../lib/api";
import { useProv } from "../lib/provenance";
import { useT } from "../lib/i18n";

const OBJ = ["npv", "oil", "cash", "water", "balanced", "custom"];

export function Portfolio() {
  const prov = useProv();
  const { t } = useT();
  const { field, meta } = useApp();
  const nav = useNavigate();
  const toast = useToast();
  const base = meta?.settings?.portfolio;
  const [cons, setCons] = useState<Any>(ls.get("core.portfolio.cons", { budget: 1000000, crews: 2, rigs: 1, horizon_months: 12, max_concurrent: 6, min_npv: 0, risk_tolerance: 0.6 }));
  const [objective, setObjective] = useState(ls.get("core.portfolio.obj", "npv"));
  const [weights, setWeights] = useState<Any>({ economic: 0.4, production: 0.2, water: 0.1, confidence: 0.2, urgency: 0.1 });
  const [plan, setPlan] = useState<Any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Any>(null);
  const [compare, setCompare] = useState<Any>(null);
  const [tornado, setTornado] = useState<Any>(null);
  const [manual, setManual] = useState<Any>(null);
  const [scenarios, setScenarios] = useState<Any[]>([]);
  const [over, setOver] = useState<number | null>(null);
  const timer = useRef<Any>(null);
  useEffect(() => { if (base && !ls.get("core.portfolio.cons", null)) setCons({ ...base }); /* eslint-disable-next-line */ }, [meta]);
  const optimise = async (c = cons, o = objective) => {
    setBusy(true); setError(null);
    try { const p = await api.post("/api/portfolio/optimise", { ...c, objective: o, weights: o === "custom" ? weights : undefined, field: field || undefined }); setPlan(p); const cd = await api.get("/api/portfolio/candidates"); setScenarios(cd.scenarios || []); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  useEffect(() => { optimise(); /* eslint-disable-next-line */ }, [field]);
  const setC = (k: string, v: Any) => { const c = { ...cons, [k]: v }; setCons(c); ls.set("core.portfolio.cons", c); clearTimeout(timer.current); timer.current = setTimeout(() => optimise(c, objective), 350); };
  const setObj = (o: string) => { setObjective(o); ls.set("core.portfolio.obj", o); optimise(cons, o); };
  const planEdit = async (body: Any) => { await api.post("/api/portfolio/plan-state", body); await optimise(); };
  const lock = (job: Any) => { const locked = { ...(planState().locked || {}) }; if (job.locked) delete locked[job.candidate_id]; else locked[job.candidate_id] = job.quarter; planEdit({ locked }); };
  const remove = (job: Any) => planEdit({ removed: [...(planState().removed || []), job.candidate_id] });
  const planState = () => ({ locked: Object.fromEntries((plan?.selected || []).filter((s: Any) => s.locked).map((s: Any) => [s.candidate_id, s.quarter])), removed: (plan?.excluded || []).filter((e: Any) => e.excluded_reason === "removed by user").map((e: Any) => e.candidate_id), moves: Object.fromEntries((plan?.selected || []).filter((s: Any) => s.moved).map((s: Any) => [s.candidate_id, s.quarter])) });
  const drop = (q: number, cid: string) => { const moves = { ...planState().moves, [cid]: q }; setOver(null); planEdit({ moves }); };
  const restore = (cid: string) => planEdit({ removed: planState().removed.filter((x: string) => x !== cid) });
  const resetPlan = async () => { await api.post("/api/portfolio/plan-state", { reset: true }); const c = { ...(base || cons) }; setCons(c); ls.set("core.portfolio.cons", c); setObjective("npv"); await optimise(c, "npv"); toast(t("reset") + " ✓"); };
  const saveScenario = async (dup = false) => { const name = prompt(t("scenario_name"), dup ? `Copy of ${scenarios[scenarios.length - 1]?.name || "scenario"}` : `Budget ${fmt.money(cons.budget)} · ${objective}`); if (!name) return; await api.post("/api/portfolio/scenarios", { name, budget: cons.budget, constraints: cons, objective, plan }); toast(t("saved")); const cd = await api.get("/api/portfolio/candidates"); setScenarios(cd.scenarios); };
  const exportPlan = () => download("core_plan.csv", toCSV((plan?.selected || []).map((s: Any) => ({ quarter: `Q${s.quarter + 1}`, candidate_id: s.candidate_id, well_id: s.well_id, action: s.action, cost: s.cost, npv: s.npv, npv_lo: s.npv_lo, npv_hi: s.npv_hi, oil_bpd: s.oil_bpd, water_bpd: s.water_bpd, duration_months: s.duration_months, crew_type: s.crew_type, risk: s.risk, confidence: s.confidence, locked: s.locked }))));
  const doCompare = async () => setCompare(await api.post("/api/portfolio/compare", { ...cons, objective, field: field || undefined }));
  const doTornado = async () => { setTornado("busy"); setTornado(await api.post("/api/portfolio/sensitivity", { ...cons, objective })); };
  const addManual = async () => { try { await api.post("/api/portfolio/manual-job", manual); setManual(null); toast(t("saved")); optimise(); } catch (e: Any) { toast(e.message, "err"); } };
  const k = plan?.kpi;
  const Q = plan?.quarters || 4;
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: "minmax(280px, 340px) minmax(0, 1fr)" }}>
      <div className="grid gap-3 content-start">
        <Card title={t("pf_title")}>
          <label className="block text-[12px] mb-1 subtle">{t("budget")} · <b className="text-ink">{fmt.money(cons.budget)}</b></label>
          <input type="range" min={0} max={3000000} step={25000} value={cons.budget} onChange={(e) => setC("budget", Number(e.target.value))} className="w-full" aria-label={t("budget")} />
          <div className="grid grid-cols-2 gap-2 mt-3 text-[12px]">
            {([["crews", 0, 10, 1], ["rigs", 0, 5, 1], ["horizon_months", 3, 24, 3], ["max_concurrent", 1, 12, 1], ["min_npv", -100000, 500000, 10000], ["risk_tolerance", 0, 1, 0.05]] as [string, number, number, number][]).map(([kk, mn, mx, st]) => <label key={kk} className="flex flex-col gap-1"><span className="faint">{t(kk as Any)}</span><input type="number" min={mn} max={mx} step={st} value={cons[kk]} onChange={(e) => setC(kk, Number(e.target.value))} /></label>)}
          </div>
          <label className="block text-[12px] mt-3 faint">{t("objective")}</label>
          <select value={objective} onChange={(e) => setObj(e.target.value)} className="w-full">{OBJ.map((o) => <option key={o} value={o}>{t(`obj_${o}` as Any)}</option>)}</select>
          {objective === "custom" && <div className="grid grid-cols-2 gap-2 mt-2 text-[11px]">{Object.entries(weights).map(([kk, v]: Any) => <label key={kk} className="flex flex-col"><span className="faint">{kk}</span><input type="number" step={0.05} min={0} max={1} value={v} onChange={(e) => setWeights({ ...weights, [kk]: Number(e.target.value) })} onBlur={() => optimise()} /></label>)}</div>}
          <div className="flex flex-wrap gap-2 mt-4">
            <button className="btn primary" onClick={() => optimise()} disabled={busy}><Icon name="play" size={14} />{t("optimise")}</button>
            <button className="btn" onClick={() => setManual({ well_id: "", action: "cleanout", cost: 30000, npv: 0, oil_bpd: 0, water_bpd: 0, duration_months: 1, crew_type: "rigless", risk: 0.5 })}>{t("add_manual")}</button>
            <button className="btn" onClick={doCompare}>{t("compare_plan")}</button>
            <button className="btn" onClick={() => saveScenario(false)}>{t("save_scenario")}</button>
            <button className="btn" onClick={() => saveScenario(true)}>{t("duplicate_scenario")}</button>
            <button className="btn" onClick={resetPlan}><Icon name="reset" size={13} />{t("reset")}</button>
            <button className="btn" onClick={exportPlan} disabled={!plan}><Icon name="download" size={13} />{t("export_plan")}</button>
            <button className="btn" onClick={doTornado}>{t("tornado")}</button>
          </div>
        </Card>
        {scenarios.length > 0 && <Card title={t("nav_scenarios")} corner={{ to: "/portfolio/scenarios", label: t("nav_scenarios") }}><div className="space-y-1 text-[12px]">{scenarios.slice(-5).reverse().map((s: Any) => <div key={s.scenario_id} className="glass-inner px-3 py-2 flex justify-between"><span>{s.name}</span><span className="faint">{fmt.money(s.plan_kpi?.expected_value)}</span></div>)}</div></Card>}
        {tornado && tornado !== "busy" && <Card title={t("tornado")}><Tornado rows={tornado.tornado} /><div className="faint text-[11px]">{tornado.note}</div></Card>}
      </div>
      <div className="grid gap-3 content-start">
        {error && <ErrorBox error={error} onRetry={() => optimise()} />}
        {!plan && !error && <Skeleton h={300} />}
        {plan && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Kpi label={t("available")} value={k.available} small sub={`${k.eligible} eligible · ${t("candidate_cost")} ${fmt.money(k.total_candidate_cost)}`} />
              <Kpi label={t("selected")} value={k.selected} small sub={`${fmt.money(k.investment)} of ${fmt.money(k.budget)}`} badge={busy ? <span className="badge amber">…</span> : <Badge label={plan.status} small color={plan.status === "Optimal" ? "green" : "red"} />} />
              <Kpi label={t("expected_value")} provenance={prov("expected_value")} value={fmt.money(k.expected_value)} small sub={`${t("range")} ${fmt.money(k.value_lo)} – ${fmt.money(k.value_hi)}`} badge={<Badge label={t("illustrative_short")} color="amber" small />} />
              <Kpi label={t("oil_uplift")} provenance={prov("oil_uplift")} value={`+${fmt.n(k.expected_oil_bpd)}`} unit="bbl/d" small sub={`${t("water_reduction_kpi")} −${fmt.n(k.expected_water_reduction_bpd)} bbl/d`} />
              <Kpi label={t("avoided")} provenance={prov("avoided")} value={fmt.money(k.avoided_poor_spend)} small sub={`${t("crew_util")} ${fmt.pct(k.crew_utilisation)} · ${t("rig_util")} ${fmt.pct(k.rig_utilisation)}`} />
            </div>
            {plan.conflicts?.length > 0 && <div className="glass-inner p-3 text-[12px] text-[#FFB3A8]"><b>{t("conflicts")}:</b> {plan.conflicts.join(" · ")}</div>}
            <Card title={t("schedule")} subtitle={t("drag_hint")}>
              <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Q}, minmax(0, 1fr))` }}>
                {Array.from({ length: Q }).map((_, q) => (
                  <div key={q} className={`gantt-cell ${over === q ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(q); }} onDragLeave={() => setOver(null)} onDrop={(e) => drop(q, e.dataTransfer.getData("text/plain"))}>
                    <div className="faint text-[11px] mb-1">Q{q + 1} · {plan.selected.filter((s: Any) => s.quarter === q).length} {t("jobs").toLowerCase()} · {fmt.money(plan.selected.filter((s: Any) => s.quarter === q).reduce((a: number, s: Any) => a + s.cost, 0))}</div>
                    {plan.selected.filter((s: Any) => s.quarter === q).map((s: Any) => (
                      <div key={s.candidate_id} className={`job-card ${s.crew_type} ${s.locked ? "locked" : ""}`} draggable onDragStart={(e) => e.dataTransfer.setData("text/plain", s.candidate_id)} title={`${s.label} · NPV ${fmt.money(s.npv)} · ${s.confidence}`}>
                        <div className="flex justify-between items-center"><button className="font-semibold hover:underline" onClick={() => nav(`/wells/${s.well_id}`)}>{s.well_id}</button><span className="flex gap-1"><button className="btn ghost" style={{ padding: 2 }} onClick={() => lock(s)} aria-label={s.locked ? t("unlock_job") : t("lock_job")} title={s.locked ? t("unlock_job") : t("lock_job")}><Icon name="lock" size={12} /></button><button className="btn ghost" style={{ padding: 2 }} onClick={() => remove(s)} aria-label={t("remove_job")} title={t("remove_job")}><Icon name="x" size={12} /></button></span></div>
                        <div className="faint">{String(s.action).replace(/_/g, " ")} · {fmt.money(s.cost)} · {s.crew_type}</div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </Card>
            <Card title={`${t("selected")} (${plan.selected.length})`}>
              <DataTable id="plan" rows={plan.selected} rowKey="candidate_id" dense columns={[{ key: "quarter", label: "Q", render: (r: Any) => `Q${r.quarter + 1}` }, { key: "well_id", label: t("well") }, { key: "action", label: t("action"), render: (r: Any) => String(r.action).replace(/_/g, " ") }, { key: "module", label: "source" }, { key: "cost", label: t("cost"), num: true, render: (r: Any) => fmt.money(r.cost) }, { key: "npv", label: t("npv"), num: true, render: (r: Any) => <span>{fmt.money(r.npv)} <span className="faint">({fmt.money(r.npv_lo)}–{fmt.money(r.npv_hi)})</span></span> }, { key: "oil_bpd", label: t("oil"), num: true, render: (r: Any) => fmt.n(r.oil_bpd, 1) }, { key: "water_bpd", label: t("water"), num: true, render: (r: Any) => fmt.n(r.water_bpd, 1) }, { key: "duration_months", label: t("duration"), num: true }, { key: "crew_type", label: t("crews") }, { key: "risk", label: "risk", num: true }, { key: "confidence", label: t("confidence"), render: (r: Any) => <Badge label={r.confidence} small /> }, { key: "_a", label: "", render: (r: Any) => <span className="flex gap-1"><button className="btn sm" onClick={(e) => { e.stopPropagation(); lock(r); }}>{r.locked ? t("unlock_job") : t("lock_job")}</button><button className="btn sm danger" onClick={(e) => { e.stopPropagation(); remove(r); }}>{t("remove_job")}</button></span> }]} onRow={(r) => nav(`/wells/${r.well_id}`)} />
            </Card>
            <div className="grid md:grid-cols-2 gap-3">
              <Card title={`${t("not_selected")} (${plan.not_selected.length})`}><div className="max-h-[260px] overflow-auto text-[12px] space-y-1">{plan.not_selected.map((c: Any) => <div key={c.candidate_id} className="glass-inner px-3 py-1.5 flex justify-between"><span>{c.well_id} · {String(c.action).replace(/_/g, " ")}</span><span className="faint">{fmt.money(c.cost)} · NPV {fmt.money(c.npv)}</span></div>)}</div></Card>
              <Card title={`${t("excluded")} (${plan.excluded.length})`}><div className="max-h-[260px] overflow-auto text-[12px] space-y-1">{plan.excluded.map((c: Any) => <div key={c.candidate_id} className="glass-inner px-3 py-1.5 flex justify-between items-center"><span>{c.well_id} · {String(c.action).replace(/_/g, " ")} <span className="faint">— {c.excluded_reason}</span></span>{c.excluded_reason === "removed by user" && <button className="btn sm ghost" onClick={() => restore(c.candidate_id)}>{t("include")}</button>}</div>)}</div></Card>
            </div>
          </>
        )}
      </div>
      <Drawer open={!!compare} onClose={() => setCompare(null)} title={t("compare_plan")} width={900}>
        {compare && (
          <div className="grid gap-3">
            <table className="core"><thead><tr><th>{t("method")}</th><th className="num">{t("jobs")}</th><th className="num">{t("investment")}</th><th className="num">{t("oil")} bbl/d</th><th className="num">{t("water")} bbl/d</th><th className="num">{t("npv")}</th><th className="num">{t("downside")}</th><th className="num">{t("bad_exposure")}</th></tr></thead>
              <tbody>{[{ name: compare.core.name, kpi: compare.core.kpi, core: true }, ...compare.baselines.map((b: Any) => ({ name: `${t("baseline_plan")}: ${b.rule.replace(/_/g, " ")}`, kpi: b.kpi }))].map((r: Any) => <tr key={r.name} className={r.core ? "selected row" : ""}><td className="font-medium">{r.name}</td><td className="num">{r.kpi.selected}</td><td className="num">{fmt.money(r.kpi.investment)}</td><td className="num">{fmt.n(r.kpi.expected_oil_bpd)}</td><td className="num">{fmt.n(r.kpi.expected_water_reduction_bpd)}</td><td className="num">{fmt.money(r.kpi.expected_value)}</td><td className="num">{fmt.money(r.kpi.downside_risk)}</td><td className="num">{fmt.money(r.kpi.bad_job_exposure)}</td></tr>)}</tbody></table>
            <Bars data={[{ n: "CORE", v: compare.core.kpi.expected_value }, ...compare.baselines.map((b: Any) => ({ n: b.rule.replace(/_/g, " "), v: b.kpi.expected_value }))]} xKey="n" series={[{ key: "v", name: t("npv") }]} fmtv={(v) => fmt.money(v)} height={200} colorBy={(d) => (d.n === "CORE" ? C.amber : C.blue)} />
            <div className="faint text-[12px]">{compare.note} {compare.core.kpi.expected_value <= Math.max(...compare.baselines.map((b: Any) => b.kpi.expected_value)) && <b className="text-[#FFB3A8]">{t("x_baseline_beats")}</b>}</div>
          </div>
        )}
      </Drawer>
      <Drawer open={!!manual} onClose={() => setManual(null)} title={t("add_manual")} width={520}>
        {manual && <div className="grid grid-cols-2 gap-2 text-[12px]">{Object.entries(manual).map(([kk, v]: Any) => <label key={kk} className="flex flex-col gap-1"><span className="faint">{kk.replace(/_/g, " ")}</span>{kk === "crew_type" ? <select value={v} onChange={(e) => setManual({ ...manual, [kk]: e.target.value })}><option value="rigless">rigless</option><option value="rig">rig</option></select> : <input value={v} type={typeof v === "number" ? "number" : "text"} onChange={(e) => setManual({ ...manual, [kk]: typeof v === "number" ? Number(e.target.value) : e.target.value })} />}</label>)}<label className="flex flex-col gap-1 col-span-2"><span className="faint">safety block (leave empty if none)</span><input value={manual.safety_block || ""} onChange={(e) => setManual({ ...manual, safety_block: e.target.value || null })} /></label><div className="col-span-2 flex gap-2 mt-2"><button className="btn primary" onClick={addManual} disabled={!manual.well_id}>{t("save")}</button><button className="btn ghost" onClick={() => setManual(null)}>{t("cancel")}</button></div><div className="col-span-2 faint">{t("x_manual_jobs")}</div></div>}
      </Drawer>
    </div>
  );
}

export function Scenarios() {
  const { t } = useT();
  const toast = useToast();
  const { data, error, loading, reload } = useFetch<Any>("/api/portfolio/candidates");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  const del = async (id: string) => { await api.del(`/api/portfolio/scenarios/${id}`); toast("Deleted"); reload(); };
  return (
    <Card title={t("nav_scenarios")} subtitle={t("x_saved_plans")}>
      {!data.scenarios.length && <div className="subtle text-[13px]">{t("x_no_scenarios")}</div>}
      <table className="core"><thead><tr><th>{t("scenario_name")}</th><th className="num">{t("budget")}</th><th>{t("objective")}</th><th className="num">{t("jobs")}</th><th className="num">{t("investment")}</th><th className="num">{t("npv")}</th><th className="num">{t("oil")}</th><th>{t("user")}</th><th>{t("date")}</th><th></th></tr></thead>
        <tbody>{data.scenarios.map((s: Any) => <tr key={s.scenario_id}><td className="font-medium">{s.name}</td><td className="num">{fmt.money(s.budget)}</td><td>{s.objective}</td><td className="num">{s.plan_kpi?.selected}</td><td className="num">{fmt.money(s.plan_kpi?.investment)}</td><td className="num">{fmt.money(s.plan_kpi?.expected_value)}</td><td className="num">{fmt.n(s.plan_kpi?.expected_oil_bpd)}</td><td>{s.created_by}</td><td className="faint">{fmt.date(s.created_at)}</td><td><button className="btn sm danger" onClick={() => del(s.scenario_id)}>{t("remove_job")}</button></td></tr>)}</tbody></table>
    </Card>
  );
}
