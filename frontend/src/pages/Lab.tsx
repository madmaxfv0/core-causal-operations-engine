import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Bars, C, Histogram, Matrix, Tornado } from "../charts";
import { DataTable } from "../components/DataTable";
import { Badge, Card, ErrorBox, Kpi, Skeleton, Tabs, useFetch } from "../components/ui";
import { Any, api, fmt, iType } from "../lib/api";
import { useProv } from "../lib/provenance";
import { useT } from "../lib/i18n";

export function ModelLab({ initial }: { initial?: string }) {
  const { t } = useT();
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") || initial || "planted";
  const tabs = [["planted", "lab_planted"], ["placebo", "lab_placebo"], ["blind", "lab_blind"], ["calibration", "lab_calibration"], ["reason", "lab_reason"], ["sensitivity", "lab_sensitivity"], ["cards", "lab_cards"]];
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-3 flex-wrap"><h1 style={{ fontSize: 28 }}>{t("lab_title")}</h1><span className="subtle text-[13px]">{t("x_falsify")}</span></div>
      <Tabs tabs={tabs.map(([k, l]) => ({ key: k, label: t(l as Any) }))} value={tab} onChange={(k) => setSp({ tab: k })} />
      {tab === "planted" && <Planted />}{tab === "placebo" && <Placebo />}{tab === "blind" && <Blind />}{tab === "calibration" && <Calibration />}{tab === "reason" && <ReasonAcc />}{tab === "sensitivity" && <Sens />}{tab === "cards" && <Cards />}
    </div>
  );
}

function Planted() {
  const prov = useProv();
  const { t } = useT();
  const nav = useNavigate();
  const { data, error, loading, reload } = useFetch<Any>("/api/validation/planted-truth");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={400} />;
  if (!data.available) return <Card><div className="subtle">{data.note}</div></Card>;
  const m = data.metrics;
  const ex = [...data.rows].sort((a: Any, b: Any) => (b.naive - b.core) - (a.naive - a.core)).slice(0, 8);
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2"><Badge label={data.label} color="amber" /><span className="subtle text-[13px]">{data.n} interventions with a secretly planted true effect. The analysis layer never reads the truth table.</span></div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label={t("mae")} provenance={prov("mae")} value={<span>{fmt.n(m.core.mae, 2)} <span className="faint text-[14px]">vs {fmt.n(m.naive.mae, 2)}</span></span>} unit="bbl/d" small sub={`${t("core")} vs ${t("naive")}`} />
        <Kpi label={t("bias")} provenance={prov("bias")} value={<span>{m.core.bias >= 0 ? "+" : ""}{fmt.n(m.core.bias, 2)} <span className="faint text-[14px]">vs +{fmt.n(m.naive.bias, 2)}</span></span>} unit="bbl/d" small sub="naive systematically overstates" />
        <Kpi label={t("coverage")} provenance={prov("coverage")} value={fmt.pct(m.core.coverage_80)} small sub="share of true effects inside the 80% interval" />
        <Kpi label={t("spearman")} provenance={prov("spearman")} value={<span>{fmt.n(m.core.spearman, 2)} <span className="faint text-[14px]">vs {fmt.n(m.naive.spearman, 2)}</span></span>} small sub={`zero-effect jobs (${m.zero_effect_jobs.n}): CORE ${fmt.n(m.zero_effect_jobs.core_mean, 2)} · naive ${fmt.n(m.zero_effect_jobs.naive_mean, 2)}`} />
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <Card title={`${t("truth")} · ${t("naive")} · ${t("core")}`}><Bars data={ex.map((r: Any) => ({ id: r.well_id, truth: r.truth, naive: r.naive, core: r.core }))} xKey="id" series={[{ key: "truth", name: t("truth"), color: C.green }, { key: "naive", name: t("naive"), color: C.red }, { key: "core", name: t("core"), color: C.amber }]} height={280} name="planted_examples" fmtv={(v) => `${fmt.n(v, 1)} bbl/d`} /><div className="faint text-[11px]">{t("x_eight_jobs")}</div></Card>
        <Card title={t("x_est_truth")}><Matrix points={data.rows.flatMap((r: Any) => [{ label: `${r.well_id} naive`, x: r.truth, y: Math.max(0, Math.min(1, (r.naive + 10) / 40)), z: 1, color: C.red, sub: `naive ${fmt.n(r.naive, 1)}` }, { label: `${r.well_id} CORE`, x: r.truth, y: Math.max(0, Math.min(1, (r.core + 10) / 40)), z: 1, color: C.amber, sub: `CORE ${fmt.n(r.core, 1)} (${fmt.range(r.lo, r.hi, 1)})` }])} xLabel={t("truth")} yLabel="estimate (scaled)" height={280} name="planted_scatter" /></Card>
      </div>
      <Card title={t("lab_planted")}><DataTable id="planted" rows={data.rows} rowKey="intervention_id" dense columns={[{ key: "intervention_id", label: "ID" }, { key: "well_id", label: t("well") }, { key: "type", label: t("type") }, { key: "truth", label: t("truth"), num: true }, { key: "naive", label: t("naive"), num: true, render: (r: Any) => <span style={{ color: C.red }}>{fmt.n(r.naive, 2)}</span> }, { key: "core", label: t("core"), num: true, render: (r: Any) => <span style={{ color: C.amber }}>{fmt.n(r.core, 2)}</span> }, { key: "lo", label: "80% interval", render: (r: Any) => <span className={r.truth >= r.lo && r.truth <= r.hi ? "text-[#9FE6BC]" : "text-[#FFB3A8]"}>{fmt.range(r.lo, r.hi, 2)}</span> }, { key: "confidence", label: t("confidence"), render: (r: Any) => <Badge label={r.confidence} small /> }]} onRow={(r) => nav(`/interventions/${r.intervention_id}`)} /></Card>
    </div>
  );
}

function Placebo() {
  const { t } = useT();
  const { data, error, loading, reload } = useFetch<Any>("/api/validation/placebo");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  const s = data.summary;
  const edges = Array.from({ length: 21 }, (_, i) => -10 + i);
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label={t("x_placebo_time")} value={s.in_time_n} small sub={`mean |fake effect| ${fmt.n(s.in_time_mean_abs_fake, 2)} vs mean |actual| ${fmt.n(s.in_time_mean_abs_actual, 2)} bbl/d`} />
        <Kpi label={t("x_placebo_eff")} value={s.placebo_well_effects_n} small sub={`mean ${fmt.n(s.placebo_well_effects_mean, 2)} · sd ${fmt.n(s.placebo_well_effects_sd, 2)} bbl/d`} />
        <Kpi label={t("x_centre")} value={fmt.n(s.placebo_well_effects_mean, 2)} unit="bbl/d" small sub={s.note} />
        <Kpi label={t("x_interpretation")} value={<span className="text-[13px]">{Math.abs(s.placebo_well_effects_mean || 0) < 0.5 ? "No systematic phantom effect on untreated wells" : "Phantom effects present — treat estimates with caution"}</span>} small />
      </div>
      <Card title={t("x_placebo_dist")}><Histogram edges={edges} counts={data.placebo_hist} height={240} xFmt={(a) => `${a}`} name="placebo_hist" /></Card>
      <Card title={t("x_placebo_time_well")}><DataTable id="placebo-time" rows={data.in_time} dense columns={[{ key: "well_id", label: t("well") }, { key: "fake_effect_bpd", label: "fake effect (bbl/d)", num: true }, { key: "actual_effect_bpd", label: "actual effect (bbl/d)", num: true }, { key: "score", label: "score", num: true, render: (r: Any) => <span className={r.score >= 0.7 ? "text-[#9FE6BC]" : r.score >= 0.4 ? "text-amber" : "text-[#FFB3A8]"}>{fmt.n(r.score, 2)}</span> }]} defaultSort={{ key: "score", dir: "asc" }} /></Card>
    </div>
  );
}

export function Blind() {
  const { t } = useT();
  const nav = useNavigate();
  const { data, error, loading, reload } = useFetch<Any>("/api/validation/blind-test");
  const [reveal, setReveal] = useState(false);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  if (!data.available) return <Card><div className="subtle">{data.note}</div></Card>;
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-3 flex-wrap"><Badge label={data.label} color="amber" /><span className="subtle text-[13px]">{t("cutoff")} {data.cutoff_month}: {data.n} wells were idle at the cut-off and restarted later. Rankings use only information before the cut-off.</span><span className="flex-1" /><button className={`btn ${reveal ? "" : "primary"}`} onClick={() => setReveal(!reveal)}>{reveal ? t("hide") : t("reveal")}</button></div>
      <Card title={`${t("method")} · ${t("lab_blind")}`} subtitle={data.note}>
        <table className="core"><thead><tr><th>{t("method")}</th><th className="num">{t("spearman")}</th><th className="num">{t("captured")} (k={data.results[0].top_k})</th><th>top-k</th></tr></thead>
          <tbody>{data.results.map((r: Any) => <tr key={r.method} className={r.method.startsWith("CORE") ? "selected row" : ""}><td className="font-medium">{r.method}</td><td className="num">{reveal ? fmt.n(r.spearman, 3) : "?"}</td><td className="num">{reveal ? fmt.pct(r.top_k_captured_share) : "?"}</td><td className="faint text-[12px]">{r.top_k_wells.join(", ")}</td></tr>)}</tbody></table>
        {reveal && <div className="mt-3"><Bars data={data.results.map((r: Any) => ({ m: r.method.replace(" (analogue-adjusted counterfactual)", "").replace(" ranking (last rate)", ""), rho: r.spearman ?? 0 }))} xKey="m" series={[{ key: "rho", name: t("spearman") }]} height={200} colorBy={(d) => (d.m.startsWith("CORE") ? C.amber : C.blue)} name="blind_results" /></div>}
      </Card>
      <Card title={t("x_holdout")}><DataTable id="blind" rows={data.rows} dense columns={[{ key: "well_id", label: t("well") }, { key: "shutin_month", label: "shut-in" }, { key: "restart_month", label: "restart" }, { key: "estimated_reason", label: t("shutin_reason") }, { key: "last_rate_bpd", label: t("last_rate"), num: true }, { key: "peak_bpd", label: t("peak"), num: true }, { key: "water_cut", label: t("water_cut"), num: true, render: (r: Any) => fmt.pct(r.water_cut) }, { key: "core_expected_bpd", label: "CORE score (bbl/d × p)", num: true }, { key: "analogs", label: "analogues", num: true }, { key: "actual_6m_bpd", label: "actual 6-month bbl/d", num: true, render: (r: Any) => reveal ? <b>{fmt.n(r.actual_6m_bpd, 1)}</b> : <span className="faint">hidden</span> }]} onRow={(r) => nav(`/wells/${r.well_id}`)} defaultSort={{ key: "core_expected_bpd", dir: "desc" }} /></Card>
    </div>
  );
}

function Calibration() {
  const { t } = useT();
  const { data, error, loading, reload } = useFetch<Any>("/api/validation/calibration");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  return <Card title={t("lab_calibration")} subtitle={data.note}><Bars data={data.bins.map((b: Any) => ({ bin: b.bin, "positive effect rate": b.positive_effect_rate, "true positive rate": b.true_positive_rate ?? 0, "mean confidence": b.mean_confidence }))} xKey="bin" series={[{ key: "mean confidence", name: "mean confidence score", color: C.blue }, { key: "positive effect rate", name: "estimated positive rate", color: C.amber }, { key: "true positive rate", name: "true positive rate (synthetic)", color: C.green }]} fmtv={(v) => fmt.pct(v)} height={260} name="calibration" /><table className="core mt-3"><thead><tr><th>bin</th><th className="num">n</th><th className="num">mean confidence</th><th className="num">estimated positive</th><th className="num">true positive</th></tr></thead><tbody>{data.bins.map((b: Any) => <tr key={b.bin}><td>{b.bin}</td><td className="num">{b.n}</td><td className="num">{fmt.n(b.mean_confidence, 2)}</td><td className="num">{fmt.pct(b.positive_effect_rate)}</td><td className="num">{fmt.pct(b.true_positive_rate)}</td></tr>)}</tbody></table></Card>;
}

function ReasonAcc() {
  const { t } = useT();
  const { data, error, loading, reload } = useFetch<Any>("/api/validation/reason-accuracy");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  if (!data.available) return <Card><div className="subtle">{t("x_req_synth")}</div></Card>;
  const labels = Array.from(new Set([...Object.keys(data.confusion), ...Object.values(data.confusion).flatMap((v: Any) => Object.keys(v))]));
  return <Card title={t("lab_reason")} subtitle={data.note}><div className="grid grid-cols-3 gap-3 mb-3"><Kpi label="wells" value={data.n} small /><Kpi label="accuracy" value={fmt.pct(data.accuracy)} small /><Kpi label="classes" value={labels.length} small /></div><table className="core"><thead><tr><th>true \ estimated</th>{labels.map((l) => <th key={l} className="num">{l}</th>)}</tr></thead><tbody>{Object.entries(data.confusion).map(([tr, row]: Any) => <tr key={tr}><td className="font-medium">{tr}</td>{labels.map((l) => <td key={l} className={`num ${l === tr && row[l] ? "text-[#9FE6BC] font-semibold" : ""}`}>{row[l] || ""}</td>)}</tr>)}</tbody></table></Card>;
}

function Sens() {
  const { t } = useT();
  const { data, error, loading, reload } = useFetch<Any>("/api/validation/sensitivity");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  return <Card title={t("lab_sensitivity")} subtitle={data.note}><Tornado rows={data.tornado} height={260} /><table className="core mt-3"><thead><tr><th>factor</th><th className="num">low case</th><th className="num">base</th><th className="num">high case</th><th>range</th></tr></thead><tbody>{data.tornado.map((r: Any) => <tr key={r.factor}><td>{r.factor}</td><td className="num">{fmt.money(r.low)}</td><td className="num">{fmt.money(r.base)}</td><td className="num">{fmt.money(r.high)}</td><td className="faint">×{r.range[0]} … ×{r.range[1]}</td></tr>)}</tbody></table></Card>;
}

function Cards() {
  const { data, error, loading, reload } = useFetch<Any>("/api/validation/model-cards");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  return <div className="grid md:grid-cols-2 gap-3">{data.map((c: Any) => <Card key={c.model} title={c.model} subtitle={`v${c.version} · ${c.owner}`}><div className="text-[12px] space-y-1">{["purpose", "fit_data", "features", "assumptions", "limitations", "validation"].map((k) => <div key={k}><span className="faint">{k.replace(/_/g, " ")}: </span>{c[k]}</div>)}</div></Card>)}</div>;
}

export function ModelRuns() {
  const { t } = useT();
  const nav = useNavigate();
  const { data, error, loading, reload } = useFetch<Any>("/api/runs");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  return <Card title={t("runs_title")} subtitle={t("x_cached_runs")}><DataTable id="runs" rows={data.runs} rowKey="analysis_id" columns={[{ key: "analysis_id", label: "ID" }, { key: "well_id", label: t("well") }, { key: "event_label", label: t("intervention") }, { key: "kind", label: t("type") }, { key: "model", label: t("model"), render: (r: Any) => String(r.model || "").replace(/_/g, " ") }, { key: "donor_count", label: t("donors"), num: true }, { key: "mean_effect_bpd", label: t("causal_estimate"), num: true }, { key: "confidence", label: t("confidence"), render: (r: Any) => <Badge label={r.confidence} small /> }, { key: "created_at", label: t("timestamp"), render: (r: Any) => fmt.date(r.created_at) }, { key: "_j", label: "", render: (r: Any) => <a className="btn sm" href={`/api/export/analysis/${r.analysis_id}.json`} onClick={(e) => e.stopPropagation()}>JSON</a> }]} onRow={(r) => nav(`/wells/${r.well_id}?tab=causal`)} defaultSort={{ key: "created_at", dir: "desc" }} /></Card>;
}

export function Network() {
  const { t } = useT();
  const nav = useNavigate();
  const { data, error, loading, reload } = useFetch<Any>("/api/network");
  const [f, setF] = useState<{ field: string; tag: string; wc: number; conf: string; itype: string }>({ field: "", tag: "", wc: 0, conf: "", itype: "" });
  const [hover, setHover] = useState<Any>(null);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={500} />;
  const nodes = data.nodes.filter((n: Any) => (!f.field || n.field === f.field) && (!f.tag || n.tags.includes(f.tag)) && (n.water_cut === null || n.water_cut === undefined || n.water_cut >= f.wc) && (!f.conf || n.confidence === f.conf) && (!f.itype || n.intervention_type === f.itype));
  const ids = new Set(nodes.map((n: Any) => n.id));
  const pos: Record<string, Any> = Object.fromEntries(data.nodes.map((n: Any) => [n.id, n]));
  const color = (n: Any) => n.tags.includes("intervention candidate") ? C.amber : n.tags.includes("underperforming") ? C.blue : n.tags.includes("high-water") ? C.teal : n.status === "idle" ? "rgba(255,255,255,0.35)" : C.green;
  const maxOpp = Math.max(1, ...data.nodes.map((n: Any) => Math.abs(n.opportunity || 0)));
  return (
    <div className="grid gap-3">
      <Card title={t("nav_network")} subtitle={data.note}>
        <div className="flex flex-wrap gap-2 mb-3 text-[12px]">
          <select value={f.field} onChange={(e) => setF({ ...f, field: e.target.value })}><option value="">{t("field_all")}</option>{data.fields.map((x: string) => <option key={x}>{x}</option>)}</select>
          <select value={f.tag} onChange={(e) => setF({ ...f, tag: e.target.value })}><option value="">{t("status")}</option>{["producing", "idle", "high-water", "underperforming", "intervention candidate", "insufficient data"].map((x) => <option key={x} value={x}>{x}</option>)}</select>
          <select value={f.conf} onChange={(e) => setF({ ...f, conf: e.target.value })}><option value="">{t("confidence")}</option>{["HIGH CONFIDENCE", "MODERATE CONFIDENCE", "LOW CONFIDENCE"].map((x) => <option key={x} value={x}>{x}</option>)}</select>
          <select value={f.itype} onChange={(e) => setF({ ...f, itype: e.target.value })}><option value="">{t("est_intervention")}</option>{["restart", "pump_replacement", "cleanout", "water_shutoff", "stimulation", "workover"].map((x) => <option key={x} value={x}>{iType(t, x)}</option>)}</select>
          <label className="chip">{t("water_cut")} ≥ {fmt.pct(f.wc)}<input type="range" min={0} max={0.98} step={0.02} value={f.wc} onChange={(e) => setF({ ...f, wc: Number(e.target.value) })} style={{ width: 100 }} /></label>
          <span className="faint self-center">{nodes.length} wells</span>
        </div>
        <div className="glass-inner" style={{ height: 560, position: "relative", overflow: "visible" }}>
          <svg viewBox="0 0 1000 520" width="100%" height="100%">
            {data.edges.filter((e: Any) => ids.has(e.source) && ids.has(e.target)).map((e: Any, i: number) => <line key={i} x1={pos[e.source].x} y1={pos[e.source].y} x2={pos[e.target].x} y2={pos[e.target].y} stroke={e.kind === "donor" ? C.blue : C.amber} strokeOpacity={0.35} strokeWidth={1} />)}
            {data.fields.map((fl: string, i: number) => <text key={fl} x={200 + i * 320} y={30} textAnchor="middle" fill="rgba(244,245,247,0.5)" fontSize="13">{fl}</text>)}
            {nodes.map((n: Any) => <circle key={n.id} cx={n.x} cy={n.y} r={4 + 9 * Math.sqrt(Math.abs(n.opportunity || 0) / maxOpp)} fill={color(n)} fillOpacity={0.85} stroke="rgba(255,255,255,0.4)" style={{ cursor: "pointer", filter: n.tags.includes("intervention candidate") ? "drop-shadow(0 0 6px rgba(242,182,50,0.7))" : undefined }} onMouseEnter={() => setHover(n)} onMouseLeave={() => setHover(null)} onClick={() => nav(`/wells/${n.id}`)}><title>{n.id}</title></circle>)}
          </svg>
          {hover && <div className="glass-strong p-3 text-[12px] absolute" style={{ left: 12, bottom: 12 }}><b>{hover.id}</b> · {hover.field}<div className="faint">{hover.tags.join(" · ")}</div><div>{t("water_cut")} {fmt.pct(hover.water_cut)} · {t("value")} {fmt.money(hover.opportunity)} · {hover.confidence || "—"}</div></div>}
          <div className="absolute right-3 top-3 text-[11px] glass-strong p-2 space-y-1">{[["intervention candidate", C.amber], ["underperforming", C.blue], ["high-water", C.teal], ["producing", C.green], ["idle", "rgba(255,255,255,0.35)"]].map(([l, c]) => <div key={l} className="flex items-center gap-2"><span className="inline-block w-3 h-3 rounded-full" style={{ background: c as string }} />{l}</div>)}<div className="faint">edge: donor (blue) · analogue restart (amber)</div></div>
        </div>
      </Card>
    </div>
  );
}
