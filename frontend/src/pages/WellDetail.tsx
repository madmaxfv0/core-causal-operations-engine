import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { C, HeroChart, TT } from "../charts";
import { DataTable } from "../components/DataTable";
import { useApp } from "../components/Shell";
import { Badge, Card, DecisionButtons, ErrorBox, Icon, Kpi, LabeledValue, Progress, Provenance, Skeleton, Tabs, useFetch, useToast } from "../components/ui";
import { Any, api, download, fmt, toCSV } from "../lib/api";
import { useProv } from "../lib/provenance";
import { useT } from "../lib/i18n";

export function WellDetail() {
  const { id } = useParams();
  const { t } = useT();
  const nav = useNavigate();
  const toast = useToast();
  const { openCopilot } = useApp();
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") || "overview";
  const { data, error, loading, reload } = useFetch<Any>(`/api/wells/${id}`);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={500} />;
  const w = data.well, ov = data.overview;
  const rec = data.idle ? { id: `IDLE-${id}`, action: data.idle.intervention_type, module: "idle", status: data.idle.status } : data.ghost?.is_opportunity ? { id: `GHOST-${id}`, action: "investigate_gap", module: "ghost", status: "REVIEW" } : null;
  const addToPlan = async () => { if (!rec) return; const ps = await api.get("/api/portfolio/candidates"); const locked = { ...(ps.plan_state?.locked || {}), [rec.id]: null }; await api.post("/api/portfolio/plan-state", { locked }); toast(`${id} ${t("add_to_plan").toLowerCase()} ✓`); nav("/portfolio"); };
  return (
    <div className="grid gap-3">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap"><h1 style={{ fontSize: 34 }}>{id}</h1><Badge label={data.status} /><Badge label={data.data_mode} color="amber" small /></div>
            <div className="subtle text-[13px] mt-1">{w.field} · {w.pool || "—"} · {w.operator} · {w.lift_type || "lift n/a"} · {t("dq")} <b>{data.quality.score}</b> ({data.quality.grade}) · {t("last_update" as Any) === "last_update" ? "updated" : ""} {data.last_update}</div>
            {data.quality.flags.length > 0 && <div className="mt-1 flex gap-1 flex-wrap">{data.quality.flags.map((f: string) => <Badge key={f} label={f} small color="amber" />)}</div>}
          </div>
          <div className="flex gap-2 flex-wrap">
            <button className="btn primary" onClick={() => setSp({ tab: "causal" })}><Icon name="play" size={14} />{t("run_analysis")}</button>
            {data.idle && <button className="btn" onClick={() => nav(`/idle?well=${id}`)}>{t("compare_scenarios")}</button>}
            {rec && <button className="btn" onClick={addToPlan}>{t("add_to_plan")}</button>}
            <button className="btn" onClick={() => openCopilot(`Why was ${id} flagged?`)}>{t("ask_archive")}</button>
            <a className="btn" href={`/api/export/well/${id}/report.pdf`}><Icon name="download" size={14} />{t("export_pdf")}</a>
          </div>
        </div>
      </Card>
      <Tabs value={tab} onChange={(k) => setSp({ tab: k })} tabs={[{ key: "overview", label: t("tab_overview") }, { key: "production", label: t("tab_production") }, { key: "interventions", label: t("tab_interventions") }, { key: "causal", label: t("tab_causal") }, { key: "water", label: t("tab_water") }, { key: "documents", label: t("tab_documents") }, { key: "decisions", label: t("tab_decisions") }]} />
      {tab === "overview" && <OverviewTab data={data} rec={rec} reload={reload} />}
      {tab === "production" && <ProductionTab data={data} />}
      {tab === "interventions" && <Card title={t("tab_interventions")}>{data.interventions.length ? <DataTable id="well-int" rows={data.interventions} rowKey="intervention_id" columns={[{ key: "intervention_id", label: "ID" }, { key: "date", label: t("date") }, { key: "type", label: t("type") }, { key: "cost", label: t("cost"), num: true, render: (r: Any) => fmt.money(r.cost) }, { key: "naive_gain_bpd", label: t("naive_estimate"), num: true }, { key: "causal_gain_bpd", label: t("causal_estimate"), num: true }, { key: "net_value", label: t("npv"), num: true, render: (r: Any) => fmt.money(r.net_value) }, { key: "confidence", label: t("confidence"), render: (r: Any) => <Badge label={r.confidence} small /> }]} onRow={(r) => nav(`/interventions/${r.intervention_id}`)} dense /> : <div className="subtle">{t("x_no_int_hist")} <button className="btn sm ml-2" onClick={() => nav("/data/imports")}>{t("x_import_int")}</button> <button className="btn sm" onClick={() => nav("/archive")}>{t("x_upload_archive")}</button></div>}</Card>}
      {tab === "causal" && <CausalTab data={data} rec={rec} reloadWell={reload} />}
      {tab === "water" && <WaterTab data={data} />}
      {tab === "documents" && <DocumentsTab data={data} reload={reload} />}
      {tab === "decisions" && <DecisionsTab data={data} reload={reload} rec={rec} />}
    </div>
  );
}

function OverviewTab({ data, rec, reload }: Any) {
  const prov = useProv();
  const { t } = useT();
  const ov = data.overview;
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi label={t("current_oil")} provenance={prov("current_oil")} value={fmt.n(ov.current_oil_bpd, 1)} unit="bbl/d" small />
        <Kpi label={t("expected_baseline")} provenance={prov("expected_baseline")} value={fmt.n(ov.expected_baseline_bpd, 1)} unit="bbl/d" small sub={data.ghost ? `${data.ghost.model.replace(/_/g, " ")} · ${data.ghost.confidence}` : "producing wells only"} />
        <Kpi label={t("gap")} provenance={prov("gap")} value={fmt.n(ov.gap_bpd, 1)} unit="bbl/d" small sub={data.ghost ? `${t("range")} ${fmt.range(data.ghost.gap_lo, data.ghost.gap_hi, 1)}` : undefined} />
        <Kpi label={t("water_cut")} provenance={prov("water_cut")} value={fmt.pct(ov.water_cut)} small />
        <Kpi label={t("water_cost")} provenance={prov("water_cost")} value={fmt.money(ov.water_cost_per_day)} unit="/day" small badge={<Badge label={t("illustrative_short")} color="amber" small />} />
        <Kpi label={t("last_job")} value={<span className="text-[15px]">{ov.last_job || "—"}</span>} small />
        <Kpi label={t("recommended_action")} value={<span className="text-[15px]">{ov.recommended_action || "—"}</span>} small />
        <Kpi label={t("confidence")} value={<Badge label={ov.confidence || "n/a"} />} small />
      </div>
      <ProductionChart data={data} />
      <Card title={t("x_data_sources")}>
        <div className="grid md:grid-cols-3 gap-3 text-[12px]">
          <div><div className="faint">{t("x_well_identity")}</div><div>{data.source || "Loaded dataset"} · {data.data_mode}</div></div>
          <div><div className="faint">{t("x_private_scada")}</div><div>{t("x_not_public")}</div></div>
          <div><div className="faint">{t("x_latest_public")}</div><div>{data.last_update || "Not publicly available"}</div></div>
        </div>
      </Card>
      {!!data.outcomes?.length && <Card title={t("x_closed_loop")} subtitle={t("x_observed_sep")}>
        <div className="space-y-2 text-[12px]">{data.outcomes.map((o: Any) => <div key={o.outcome_id} className="glass-inner p-3 flex flex-wrap gap-3 items-center"><b>{o.intervention_type}</b><span>{o.intervention_date}</span><span>predicted {fmt.n(o.predicted_uplift_bpd, 1)} bbl/d</span><span>actual {fmt.n(o.actual_uplift_bpd, 1)} bbl/d</span><Badge label={o.prediction_accuracy == null ? "ACCURACY PENDING" : `${fmt.pct(o.prediction_accuracy, 1)} ACCURACY`} color={o.prediction_accuracy == null ? "grey" : "green"} small /></div>)}</div>
      </Card>}
      {data.idle && <Card title={t("why_flagged")}><ul className="list-disc ml-5 text-[13px] space-y-1">{data.idle.why?.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul><div className="mt-3 text-[12px] faint">{t("shutin_reason")}: {data.idle.reasons?.map((r: Any) => `${r.reason} ${Math.round(r.probability * 100)}%`).join(" · ")}</div>{rec && <div className="mt-3"><DecisionButtons recommendationId={rec.id} wellId={data.well_id} action={rec.action} confidence={data.idle.confidence} module="idle" inputs={{ expected_npv: data.idle.expected_npv, expected_oil_bpd: data.idle.expected_oil_bpd }} onDone={reload} /></div>}</Card>}
    </div>
  );
}

function ProductionChart({ data }: Any) {
  const { t } = useT();
  const rows = data.production.map((p: Any) => ({ ...p, baseline: data.ghost && p.t >= data.production.length - 6 ? data.ghost.expected_bpd : null }));
  const ints = data.events || [];
  return (
    <Card title={t("tab_production")}>
      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <defs><linearGradient id="gA2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.amber} stopOpacity={0.5} /><stop offset="100%" stopColor={C.amber} stopOpacity={0.04} /></linearGradient></defs>
            <CartesianGrid vertical={false} stroke={C.grid} />
            <XAxis dataKey="month" tick={{ fill: C.muted, fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={30} />
            <YAxis yAxisId="l" tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={44} />
            <YAxis yAxisId="r" orientation="right" domain={[0, 1]} tick={{ fill: C.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={36} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
            <Tooltip content={<TT fmtv={(v: Any, k: string) => (k === "water_cut" ? fmt.pct(v) : `${fmt.n(v, 1)} bbl/d`)} />} />
            {data.shutin_periods.map((s: Any, i: number) => <ReferenceArea key={i} yAxisId="l" x1={s.start_month} x2={s.end_month} fill={C.red} fillOpacity={0.08} label={{ value: t("shutin_periods"), fill: C.muted, fontSize: 10, position: "insideTop" }} />)}
            {ints.map((e: Any, i: number) => <ReferenceLine key={i} yAxisId="l" x={e.month} stroke={C.amber} strokeDasharray="3 3" label={{ value: e.label, fill: C.amber, fontSize: 10, position: "top" }} />)}
            <Area yAxisId="l" dataKey="oil_bpd" name={t("oil")} stroke={C.amber} fill="url(#gA2)" strokeWidth={2} isAnimationActive={false} connectNulls={false} />
            <Line yAxisId="l" dataKey="water_bpd" name={t("water")} stroke={C.blue} strokeWidth={1.6} dot={false} isAnimationActive={false} />
            <Line yAxisId="r" dataKey="water_cut" name={t("water_cut")} stroke={C.teal} strokeWidth={1.2} dot={false} strokeDasharray="4 3" isAnimationActive={false} />
            <Line yAxisId="l" dataKey="baseline" name={t("baseline")} stroke={C.lav} strokeWidth={2} dot={false} isAnimationActive={false} />
            <Legend wrapperStyle={{ fontSize: 11 }} iconSize={10} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function ProductionTab({ data }: Any) {
  const { t } = useT();
  return <div className="grid gap-3"><ProductionChart data={data} /><Card title={t("tab_production")}><DataTable id="well-prod" rows={data.production} rowKey="t" columns={[{ key: "month", label: t("month") }, { key: "oil_m3", label: "oil m³ (source)", num: true, render: (r: Any) => fmt.n(r.oil_m3, 1) }, { key: "water_m3", label: "water m³ (source)", num: true, render: (r: Any) => fmt.n(r.water_m3, 1) }, { key: "oil_bpd", label: "oil bbl/d", num: true, render: (r: Any) => fmt.n(r.oil_bpd, 2) }, { key: "water_bpd", label: "water bbl/d", num: true, render: (r: Any) => fmt.n(r.water_bpd, 1) }, { key: "water_cut", label: t("water_cut"), num: true, render: (r: Any) => fmt.pct(r.water_cut, 1) }, { key: "hours", label: "hours", num: true }]} defaultSort={{ key: "t", dir: "desc" }} pageSize={24} /></Card></div>;
}

export function CausalTab({ data, rec, reloadWell, initialEvent }: Any) {
  const { t } = useT();
  const toast = useToast();
  const nav = useNavigate();
  const events: Any[] = data.events?.length ? data.events : [{ kind: "pseudo", label: "Ghost-barrel screen (pseudo event: last 6 months)", pre_end: data.production.length - 7, post_start: data.production.length - 6, post_window: 6 }];
  const [ev, setEv] = useState<Any>(initialEvent || events[0]);
  const [model, setModel] = useState("auto");
  const [analysis, setAnalysis] = useState<Any>(null);
  const [steps, setSteps] = useState<string[] | null>(null);
  const [excl, setExcl] = useState<string[]>([]);
  const [locked, setLocked] = useState(false);
  const [rules, setRules] = useState<Any>(null);
  const [error, setError] = useState<Any>(null);
  const load = async () => {
    setError(null);
    try { const a = await api.get(`/api/wells/${data.well_id}/causal?pre_end=${ev.pre_end}&post_start=${ev.post_start}&model=${model}&kind=${ev.kind}${ev.post_window ? `&post_window=${ev.post_window}` : ""}`); setAnalysis(a); setExcl(a.donor_overrides?.exclusions || []); setLocked(!!a.donor_overrides?.locked); } catch (e) { setError(e); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [ev, model]);
  const rerun = async (exclusions = excl, lock = locked) => {
    setSteps(["Queued"]); setError(null);
    try {
      const j = await api.post(`/api/wells/${data.well_id}/causal/run`, { pre_end: ev.pre_end, post_start: ev.post_start, model, kind: ev.kind, post_window: ev.post_window, exclusions, forced: [], lock });
      const res = await api.job(j.job_id, setSteps);
      setAnalysis({ ...res, donor_overrides: { exclusions, locked: lock } }); setSteps(null); toast(`${t("rerun")} ✓ ${res.confidence}`);
    } catch (e: Any) { setSteps(null); setError(e); }
  };
  const toggleDonor = (wid: string) => { const next = excl.includes(wid) ? excl.filter((x) => x !== wid) : [...excl, wid]; setExcl(next); };
  const donorCols = useMemo(() => [
    { key: "well_id", label: t("well"), render: (r: Any) => <button className="font-medium hover:underline" onClick={(e) => { e.stopPropagation(); nav(`/wells/${r.well_id}`); }}>{r.well_id}</button> },
    { key: "similarity", label: t("similarity"), num: true, render: (r: Any) => fmt.n(r.similarity, 3) },
    { key: "pre_rate_bpd", label: `${t("oil")} pre (bbl/d)`, num: true, render: (r: Any) => fmt.n(r.pre_rate_bpd, 1) },
    { key: "water_cut", label: t("water_cut"), num: true, render: (r: Any) => fmt.pct(r.water_cut) },
    { key: "trend_pct_per_year", label: "trend %/yr", num: true, render: (r: Any) => fmt.n(r.trend_pct_per_year, 1) },
    { key: "weight", label: t("weight"), num: true, render: (r: Any) => <span className={r.weight > 0.05 ? "text-amber font-semibold" : ""}>{fmt.n(r.weight, 3)}</span> },
    { key: "reasons", label: t("reason_selected"), render: (r: Any) => <span className="faint">{(r.reasons || []).join("; ")}</span> },
    { key: "_act", label: "", render: (r: Any) => <button className={`btn sm ${r.excluded || excl.includes(r.well_id) ? "" : "ghost"}`} onClick={(e) => { e.stopPropagation(); toggleDonor(r.well_id); }} disabled={locked}>{r.excluded || excl.includes(r.well_id) ? t("include") : t("exclude")}</button> },
  ], [t, excl, locked]);
  const d = analysis?.diagnostics || {};
  return (
    <div className="grid gap-3">
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <select value={events.indexOf(ev) >= 0 ? events.indexOf(ev) : 0} onChange={(e) => setEv(events[Number(e.target.value)])} aria-label={t("intervention")}>{events.map((e: Any, i: number) => <option key={i} value={i}>{e.month || ""} {e.label}</option>)}</select>
          <select value={model} onChange={(e) => setModel(e.target.value)} aria-label={t("model")}><option value="auto">AUTO</option><option value="synthetic_control">{t("x_synth_control")}</option><option value="matched_wells">{t("x_matched_wells")}</option><option value="decline_curve">{t("x_decline_curve")}</option><option value="did">{t("x_did")}</option></select>
          <button className="btn primary" onClick={() => rerun()} disabled={!!steps}><Icon name="play" size={14} />{t("run_analysis")}</button>
          <span className="flex-1" />
          {analysis && <a className="btn sm" href={`/api/export/analysis/${analysis.analysis_id}.json`}><Icon name="download" size={13} />{t("export_json")}</a>}
          {analysis && <button className="btn sm" onClick={() => download(`${data.well_id}_analysis.csv`, toCSV(analysis.months.map((m: string, i: number) => ({ month: m, rel: analysis.rel_months[i], actual: analysis.actual[i], counterfactual: analysis.counterfactual[i], lo: analysis.cf_lo[i], hi: analysis.cf_hi[i] }))))}><Icon name="download" size={13} />{t("export_csv")}</button>}
        </div>
        {analysis?.status === "COMPLETE" && <div className="mt-3 text-[13px] subtle">{t("hero_caption")} <span className="faint">— {ev.label}, {ev.month}</span></div>}
      </Card>
      {steps && <Progress steps={steps} label={t("run_analysis")} />}
      {error && <ErrorBox error={error} onRetry={load} />}
      {analysis && analysis.status !== "COMPLETE" && !steps && <Card><div className="text-[#FFB3A8] font-medium mb-1">{analysis.status}</div>{analysis.messages.map((m: string, i: number) => <div key={i} className="subtle text-[13px]">{m}</div>)}<button className="btn sm mt-3" onClick={async () => setRules(await api.get("/api/eligibility-rules"))}>{t("eligibility_rules")}</button></Card>}
      {analysis && analysis.status === "COMPLETE" && !steps && (
        <>
          <Card title={<span className="flex items-center gap-2">{t("tab_causal")} <Badge label={analysis.confidence} /><Provenance data={{ model: analysis.model_label, donors: d.donor_count, effective_donors: d.effective_donors, pre_window: d.pre_window, post_window: d.post_window, pre_r2: d.pre_r2, pre_nrmse: d.pre_nrmse, placebo_wells_p: d.placebo_wells_p, placebo_time_score: d.placebo_time_score, interval: `80%: ${analysis.effect_lo_bpd}–${analysis.effect_hi_bpd} bbl/d`, note: d.interval_note, bootstrap_samples: analysis.meta.bootstrap_samples, seed: analysis.meta.seed, model_version: analysis.meta.model_version, dataset_version: analysis.meta.dataset_version, last_run: analysis.created_at }} label={t("provenance")} /></span>}>
            <HeroChart analysis={analysis} />
            {analysis.messages?.length > 0 && <div className="mt-2 text-[12px] subtle">{analysis.messages.join(" ")}</div>}
          </Card>
          <div className="grid md:grid-cols-3 gap-3">
            <Card title={t("pre_fit")}><div className="grid grid-cols-2 gap-3 text-[13px]"><LabeledValue label="R²" value={fmt.n(d.pre_r2, 3)} /><LabeledValue label="RMSE" value={`${fmt.n(d.pre_rmse_bpd, 2)} bbl/d (${fmt.pct(d.pre_nrmse)})`} /><LabeledValue label={t("baseline_reliability")} value={<Badge label={d.baseline_reliability} color={d.baseline_reliability === "high" ? "green" : d.baseline_reliability === "moderate" ? "amber" : "red"} />} /><LabeledValue label={t("treatment_window")} value={`${d.pre_window} / ${d.post_window} ${t("months")}`} /><LabeledValue label={t("donors")} value={`${d.donor_count} (${d.effective_donors} effective) of ${d.candidate_count} eligible`} /><LabeledValue label={t("missing_data")} value={fmt.pct(d.missing_pct)} /><LabeledValue label={t("donor_quality")} value={fmt.n(d.donor_pool_quality, 3)} /><LabeledValue label="confidence score" value={fmt.n(d.confidence_score, 2)} /></div></Card>
            <Card title={t("placebo")}>
              {analysis.placebo?.in_time ? <div className="text-[13px] mb-3"><div className="faint">Placebo-in-time (fake treatment at month {analysis.placebo.in_time.fake_t0})</div><div>fake effect <b>{fmt.n(analysis.placebo.in_time.fake_effect_bpd, 2)}</b> vs actual <b>{fmt.n(analysis.placebo.in_time.actual_effect_bpd, 2)}</b> bbl/d · score {fmt.n(analysis.placebo.in_time.score, 2)}</div><div className="faint text-[11px]">{analysis.placebo.in_time.note}</div></div> : <div className="faint text-[12px] mb-3">{t("x_placebo_na")}</div>}
              {analysis.placebo?.wells ? <div className="text-[13px]"><div className="faint">{t("x_placebo_wells_t")}</div><div>p = <b>{fmt.n(analysis.placebo.wells.p_value, 3)}</b> · treated ratio {fmt.n(analysis.placebo.wells.treated_rmspe_ratio, 2)}</div><div className="flex flex-wrap gap-1 mt-1">{analysis.placebo.wells.placebos.map((p: Any) => <span key={p.well_id} className="badge grey" title={`ratio ${p.rmspe_ratio}`}>{p.well_id} {fmt.n(p.effect_bpd, 1)}</span>)}</div><div className="faint text-[11px] mt-1">{analysis.placebo.wells.note}</div></div> : <div className="faint text-[12px]">{t("x_placebo_model_na")}</div>}
            </Card>
            <Card title={t("uncertainty")}><div className="text-[13px] space-y-2"><div><span className="faint">{t("most_likely")}</span><div className="text-[22px] font-semibold">{fmt.n(analysis.mean_effect_bpd, 1)} <span className="faint text-[12px]">bbl/d</span></div></div><div><span className="faint">{t("range")} (80%)</span><div className="text-[16px]">{fmt.range(analysis.effect_lo_bpd, analysis.effect_hi_bpd, 1)} bbl/d</div></div><div><span className="faint">{t("cumulative_oil")}</span><div>{fmt.n(analysis.cumulative_effect_bbl)} bbl · {t("range")} {fmt.range(analysis.cumulative_lo_bbl, analysis.cumulative_hi_bbl)}</div></div>{analysis.truth && <div className="glass-inner p-2 mt-2"><Badge label={t("x_synth_truth")} color="blue" small /> planted effect {fmt.n(analysis.truth.true_effect_bpd_12m, 1)} bbl/d</div>}</div></Card>
          </div>
          <Card title={<span>{t("donors")} <span className="faint text-[12px]">· {t("view_evidence")}</span></span>} action={<div className="flex gap-2"><button className="btn sm" onClick={() => { setLocked(!locked); rerun(excl, !locked); }}><Icon name="lock" size={13} />{locked ? t("unlock_donors") : t("lock_donors")}</button><button className="btn sm primary" onClick={() => rerun()} disabled={!!steps}>{t("rerun")}</button></div>}>
            <DataTable id="donors" rows={analysis.donors} columns={donorCols} dense defaultSort={{ key: "weight", dir: "desc" }} />
            {excl.length > 0 && <div className="faint text-[12px] mt-2">{excl.length} excluded: {excl.join(", ")} — press {t("rerun")} to apply.</div>}
          </Card>
          {rec && <Card title={t("recommendation")}><div className="text-[13px] mb-2">{rec.status} · {String(rec.action).replace(/_/g, " ")} · {t("confidence")}: {analysis.confidence}</div><DecisionButtons recommendationId={rec.id} wellId={data.well_id} action={rec.action} confidence={analysis.confidence} module={rec.module} inputs={{ analysis_id: analysis.analysis_id, model: analysis.model, effect_bpd: analysis.mean_effect_bpd }} onDone={reloadWell} /></Card>}
        </>
      )}
      {rules && <Card title={t("eligibility_rules")} action={<button className="btn ghost sm" onClick={() => setRules(null)}>{t("close")}</button>}><ul className="list-disc ml-5 text-[13px] space-y-1">{rules.rules.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></Card>}
    </div>
  );
}

function WaterTab({ data }: Any) {
  const { t } = useT();
  const toast = useToast();
  const w = data.water;
  const [f, setF] = useState({ water_reduction_bpd: w ? Math.round(w.water_bpd * 0.3) : 100, oil_effect_bpd: w ? Math.round(w.oil_bpd * 0.15) : 5, cost: 120000, success_probability: 0.6, duration_months: 24 });
  const [res, setRes] = useState<Any>(null);
  const run = async () => { try { setRes(await api.post("/api/water/shutoff-scenario", { well_id: data.well_id, ...f })); } catch (e: Any) { toast(e.message, "err"); } };
  if (!w) return <Card><div className="subtle">{t("x_water_prod_only")}</div></Card>;
  return (
    <div className="grid md:grid-cols-2 gap-3">
      <Card title={t("water_title")}><div className="grid grid-cols-2 gap-3 text-[13px]"><LabeledValue label={t("water")} value={`${fmt.n(w.water_bpd)} bbl/d`} /><LabeledValue label={t("water_cut")} value={fmt.pct(w.water_cut)} /><LabeledValue label={t("visible_cost")} value={`$${fmt.n(w.visible_cost_per_bbl, 2)}/bbl`} /><LabeledValue label={t("hidden_cost")} value={`$${fmt.n(w.shadow_cost_per_bbl, 2)}/bbl`} /><LabeledValue label={t("total_cost")} value={`${fmt.money(w.water_cost_per_day)}/day · ${fmt.money(w.water_cost_per_year)}/yr`} /><LabeledValue label={t("facility")} value={`${w.facility} · ${w.constraint_status} · ${w.utilisation ? fmt.pct(w.utilisation) : "n/a"}`} /></div><div className="faint text-[11px] mt-3"><Badge label={t("illustrative")} color="amber" small /> component costs are editable in Settings; corrosion/scale excluded (operator data required).</div></Card>
      <Card title={t("shutoff")}>
        <div className="grid grid-cols-2 gap-2 text-[12px]">
          {([["water_reduction_bpd", t("water_reduction")], ["oil_effect_bpd", t("oil_effect")], ["cost", t("cost")], ["success_probability", t("success_prob")], ["duration_months", t("duration")]] as [string, string][]).map(([k, l]) => <label key={k} className="flex flex-col gap-1"><span className="faint">{l}</span><input type="number" step={k === "success_probability" ? 0.05 : 1} value={(f as Any)[k]} onChange={(e) => setF({ ...f, [k]: Number(e.target.value) })} /></label>)}
        </div>
        <button className="btn primary mt-3" onClick={run}>{t("apply")}</button>
        {res && <div className="glass-inner p-3 mt-3 text-[13px] fade-in"><div>{t("net_value")}: <b>{fmt.money(res.expected_net_value)}</b> · {t("payback")}: {res.payback_months ?? "—"} {t("months")}</div><div className="faint">{t("range")}: {fmt.money(res.range[0])} – {fmt.money(res.range[1])}</div><Provenance data={res.economics.provenance} /></div>}
      </Card>
    </div>
  );
}

function DocumentsTab({ data, reload }: Any) {
  const { t } = useT();
  const nav = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const up = async (file: File | null) => { if (!file) return; setBusy(true); try { await api.upload("/api/archive/upload", file, { well_id: data.well_id }); toast(`${file.name} ✓`); reload(); } catch (e: Any) { toast(e.message, "err"); } finally { setBusy(false); } };
  return <Card title={t("tab_documents")} action={<label className="btn sm cursor-pointer"><Icon name="upload" size={13} />{t("upload")}<input type="file" className="hidden" onChange={(e) => up(e.target.files?.[0] || null)} disabled={busy} /></label>}>
    {!data.documents.length && <div className="subtle text-[13px]">{t("x_no_docs")}</div>}
    <div className="space-y-2">{data.documents.map((d: Any) => <button key={d.document_id} className="w-full text-left glass-inner p-3 text-[13px] hover:bg-white/10" onClick={() => nav(`/archive?doc=${d.document_id}`)}><div className="flex justify-between"><span className="font-medium">{d.file_name}</span><Badge label={d.review_status} small /></div><div className="faint">{d.language} · {d.doc_type} · {d.date || "—"}</div></button>)}</div>
  </Card>;
}

function DecisionsTab({ data, reload, rec }: Any) {
  const { t } = useT();
  const toast = useToast();
  const [note, setNote] = useState("");
  const addNote = async () => { if (!note.trim()) return; await api.post(`/api/notes/${data.well_id}`, { text: note }); setNote(""); toast(t("note_saved")); reload(); };
  return (
    <div className="grid md:grid-cols-2 gap-3">
      <Card title={t("tab_decisions")}>{!data.decisions.length && <div className="subtle text-[13px] mb-3">{t("x_no_dec_well")}</div>}<div className="space-y-2">{data.decisions.map((d: Any) => <div key={d.decision_id} className="glass-inner p-3 text-[12px]"><div className="flex justify-between"><Badge label={d.decision} /><span className="faint">{fmt.date(d.timestamp)} · {d.user}</span></div><div className="mt-1">{String(d.action).replace(/_/g, " ")} · {d.reason || ""} {d.notes || ""}</div><div className="faint">model {d.model_version} · {d.confidence}</div></div>)}</div>{rec && <div className="mt-4"><DecisionButtons recommendationId={rec.id} wellId={data.well_id} action={rec.action} module={rec.module} onDone={reload} /></div>}</Card>
      <Card title={t("notes")}><textarea className="w-full" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("add_note")} /><button className="btn sm mt-2" onClick={addNote}>{t("add_note")}</button><div className="space-y-2 mt-3">{data.notes.map((n: Any) => <div key={n.note_id} className="glass-inner p-3 text-[12px]"><div className="faint">{fmt.date(n.timestamp)} · {n.user}</div>{n.text}</div>)}</div></Card>
    </div>
  );
}
