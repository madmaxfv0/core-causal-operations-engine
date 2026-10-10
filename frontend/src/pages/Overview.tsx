import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bars, C, Matrix, TrendChart, Waterfall } from "../charts";
import { DataTable } from "../components/DataTable";
import { useApp } from "../components/Shell";
import { Badge, Card, DecisionButtons, ErrorBox, Kpi, Skeleton, useFetch } from "../components/ui";
import { Any, fmt, iType } from "../lib/api";
import { useProv } from "../lib/provenance";
import { useT } from "../lib/i18n";

export function Overview() {
  const prov = useProv();
  const { t } = useT();
  const { field, meta } = useApp();
  const nav = useNavigate();
  const { data, error, loading, reload } = useFetch<Any>(`/api/overview${field ? `?field=${encodeURIComponent(field)}` : ""}`);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <div className="grid gap-3"><Skeleton h={180} /><Skeleton h={320} /></div>;
  const k = data.kpi;
  const trend = data.trend.slice(-36);
  const oilSpark = trend.map((x: Any) => x.oil_bpd), waterSpark = trend.map((x: Any) => x.water_bpd);
  const trendPct = (arr: number[]) => (arr.length > 12 ? ((arr[arr.length - 1] - arr[arr.length - 13]) / (arr[arr.length - 13] || 1)) * 100 : null);
  const invest = data.investment_return.map((c: Any) => ({ ...c, label: c.well_id, x: c.cost, y: c.npv > 0 ? Math.min(1, c.npv / Math.max(1, Math.max(...data.investment_return.map((z: Any) => z.npv)))) : 0.02, color: c.selected ? C.amber : "rgba(255,255,255,0.35)", sub: `${iType(t, c.action)} · NPV ${fmt.money(c.npv)}${c.selected ? " · selected" : ""}` }));
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(300px, 420px)" }}>
      <div className="grid gap-3">
        <div className="pt-8 pb-3 pl-2">
          <span className="chip amber mb-3" style={{ fontSize: 12 }}>{field || t("field_all")} · {t("ov_title")}</span>
          <div className="hero-title">{meta?.dataset_label || "CORE"}</div>
          <div className="subtle mt-3 text-[13px]">{data.label} · {t("ov_label")}</div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Kpi label={t("ov_oil")} provenance={prov("ov_oil")} value={fmt.n(k.oil_bpd)} unit={t("per_day")} spark={oilSpark} trend={trendPct(oilSpark)} />
          <Kpi label={t("ov_water")} provenance={prov("ov_water")} value={fmt.n(k.water_bpd)} unit={t("per_day")} spark={waterSpark} trend={trendPct(waterSpark)} sub={`${t("water_cut")} ${fmt.pct(k.water_cut)}`} />
          <Kpi label={t("ov_idle")} provenance={prov("ov_idle")} value={k.idle_wells} sub={`${k.producing_wells} ${t("k_producing")} · ${k.restart_events} ${t("k_restart_events")}`} />
          <Kpi label={t("ov_screened")} provenance={prov("ov_screened")} value={k.wells_screened} sub={`${k.jobs_analysed} ${t("k_jobs_analysed")}`} />
          <Kpi label={t("ov_underperf")} provenance={prov("ov_underperf")} value={k.underperformance_candidates} small />
          <Kpi label={t("ov_candidates")} provenance={prov("ov_candidates")} value={k.intervention_candidates} small sub={`${k.high_confidence_opportunities} ${t("k_high_conf")}`} />
          <Kpi label={t("ov_recoverable")} provenance={prov("ov_recoverable")} value={`+${fmt.n(k.recoverable_opportunity_bpd)}`} unit={t("per_day")} small sub={`${t("range")} ${fmt.range(k.recoverable_range_bpd[0], k.recoverable_range_bpd[1])}`} badge={<Badge label={t("x_model_est")} color="blue" small />} />
          <Kpi label={t("ov_avoidable_water")} provenance={prov("ov_avoidable_water")} value={`−${fmt.n(k.avoidable_water_bpd)}`} unit={t("per_day")} small badge={<Badge label={t("x_model_est")} color="blue" small />} />
          <Kpi label={t("ov_capital")} provenance={prov("ov_capital")} value={fmt.money(k.capital_required)} small badge={<Badge label={t("illustrative_short")} color="amber" small />} />
          <Kpi label={t("ov_npv")} provenance={prov("ov_npv")} value={fmt.money(k.portfolio_npv)} small sub={`${t("range")} ${fmt.money(k.portfolio_npv_range[0])} – ${fmt.money(k.portfolio_npv_range[1])}`} badge={<Badge label={t("illustrative_short")} color="amber" small />} />
          <Kpi label={t("total_cost")} provenance={prov("total_cost")} value={fmt.money(k.water_cost_per_year)} unit="/yr" small badge={<Badge label={t("illustrative_short")} color="amber" small />} />
        </div>
        <Card title={t("ov_trend")} corner={{ to: "/wells", label: t("nav_wells") }}>
          <TrendChart data={data.trend} series={[{ key: "oil_bpd", name: t("oil"), color: C.amber, type: "area" }, { key: "water_bpd", name: t("water"), color: C.blue, type: "line", axis: "right" }]} name="field_production" />
        </Card>
        <div className="grid md:grid-cols-2 gap-3">
          <Card title={t("ov_waterfall")}><Waterfall steps={data.waterfall} unit="bbl/d" name="opportunity_waterfall" /></Card>
          <Card title={t("ov_matrix")} corner={{ to: "/idle", label: t("nav_idle") }}>
            <Matrix points={data.matrix.map((m: Any) => ({ ...m, label: `${m.well_id} · ${m.status}`, z: 1, sub: m.confidence }))} xLabel={t("value")} yLabel={t("confidence")} xFmt={(v) => fmt.money(v)} quadrants={[t("quad_act"), t("quad_investigate"), t("quad_insufficient"), t("quad_low")]} xMid={Math.max(1, ...data.matrix.map((m: Any) => m.x)) * 0.35} onPoint={(p) => nav(`/wells/${p.well_id}`)} name="opportunity_matrix" />
          </Card>
          <Card title={t("ov_water_matrix")} corner={{ to: "/water", label: t("nav_water_econ") }}>
            <Matrix points={data.water_matrix.map((m: Any) => ({ ...m, label: m.well_id, x: m.water_cut, y: Math.min(1, m.cost_per_year / Math.max(1, Math.max(...data.water_matrix.map((z: Any) => z.cost_per_year)))), z: m.oil_bpd, color: m.constraint === "constrained" ? C.red : m.constraint === "near limit" ? C.amber : C.blue, sub: `${fmt.money(m.cost_per_year)}/yr · ${m.constraint}` }))} xLabel={t("water_cut")} yLabel={t("water_cost")} xFmt={(v) => fmt.pct(v)} onPoint={(p) => nav(`/wells/${p.well_id}`)} name="water_matrix" />
          </Card>
          <Card title={t("ov_invest")} corner={{ to: "/portfolio", label: t("nav_portfolio") }}>
            <Matrix points={invest} xLabel={t("cost")} yLabel={t("npv")} xFmt={(v) => fmt.money(v)} onPoint={(p) => nav(`/wells/${p.well_id}`)} name="investment_return" />
          </Card>
        </div>
      </div>
      <div className="grid gap-3 content-start">
        <Card title={t("ov_awaiting")} corner={{ to: "/decisions", label: t("nav_decisions") }}>
          {!data.awaiting_review.length && <div className="subtle text-[13px]">{t("x_all_decided")}</div>}
          <div className="space-y-2">
            {data.awaiting_review.map((a: Any) => (
              <div key={a.recommendation_id} className="glass-inner p-3 text-[12px]">
                <div className="flex justify-between items-center mb-1"><button className="font-semibold hover:underline" onClick={() => nav(`/wells/${a.well_id}`)}>{a.well_id}</button><Badge label={a.status} small /></div>
                <div className="subtle mb-2">{iType(t, a.action)} · {fmt.money(a.value)} · <Badge label={a.confidence} small /></div>
                <DecisionButtons recommendationId={a.recommendation_id} wellId={a.well_id} action={a.action || ""} confidence={a.confidence} module={a.module} compact onDone={reload} />
              </div>
            ))}
          </div>
        </Card>
        <Card title={t("ov_recent")} corner={{ to: "/runs", label: t("nav_runs") }}>
          <div className="space-y-1 text-[12px]">
            {data.recent_analyses.map((r: Any) => <button key={r.analysis_id} className="w-full text-left glass-inner px-3 py-2 hover:bg-white/10" onClick={() => nav(`/wells/${r.well_id}?tab=causal`)}><div className="flex justify-between"><span className="font-medium">{r.well_id}</span><Badge label={r.confidence} small /></div><div className="faint">{r.event_label || r.kind} · {String(r.model || "").replace(/_/g, " ")} · {fmt.n(r.mean_effect_bpd, 1)} bbl/d</div></button>)}
          </div>
        </Card>
      </div>
    </div>
  );
}

export function Wells() {
  const { t } = useT();
  const { field } = useApp();
  const nav = useNavigate();
  const [flt, setFlt] = useState<string>("");
  const { data, error, loading, reload } = useFetch<Any>(`/api/wells?${field ? `field=${encodeURIComponent(field)}&` : ""}${flt ? `status=${flt}` : ""}`);
  const filters = [["producing", "f_producing"], ["idle", "f_idle"], ["high_water", "f_high_water"], ["opportunity", "f_opportunity"], ["intervention_candidate", "f_candidate"], ["low_confidence", "f_low_conf"], ["insufficient_evidence", "f_insufficient"]];
  const cols = useMemo(() => [
    { key: "well_id", label: t("well"), render: (r: Any) => <span className="font-medium">{r.well_id}</span> },
    { key: "field", label: t("field") },
    { key: "status", label: t("status"), render: (r: Any) => <Badge label={r.status} /> },
    { key: "oil_bpd", label: `${t("oil")} (bbl/d)`, num: true, render: (r: Any) => fmt.n(r.oil_bpd, 1) },
    { key: "water_bpd", label: `${t("water")} (bbl/d)`, num: true, render: (r: Any) => fmt.n(r.water_bpd, 0) },
    { key: "water_cut", label: t("water_cut"), num: true, render: (r: Any) => fmt.pct(r.water_cut) },
    { key: "baseline_bpd", label: t("baseline"), num: true, render: (r: Any) => fmt.n(r.baseline_bpd, 1) },
    { key: "gap_bpd", label: t("gap"), num: true, render: (r: Any) => fmt.n(r.gap_bpd, 1) },
    { key: "opportunity", label: t("opportunity"), num: true, render: (r: Any) => fmt.money(r.opportunity) },
    { key: "last_intervention", label: t("last_intervention") },
    { key: "confidence", label: t("confidence"), render: (r: Any) => <Badge label={r.confidence} small /> },
    { key: "recommendation", label: t("recommendation"), render: (r: Any) => <span>{r.recommendation}</span> },
    { key: "dq_score", label: t("dq"), num: true, hidden: true, render: (r: Any) => fmt.n(r.dq_score) },
  ], [t]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  return (
    <Card title={t("wells_title")} subtitle={data ? `${data.rows.length} ${t("rows")}` : ""}>
      {loading || !data ? <Skeleton h={400} /> : (
        <DataTable id="wells" rows={data.rows} columns={cols} onRow={(r) => nav(`/wells/${r.well_id}`)} searchKeys={["well_id", "field", "status", "recommendation"]} defaultSort={{ key: "opportunity", dir: "desc" }}
          toolbar={<div className="flex gap-1 flex-wrap">{filters.map(([k, lbl]) => <button key={k} className={`chip ${flt === k ? "amber" : ""}`} style={{ padding: "5px 10px", fontSize: 12 }} onClick={() => setFlt(flt === k ? "" : k)}>{t(lbl as Any)}</button>)}</div>} />
      )}
    </Card>
  );
}

export function QualityPage() {
  const prov = useProv();
  const { t } = useT();
  const nav = useNavigate();
  const { data, error, loading, reload } = useFetch<Any>("/api/quality");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={400} />;
  const comp = ["dq_completeness", "dq_missing_months", "dq_duplicate_rows", "dq_negative_volumes", "dq_outliers", "dq_unusual_jumps", "dq_status_inconsistencies", "dq_unit_issues", "dq_insufficient_pre_period", "dq_insufficient_post_period"];
  const cols = [{ key: "well_id", label: t("well") }, { key: "dq_score", label: "Score", num: true }, { key: "dq_grade", label: "Grade", render: (r: Any) => <Badge label={r.dq_grade} color={r.dq_grade === "good" ? "green" : r.dq_grade === "fair" ? "amber" : "red"} /> }, { key: "dq_flags", label: "Flags", render: (r: Any) => <span className="faint">{String(r.dq_flags || "").replace(/,/g, ", ")}</span> }, ...comp.map((c) => ({ key: c, label: c.replace("dq_", "").replace(/_/g, " "), num: true, render: (r: Any) => (typeof r[c] === "boolean" ? (r[c] ? "yes" : "no") : String(r[c])) }))];
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-4 gap-3"><Kpi label={t("x_wells2")} provenance={prov("dq_wells")} value={data.summary.wells} small /><Kpi label="Good" value={data.summary.good} small /><Kpi label="Fair" value={data.summary.fair} small /><Kpi label="Poor" provenance={prov("dq_poor")} value={data.summary.poor} small sub="excluded from high-confidence recommendations" /></div>
      <Card title={t("nav_quality")} subtitle={t("x_score_sum")}><DataTable id="quality" rows={data.rows} columns={cols} onRow={(r) => nav(`/wells/${r.well_id}`)} defaultSort={{ key: "dq_score", dir: "asc" }} /></Card>
      <Card title={t("x_grade_dist")}><Bars data={[{ g: "good", n: data.summary.good }, { g: "fair", n: data.summary.fair }, { g: "poor", n: data.summary.poor }]} xKey="g" series={[{ key: "n", name: "wells" }]} height={180} colorBy={(d) => (d.g === "good" ? C.green : d.g === "fair" ? C.amber : C.red)} /></Card>
    </div>
  );
}
