import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Bars, C, HeroChart, TrendChart, Waterfall } from "../charts";
import { DataTable } from "../components/DataTable";
import { useApp } from "../components/Shell";
import { Badge, Card, DecisionButtons, Drawer, ErrorBox, Icon, Kpi, LabeledValue, Provenance, RangeText, Skeleton, useFetch, useToast } from "../components/ui";
import { Any, api, fmt, iType } from "../lib/api";
import { useProv } from "../lib/provenance";
import { useT } from "../lib/i18n";

function Funnel({ f }: { f: Any }) {
  const { t } = useT();
  const steps = [["all_idle", "funnel_all"], ["sufficient_data", "funnel_data"], ["plausible", "funnel_plausible"], ["positive_value", "funnel_value"], ["fits_constraints", "funnel_constraints"], ["recommended", "funnel_recommended"]];
  const max = f.all_idle || 1;
  return <div className="space-y-1.5">{steps.map(([k, l], i) => <div key={k} className="flex items-center gap-3 text-[12px]"><span className="w-[220px] subtle">{t(l as Any)}</span><div className="flex-1 h-7 rounded-lg overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}><div className="h-full rounded-lg flex items-center px-2 font-semibold" style={{ width: `${Math.max(8, (f[k] / max) * 100)}%`, background: `rgba(242,182,50,${0.25 + i * 0.12})`, color: "#FFE39A" }}>{f[k]}</div></div></div>)}</div>;
}

export function IdleWells() {
  const { t } = useT();
  const { field } = useApp();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const sel = sp.get("well");
  const { data, error, loading, reload } = useFetch<Any>(`/api/idle${field ? `?field=${encodeURIComponent(field)}` : ""}`);
  const cols = useMemo(() => [
    { key: "rank", label: "#", num: true }, { key: "well_id", label: t("well"), render: (r: Any) => <span className="font-medium">{r.well_id}</span> }, { key: "status", label: t("status"), render: (r: Any) => <Badge label={r.status} /> }, { key: "last_production_month", label: t("last_production") },
    { key: "last_oil_bpd", label: t("last_rate"), num: true, render: (r: Any) => fmt.n(r.last_oil_bpd, 1) }, { key: "historical_peak_bpd", label: t("peak"), num: true, render: (r: Any) => fmt.n(r.historical_peak_bpd, 1) }, { key: "last_water_cut", label: t("water_cut"), num: true, render: (r: Any) => fmt.pct(r.last_water_cut) },
    { key: "estimated_reason", label: t("shutin_reason"), render: (r: Any) => <span>{r.estimated_reason} <Badge label={r.reason_quality} small /></span> }, { key: "restart_probability", label: t("restart_prob"), num: true, render: (r: Any) => fmt.pct(r.restart_probability) },
    { key: "expected_oil_bpd", label: t("expected_oil"), num: true, render: (r: Any) => r.expected_oil_bpd !== undefined ? <span>{fmt.n(r.expected_oil_bpd, 1)} <span className="faint">({fmt.range(r.expected_oil_lo, r.expected_oil_hi, 1)})</span></span> : "—" }, { key: "expected_water_bpd", label: t("expected_water"), num: true, render: (r: Any) => fmt.n(r.expected_water_bpd) },
    { key: "intervention_type", label: t("est_intervention"), render: (r: Any) => r.intervention_type ? iType(t, r.intervention_type) : "—" }, { key: "intervention_cost", label: t("cost"), num: true, render: (r: Any) => fmt.money(r.intervention_cost) }, { key: "expected_npv", label: t("npv"), num: true, render: (r: Any) => r.expected_npv !== undefined ? <span>{fmt.money(r.expected_npv)} <span className="faint">({fmt.money(r.npv_lo)}–{fmt.money(r.npv_hi)})</span></span> : "—" },
    { key: "payback_months", label: t("payback"), num: true }, { key: "confidence", label: t("confidence"), render: (r: Any) => <Badge label={r.confidence} small /> },
  ], [t]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={500} />;
  return (
    <div className="grid gap-3">
      <div className="grid lg:grid-cols-3 gap-3">
        <Card title={t("idle_title")} className="lg:col-span-2"><Funnel f={data.funnel} /><div className="faint text-[11px] mt-3">{data.assumptions.note} · economic limit {data.assumptions.economic_limit_bpd.value} bbl/d ({data.assumptions.economic_limit_bpd.source})</div></Card>
        <Card title={t("status")}><div className="grid grid-cols-2 gap-2 text-[12px]">{["ACT", "TEST", "REVIEW", "WAIT", "DO NOT PRIORITISE", "INSUFFICIENT DATA"].map((s) => <div key={s} className="glass-inner p-2 flex items-center justify-between"><Badge label={s} small /><b>{data.rows.filter((r: Any) => r.status === s).length}</b></div>)}</div></Card>
      </div>
      <Card title={t("nav_idle")}><DataTable id="idle" rows={data.rows} columns={cols} onRow={(r) => setSp({ well: r.well_id })} selectedKey={sel} defaultSort={{ key: "rank", dir: "asc" }} searchKeys={["well_id", "status", "estimated_reason", "intervention_type", "confidence"]} /></Card>
      <Autopsy wellId={sel} onClose={() => setSp({})} onChanged={reload} />
    </div>
  );
}

function Autopsy({ wellId, onClose, onChanged }: { wellId: string | null; onClose: () => void; onChanged: () => void }) {
  const { t } = useT();
  const nav = useNavigate();
  const { data, error, loading } = useFetch<Any>(wellId ? `/api/idle/${wellId}` : null, [wellId]);
  const [compare, setCompare] = useState(false);
  const r = data?.row;
  return (
    <Drawer open={!!wellId} onClose={onClose} title={<span className="flex items-center gap-2">{t("autopsy")} · {wellId} {r && <Badge label={r.status} />} {r && <Badge label={r.confidence} small />}</span>} width={860}>
      {error && <ErrorBox error={error} />}
      {loading && <Skeleton h={300} />}
      {data && (
        <div className="grid gap-3">
          <div className="flex gap-2 flex-wrap"><button className="btn sm" onClick={() => nav(`/wells/${wellId}`)}>{t("open")} {t("well").toLowerCase()}</button><button className={`btn sm ${compare ? "primary" : ""}`} onClick={() => setCompare(!compare)}>{t("compare_scenarios")}</button><a className="btn sm" href={`/api/export/well/${wellId}/report.pdf`}><Icon name="download" size={13} />{t("export_pdf")}</a></div>
          <Card title={t("before_shutin")}>
            <div className="grid grid-cols-3 gap-3 mb-3 text-[13px]"><LabeledValue label={t("last_rate")} value={`${fmt.n(data.profile.last_rate_bpd, 1)} bbl/d`} sub={`peak ${fmt.n(data.profile.peak_bpd, 1)}`} /><LabeledValue label={t("water_cut")} value={`${fmt.pct(data.profile.wc_first)} → ${fmt.pct(data.profile.wc_last)}`} /><LabeledValue label="hours (last / avg)" value={`${fmt.n(data.profile.hours_last)} / ${fmt.n(data.profile.hours_mean)}`} /></div>
            <TrendChart data={data.profile.months.map((m: string, i: number) => ({ month: m, oil: data.profile.series[i], wc: data.profile.wc_series[i], hours: data.profile.hours_series[i] }))} series={[{ key: "oil", name: "oil bbl/d", type: "area" }, { key: "wc", name: t("water_cut"), type: "line", color: C.teal, axis: "right" }]} height={180} name={`pre_shutin_${wellId}`} />
            <div className="text-[12px] mt-2"><span className="faint">{t("last_intervention")}:</span> {data.recent_interventions.length ? data.recent_interventions.map((m: Any) => `${m.date} ${m.type}`).join(", ") : "none recorded"} · <span className="faint">documents:</span> {data.documents.length || "none"} · <span className="faint">pressure:</span> OPERATOR DATA REQUIRED</div>
          </Card>
          <Card title={t("why_stopped")}>
            <div className="space-y-2">{r.reasons.map((x: Any) => <div key={x.reason} className="glass-inner p-3 text-[12px]"><div className="flex items-center justify-between"><span className="font-semibold">{x.reason}</span><span className="flex items-center gap-2"><span className="font-semibold">{fmt.pct(x.probability)}</span><Badge label={x.evidence_quality} small /></span></div><div className="h-1.5 rounded-full mt-1.5 mb-1.5" style={{ background: "rgba(255,255,255,0.08)" }}><div className="h-full rounded-full" style={{ width: `${x.probability * 100}%`, background: C.amber }} /></div>{x.evidence.length ? <ul className="list-disc ml-4 subtle">{x.evidence.map((e: string, i: number) => <li key={i}>{e}</li>)}</ul> : <div className="faint">no distinguishing evidence</div>}<div className="faint">{t("source")}: {x.source}</div></div>)}</div>
            <div className="faint text-[11px] mt-2">{t("x_prob_heur")}</div>
          </Card>
          <Card title={t("scenarios")}>
            {compare && <Bars data={data.scenarios.filter((s: Any) => s.status === "OK").map((s: Any) => ({ scenario: s.label, npv: s.npv, oil: s.oil_bpd }))} xKey="scenario" series={[{ key: "npv", name: t("npv") }]} fmtv={(v) => fmt.money(v)} height={200} name={`scenarios_${wellId}`} colorBy={(d) => (d.npv > 0 ? C.green : C.red)} />}
            <table className="core"><thead><tr><th>{t("scenarios")}</th><th className="num">{t("expected_oil")}</th><th className="num">{t("expected_water")}</th><th className="num">{t("cost")}</th><th className="num">{t("duration")}</th><th className="num">{t("success_prob")}</th><th className="num">{t("npv")}</th><th className="num">{t("payback")}</th><th>{t("evidence")}</th></tr></thead>
              <tbody>{data.scenarios.map((s: Any) => <tr key={s.scenario}><td className="font-medium">{s.label}</td>{s.status === "OK" ? <><td className="num"><RangeText lo={s.oil_lo} mid={s.oil_bpd} hi={s.oil_hi} d={1} /></td><td className="num">{fmt.n(s.water_bpd)}</td><td className="num">{fmt.money(s.cost)}</td><td className="num">{s.duration_months}</td><td className="num">{fmt.pct(s.success_probability)}</td><td className="num"><span className={s.npv > 0 ? "text-[#9FE6BC]" : "text-[#FFB3A8]"}>{fmt.money(s.npv)}</span>{s.npv_lo !== undefined && <span className="faint"> ({fmt.money(s.npv_lo)}–{fmt.money(s.npv_hi)})</span>}{s.economics && <Provenance data={s.economics.provenance} />}</td><td className="num">{s.payback_months ?? "—"}</td><td className="faint text-[12px]">{s.evidence}</td></> : <td colSpan={8}><Badge label={s.status} /> <span className="faint text-[12px]">{s.evidence}</span></td>}</tr>)}</tbody></table>
          </Card>
          <Card title={t("why_flagged")}>
            <div className="grid md:grid-cols-2 gap-3 text-[13px]">
              <div><div className="faint">WHAT</div>{data.why.what}<div className="faint mt-2">WHY</div><ul className="list-disc ml-4">{data.why.why.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul><div className="faint mt-2">{t("x_compared_with")}</div><div className="flex flex-wrap gap-1">{data.why.compared_with.map((w: string) => <button key={w} className="chip" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => nav(`/wells/${w}`)}>{w}</button>)}</div></div>
              <div><div className="faint">{t("x_how_much")}</div>{fmt.n(data.why.how_much.oil_bpd, 1)} bbl/d ({fmt.range(data.why.how_much.range[0], data.why.how_much.range[1], 1)}) · NPV {fmt.money(data.why.how_much.npv)} ({fmt.money(data.why.how_much.npv_range[0])}–{fmt.money(data.why.how_much.npv_range[1])})<div className="faint mt-2">{t("x_how_certain")}</div><Badge label={data.why.how_certain} /><div className="faint mt-2">{t("could_be_wrong")}</div><ul className="list-disc ml-4">{data.why.what_could_change.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul><div className="faint mt-2">{t("x_who_decides")}</div>{data.why.who_decides}</div>
            </div>
            <div className="mt-4"><DecisionButtons recommendationId={`IDLE-${wellId}`} wellId={wellId!} action={r.intervention_type || "restart"} confidence={r.confidence} module="idle" inputs={{ expected_npv: r.expected_npv, expected_oil_bpd: r.expected_oil_bpd, status: r.status }} onDone={onChanged} /></div>
          </Card>
        </div>
      )}
    </Drawer>
  );
}

export function GhostBarrels() {
  const prov = useProv();
  const { t } = useT();
  const { field } = useApp();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const sel = sp.get("well");
  const { data, error, loading, reload } = useFetch<Any>(`/api/ghost${field ? `?field=${encodeURIComponent(field)}` : ""}`);
  const cols = useMemo(() => [
    { key: "well_id", label: t("well"), render: (r: Any) => <span className="font-medium">{r.well_id}</span> }, { key: "is_opportunity", label: t("status"), render: (r: Any) => <Badge label={r.is_opportunity ? "opportunity" : "tracking baseline"} color={r.is_opportunity ? "amber" : "grey"} small /> },
    { key: "observed_bpd", label: t("observed"), num: true, render: (r: Any) => fmt.n(r.observed_bpd, 1) }, { key: "expected_bpd", label: t("expected"), num: true, render: (r: Any) => fmt.n(r.expected_bpd, 1) }, { key: "gap_bpd", label: t("gap"), num: true, render: (r: Any) => <span>{fmt.n(r.gap_bpd, 1)} <span className="faint">({fmt.range(r.gap_lo, r.gap_hi, 1)})</span></span> }, { key: "gap_pct", label: "%", num: true, render: (r: Any) => fmt.pct(r.gap_pct) },
    { key: "oil_opportunity_bpd", label: t("opportunity"), num: true, render: (r: Any) => fmt.n(r.oil_opportunity_bpd, 1) }, { key: "water_cut", label: t("water_cut"), num: true, render: (r: Any) => fmt.pct(r.water_cut) }, { key: "probable_driver", label: t("driver") }, { key: "duration_months", label: t("duration"), num: true }, { key: "confidence", label: t("confidence"), render: (r: Any) => <Badge label={r.confidence} small /> }, { key: "annual_value", label: t("annual_value"), num: true, render: (r: Any) => fmt.money(r.annual_value) },
  ], [t]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={500} />;
  const k = data.kpi;
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi label={t("ghost_kpi")} provenance={prov("ghost_kpi")} value={`+${fmt.n(k.estimated_recoverable_bpd, 1)}`} unit="bbl/d" sub={`${t("range")} ${fmt.range(k.estimated_range_bpd[0], k.estimated_range_bpd[1], 1)} · ${k.label}`} badge={<Badge label={t("x_model_est")} color="blue" small />} />
        <Kpi label={t("ov_screened")} value={k.wells_screened} small sub={`${data.lookback_months}-month look-back vs donor counterfactual`} />
        <Kpi label={t("ov_underperf")} value={k.candidates} small />
        <Kpi label={t("annual_value")} provenance={prov("annual_value")} value={fmt.money(data.rows.filter((r: Any) => r.is_opportunity).reduce((s: number, r: Any) => s + r.annual_value, 0))} small badge={<Badge label={t("illustrative_short")} color="amber" small />} />
      </div>
      <Card title={t("ghost_title")} subtitle={t("x_ghost_note")}><DataTable id="ghost" rows={data.rows} columns={cols} onRow={(r) => setSp({ well: r.well_id })} selectedKey={sel} defaultSort={{ key: "oil_opportunity_bpd", dir: "desc" }} /></Card>
      <GhostDrawer wellId={sel} onClose={() => setSp({})} onChanged={reload} />
    </div>
  );
}

function GhostDrawer({ wellId, onClose, onChanged }: { wellId: string | null; onClose: () => void; onChanged: () => void }) {
  const { t } = useT();
  const nav = useNavigate();
  const { data, error, loading } = useFetch<Any>(wellId ? `/api/ghost/${wellId}` : null, [wellId]);
  const r = data?.row, d = data?.why?.decomposition;
  return (
    <Drawer open={!!wellId} onClose={onClose} title={<span className="flex items-center gap-2">{t("ghost_title")} · {wellId} {r && <Badge label={r.confidence} small />}</span>} width={880}>
      {error && <ErrorBox error={error} />}{loading && <Skeleton h={300} />}
      {data && (
        <div className="grid gap-3">
          <div className="flex gap-2"><button className="btn sm" onClick={() => nav(`/wells/${wellId}?tab=causal`)}>{t("open")} {t("tab_causal").toLowerCase()}</button><a className="btn sm" href={`/api/export/well/${wellId}/report.pdf`}><Icon name="download" size={13} />{t("export_pdf")}</a></div>
          <Card title={t("hero_cf")}><HeroChart analysis={data.analysis} compact height={240} /><div className="text-[12px] subtle mt-2">{t("observed")} {fmt.n(r.observed_bpd, 1)} vs {t("expected")} {fmt.n(r.expected_bpd, 1)} bbl/d · {t("gap")} {fmt.n(r.gap_bpd, 1)} ({fmt.range(r.gap_lo, r.gap_hi, 1)}) · {r.model.replace(/_/g, " ")}</div></Card>
          <div className="grid md:grid-cols-2 gap-3">
            <Card title={t("decomposition")}><div className="space-y-1.5">{d.components.map((c: Any) => <div key={c.component} className="glass-inner px-3 py-2 text-[12px] flex items-center justify-between gap-2"><div><div>{c.label}</div><div className="faint">{c.note}</div></div><div className="flex items-center gap-2 shrink-0"><span className="font-semibold">{c.bpd === null ? "n/a" : `−${fmt.n(c.bpd, 1)}`}</span><Badge label={c.status} small /></div></div>)}</div></Card>
            <Card title={t("waterfall")}><Waterfall steps={d.waterfall} unit="bbl/d" height={280} name={`ghost_waterfall_${wellId}`} /></Card>
          </div>
          <Card title={t("why_flagged")}><ol className="list-decimal ml-5 text-[13px] space-y-1">{data.why.why.map((x: string, i: number) => <li key={i}>{x}</li>)}</ol><div className="grid md:grid-cols-3 gap-3 mt-3 text-[12px]"><div><div className="faint">{t("x_evidence")}</div>{data.why.evidence.historic_interventions} historic interventions · {data.why.evidence.archive_documents} archive documents</div><div><div className="faint">{t("x_uncertainty")}</div><Badge label={data.why.uncertainty} /></div><div><div className="faint">{t("x_action")}</div>{data.why.action_status}: {String(data.why.action).replace(/_/g, " ")}</div></div><div className="faint text-[12px] mt-2">{t("could_be_wrong")}: {data.why.could_be_wrong.join("; ")}</div>
            <div className="mt-4"><DecisionButtons recommendationId={`GHOST-${wellId}`} wellId={wellId!} action={data.why.action} confidence={r.confidence} module="ghost" inputs={{ gap_bpd: r.gap_bpd, annual_value: r.annual_value }} onDone={onChanged} /></div></Card>
        </div>
      )}
    </Drawer>
  );
}

export function WaterEconomics() {
  const prov = useProv();
  const { t } = useT();
  const { field, reloadMeta } = useApp();
  const nav = useNavigate();
  const toast = useToast();
  const { data, error, loading, reload } = useFetch<Any>(`/api/water${field ? `?field=${encodeURIComponent(field)}` : ""}`);
  const settings = useFetch<Any>("/api/settings");
  const [unit, setUnit] = useState<"bbl" | "m3">("bbl");
  const [edits, setEdits] = useState<Record<string, number>>({});
  const [saving, setSaving] = useState(false);
  const [sc, setSc] = useState({ well_id: "", water_reduction_bpd: 200, oil_effect_bpd: 5, cost: 120000, success_probability: 0.6, duration_months: 24 });
  const [scRes, setScRes] = useState<Any>(null);
  const cv = unit === "bbl" ? 1 : 1 / 6.28981;
  const u = unit === "bbl" ? "bbl" : "m³";
  useEffect(() => { if (data && !sc.well_id && data.rows.length) setSc((s) => ({ ...s, well_id: data.rows[0].well_id })); }, [data]);
  const comps = settings.data?.economics?.water || {};
  const save = async () => {
    setSaving(true);
    try { const water: Any = {}; Object.entries(edits).forEach(([k, v]) => { water[k] = { value: v }; }); await api.put("/api/settings", { economics: { water } }); const j = await api.post("/api/evidence/rebuild"); await api.job(j.job_id); toast(t("saved")); setEdits({}); reload(); settings.reload(); reloadMeta(); } catch (e: Any) { toast(e.message, "err"); } finally { setSaving(false); }
  };
  const runSc = async () => { try { setScRes(await api.post("/api/water/shutoff-scenario", sc)); } catch (e: Any) { toast(e.message, "err"); } };
  const cols = useMemo(() => [
    { key: "well_id", label: t("well"), render: (r: Any) => <span className="font-medium">{r.well_id}</span> }, { key: "oil_bpd", label: `${t("oil")} ${u}/d`, num: true, render: (r: Any) => fmt.n(r.oil_bpd * cv, 1) }, { key: "water_bpd", label: `${t("water")} ${u}/d`, num: true, render: (r: Any) => fmt.n(r.water_bpd * cv) }, { key: "water_cut", label: t("water_cut"), num: true, render: (r: Any) => fmt.pct(r.water_cut) },
    { key: "total_cost_per_bbl", label: `$/${u}`, num: true, render: (r: Any) => <span>{fmt.n(r.total_cost_per_bbl / cv, 2)} <span className="faint">({fmt.n(r.visible_cost_per_bbl / cv, 2)} + {fmt.n(r.shadow_cost_per_bbl / cv, 2)})</span></span> }, { key: "water_cost_per_day", label: `${t("water_cost")}/day`, num: true, render: (r: Any) => fmt.money(r.water_cost_per_day) }, { key: "water_cost_per_year", label: `${t("water_cost")}/yr`, num: true, render: (r: Any) => fmt.money(r.water_cost_per_year) },
    { key: "facility", label: t("facility") }, { key: "constraint_status", label: t("constraint"), render: (r: Any) => <Badge label={r.constraint_status} color={r.constraint_status === "constrained" ? "red" : r.constraint_status === "near limit" ? "amber" : "green"} small /> }, { key: "potential_intervention", label: t("intervention_potential"), render: (r: Any) => r.potential_intervention ? String(r.potential_intervention).replace(/_/g, " ") : <span className="faint">—</span> }, { key: "water_avoided_bpd", label: t("water_avoided"), num: true, render: (r: Any) => fmt.n(r.water_avoided_bpd) }, { key: "expected_value", label: t("expected_value"), num: true, render: (r: Any) => fmt.money(r.expected_value) },
  ], [t, unit]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={500} />;
  const k = data.kpi;
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2 flex-wrap"><Badge label={data.mode} color="amber" /><Badge label={t("mode_operator") + ": not connected"} color="grey" /><span className="faint text-[12px]">{data.note}</span><span className="flex-1" /><span className="faint text-[12px]">{t("unit")}</span><select value={unit} onChange={(e) => setUnit(e.target.value as Any)}><option value="bbl">bbl</option><option value="m3">m³</option></select></div>
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Kpi label={t("ov_water")} provenance={prov("ov_water")} value={fmt.n(k.produced_water_bpd * cv)} unit={`${u}/d`} small />
        <Kpi label={t("visible_cost")} provenance={prov("visible_cost")} value={fmt.money(k.visible_cost_per_day)} unit="/day" small badge={<Badge label={t("illustrative_short")} color="amber" small />} />
        <Kpi label={t("hidden_cost")} value={fmt.money(k.hidden_capacity_cost_per_day)} unit="/day" small sub="capacity shadow cost" provenance={{ formula: "netback × oil fraction of marginal fluid, when facility utilisation ≥ threshold", threshold: comps.capacity_threshold, note: "facility capacities are OPERATOR DATA REQUIRED (illustrative in demo)" }} />
        <Kpi label={t("total_cost")} provenance={prov("total_cost")} value={fmt.money(k.total_cost_per_day)} unit="/day" small sub={`${fmt.money(k.total_cost_per_year)} / yr`} />
        <Kpi label={t("shutoff")} provenance={prov("shutoff")} value={k.shutoff_candidates} small sub="candidates (water cut ≥ 85%, evidence ≥ 3 jobs)" />
      </div>
      <div className="grid lg:grid-cols-3 gap-3">
        <Card title={t("components")} subtitle={t("x_assump_edit")} className="lg:col-span-1">
          <div className="space-y-1.5">{Object.entries(comps).map(([k2, v]: Any) => k2 === "capacity_threshold" ? null : <div key={k2} className="flex items-center gap-2 text-[12px]"><span className="flex-1">{k2.replace(/_/g, " ")}</span>{v.value === null ? <Badge label={v.source} small /> : <><input type="number" step="0.05" className="w-[84px]" style={{ padding: "4px 8px" }} value={edits[k2] ?? v.value} onChange={(e) => setEdits({ ...edits, [k2]: Number(e.target.value) })} /><span className="faint w-[70px]">$/bbl</span><Badge label={v.source} small /></>}</div>)}</div>
          <div className="flex gap-2 mt-3"><button className="btn primary sm" disabled={!Object.keys(edits).length || saving} onClick={save}>{saving ? t("loading") : t("save")}</button><button className="btn sm ghost" onClick={() => setEdits({})}>{t("cancel")}</button></div>
          <div className="mt-3 text-[12px]"><div className="faint mb-1">{t("facility")} {t("utilisation").toLowerCase()}</div>{data.facilities.map((f: Any) => <div key={f.facility_id} className="flex items-center gap-2 mb-1"><span className="w-[60px]">{f.facility_id}</span><div className="flex-1 h-2 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}><div className="h-full rounded-full" style={{ width: `${Math.min(100, (f.utilisation || 0) * 100)}%`, background: (f.utilisation || 0) >= (comps.capacity_threshold?.value || 0.85) ? C.red : (f.utilisation || 0) >= 0.75 ? C.amber : C.green }} /></div><span className="w-[40px] num">{fmt.pct(f.utilisation)}</span><span className="faint">{f.handling}</span></div>)}</div>
        </Card>
        <Card title={t("trajectory")} className="lg:col-span-2"><TrendChart data={data.trajectory.map((x: Any) => ({ ...x, oil: x.oil_bpd * cv, water: x.water_bpd * cv }))} series={[{ key: "water", name: `${t("water")} ${u}/d`, color: C.blue, type: "area" }, { key: "oil", name: `${t("oil")} ${u}/d`, color: C.amber, type: "line" }, { key: "water_cut", name: t("water_cut"), color: C.teal, type: "line", axis: "right" }]} height={260} name="water_trajectory" /></Card>
      </div>
      <Card title={t("water_title")}><DataTable id="water" rows={data.rows} columns={cols} onRow={(r) => nav(`/wells/${r.well_id}?tab=water`)} defaultSort={{ key: "water_cost_per_year", dir: "desc" }} /></Card>
      <Card title={t("shutoff")}>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-[12px]">
          <label className="flex flex-col gap-1"><span className="faint">{t("well")}</span><select value={sc.well_id} onChange={(e) => setSc({ ...sc, well_id: e.target.value })}>{data.rows.map((r: Any) => <option key={r.well_id} value={r.well_id}>{r.well_id}</option>)}</select></label>
          {([["water_reduction_bpd", t("water_reduction")], ["oil_effect_bpd", t("oil_effect")], ["cost", t("cost")], ["success_probability", t("success_prob")], ["duration_months", t("duration")]] as [string, string][]).map(([k2, l]) => <label key={k2} className="flex flex-col gap-1"><span className="faint">{l}</span><input type="number" step={k2 === "success_probability" ? 0.05 : 1} value={(sc as Any)[k2]} onChange={(e) => setSc({ ...sc, [k2]: Number(e.target.value) })} /></label>)}
        </div>
        <button className="btn primary mt-3" onClick={runSc}>{t("apply")}</button>
        {scRes && <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 fade-in"><Kpi label={t("net_value")} value={fmt.money(scRes.expected_net_value)} small /><Kpi label={t("payback")} value={scRes.payback_months ?? "—"} unit={t("months")} small /><Kpi label={t("npv")} value={fmt.money(scRes.npv)} small provenance={scRes.economics.provenance} /><Kpi label={t("range")} value={<span className="text-[15px]">{fmt.money(scRes.range[0])} – {fmt.money(scRes.range[1])}</span>} small /></div>}
      </Card>
    </div>
  );
}
