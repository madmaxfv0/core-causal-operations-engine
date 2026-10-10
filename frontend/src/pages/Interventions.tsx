import React, { useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Bars, C, HeroChart, Histogram, Matrix, TrendChart } from "../charts";
import { DataTable } from "../components/DataTable";
import { useApp } from "../components/Shell";
import { Badge, Card, ErrorBox, Icon, Kpi, LabeledValue, Progress, Provenance, Skeleton, useFetch, useToast } from "../components/ui";
import { Any, api, download, fmt, toCSV, iType } from "../lib/api";
import { useProv } from "../lib/provenance";
import { useT } from "../lib/i18n";

export function Interventions() {
  const prov = useProv();
  const { t } = useT();
  const { field } = useApp();
  const nav = useNavigate();
  const { data, error, loading, reload } = useFetch<Any>(`/api/interventions${field ? `?field=${encodeURIComponent(field)}` : ""}`);
  const cols = useMemo(() => [
    { key: "intervention_id", label: "ID", render: (r: Any) => <span className="font-medium">{r.intervention_id}</span> }, { key: "well_id", label: t("well") }, { key: "date", label: t("date") }, { key: "type", label: t("type"), render: (r: Any) => <span>{iType(t, r.type)}{!r.recorded && <span className="faint"> (observed)</span>}</span> },
    { key: "cost", label: t("cost"), num: true, render: (r: Any) => <span>{fmt.money(r.cost)}{r.cost_source !== "RECORD" && <span className="faint"> *</span>}</span> }, { key: "pre_rate_bpd", label: "pre bbl/d", num: true, render: (r: Any) => fmt.n(r.pre_rate_bpd, 1) }, { key: "post_rate_bpd", label: "post bbl/d", num: true, render: (r: Any) => fmt.n(r.post_rate_bpd, 1) },
    { key: "naive_gain_bpd", label: t("naive_estimate"), num: true, render: (r: Any) => <span style={{ color: C.red }}>{fmt.n(r.naive_gain_bpd, 1)}</span> }, { key: "causal_gain_bpd", label: t("causal_estimate"), num: true, render: (r: Any) => <span style={{ color: C.amber }}>{fmt.n(r.causal_gain_bpd, 1)} <span className="faint">({fmt.range(r.gain_lo_bpd, r.gain_hi_bpd, 1)})</span></span> },
    { key: "cumulative_oil_bbl", label: t("cumulative_oil"), num: true, render: (r: Any) => fmt.n(r.cumulative_oil_bbl) }, { key: "water_change_bpd", label: "Δ water", num: true, render: (r: Any) => fmt.n(r.water_change_bpd, 1) }, { key: "duration_months", label: t("duration"), num: true }, { key: "net_value", label: t("npv"), num: true, render: (r: Any) => <span className={r.net_value > 0 ? "text-[#9FE6BC]" : "text-[#FFB3A8]"}>{fmt.money(r.net_value)}</span> },
    { key: "confidence", label: t("confidence"), render: (r: Any) => <Badge label={r.confidence} small /> }, { key: "evidence_status", label: t("evidence"), render: (r: Any) => <Badge label={r.evidence_status} small color={r.evidence_status === "COMPLETE" ? "green" : "grey"} /> },
  ], [t]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={500} />;
  const k = data.kpis || {}, ch = data.charts || {};
  // A data set can legitimately contain no recorded jobs (public volumetric data has
  // none). Render an honest empty state instead of charting undefined.
  if (data.has_history === false || !data.rows?.length) {
    return (
      <div className="grid gap-3">
        <h1 style={{ fontSize: 28 }}>{t("mem_title")}</h1>
        <Card title={t("iv_none_title")}>
          <div className="subtle text-[13px] max-w-[760px]">{t("iv_none_body")}</div>
          <div className="flex gap-2 mt-3">
            <button className="btn sm" onClick={() => nav("/data")}>{t("nav_datahub")}</button>
            <button className="btn sm" onClick={() => nav("/data/imports")}>{t("x_import_int")}</button>
          </div>
        </Card>
      </div>
    );
  }
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Kpi label={t("mem_jobs")} provenance={prov("mem_jobs")} value={k.jobs_analysed} small sub={`${k.recorded_jobs} recorded · ${k.observed_restarts} observed restarts`} />
        <Kpi label={t("mem_spend")} provenance={prov("mem_spend")} value={fmt.money(k.total_spend)} small badge={<Badge label="* illustrative for observed restarts" color="amber" small />} />
        <Kpi label={t("mem_created")} provenance={prov("mem_created")} value={fmt.money(k.value_created)} small />
        <Kpi label={t("mem_destroyed")} provenance={prov("mem_destroyed")} value={fmt.money(k.value_destroyed)} small />
        <Kpi label={t("mem_anyway")} provenance={prov("mem_anyway")} value={k.would_have_improved_anyway} small sub="causal ≤ 25% of naive claim" />
        <Kpi label={t("mem_naive")} provenance={prov("mem_naive")} value={`+${fmt.n(k.naive_uplift_bpd)}`} unit="bbl/d" small sub="recorded interventions" />
        <Kpi label={t("mem_causal")} provenance={prov("mem_causal")} value={`+${fmt.n(k.causal_uplift_bpd)}`} unit="bbl/d" small sub="recorded interventions" />
        <Kpi label={t("mem_pos")} value={k.positive_payback} small />
        <Kpi label={t("mem_neg")} value={k.negative_payback} small />
        <Kpi label={t("mem_insuff")} value={k.insufficient_evidence} small />
      </div>
      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
        <Card title={t("ch_naive_vs_causal")}><Matrix points={ch.scatter.map((s: Any) => ({ ...s, label: `${s.intervention_id} ${s.well_id}`, x: s.naive, y: Math.max(0, Math.min(1, (s.causal + 10) / 40)), z: 1, color: s.causal >= s.naive ? C.green : C.amber, sub: `naive ${fmt.n(s.naive, 1)} · causal ${fmt.n(s.causal, 1)} bbl/d` }))} xLabel={t("naive")} yLabel={t("core")} onPoint={(p) => nav(`/interventions/${p.intervention_id}`)} name="naive_vs_causal" height={240} /></Card>
        <Card title={t("ch_outcomes")}><Histogram edges={ch.outcome_bins.edges} counts={ch.outcome_bins.counts} height={240} xFmt={(a, b) => `${a}…${b}`} name="outcomes" /></Card>
        <Card title={t("ch_success")}><Bars data={ch.by_type} xKey="type" series={[{ key: "success_rate", name: t("ch_success") }]} fmtv={(v) => fmt.pct(v)} height={240} name="success_by_type" /></Card>
        <Card title={t("ch_payback")}><Bars data={ch.by_type.map((x: Any) => ({ ...x, median_payback: x.median_payback ?? 0 }))} xKey="type" series={[{ key: "median_payback", name: `${t("payback")} (${t("months")})`, color: C.blue }]} height={240} name="payback_by_type" /></Card>
        <Card title={t("ch_archetype")}><Bars data={ch.by_archetype} xKey="archetype" series={[{ key: "median_causal_bpd", name: "median causal bbl/d" }]} height={240} name="uplift_archetype" /></Card>
        <Card title={t("ch_water_type")}><Bars data={ch.by_type.map((x: Any) => ({ ...x, water_change_bpd: x.water_change_bpd ?? 0 }))} xKey="type" series={[{ key: "water_change_bpd", name: "Δ water bbl/d", color: C.blue }]} height={240} name="water_by_type" colorBy={(d) => (d.water_change_bpd <= 0 ? C.green : C.red)} /></Card>
        <Card title={t("ch_persistence")}><Bars data={Object.entries(ch.persistence).map(([m, v]) => ({ m: `${m}M`, v }))} xKey="m" series={[{ key: "v", name: "mean effect bbl/d" }]} height={240} name="persistence" /></Card>
        <Card title={t("ch_cost_value")}><Matrix points={ch.scatter.map((s: Any) => ({ ...s, label: `${s.intervention_id} ${s.well_id}`, x: s.cost, y: Math.max(0, Math.min(1, (s.value + 2e5) / 1.2e6)), z: 1, color: s.value > 0 ? C.green : C.red, sub: `NPV ${fmt.money(s.value)}` }))} xLabel={t("cost")} yLabel={t("value")} xFmt={(v) => fmt.money(v)} onPoint={(p) => nav(`/interventions/${p.intervention_id}`)} name="cost_value" height={240} /></Card>
        <Card title={t("ch_conf")}><Bars data={Object.entries(ch.confidence).map(([c, n]) => ({ c, n }))} xKey="c" series={[{ key: "n", name: "analyses" }]} height={240} name="confidence_dist" colorBy={(d) => (d.c.startsWith("HIGH") ? C.green : d.c.startsWith("MOD") ? C.amber : d.c.startsWith("LOW") ? C.red : C.muted)} /></Card>
        <Card title={t("ch_time")} className="md:col-span-2 xl:col-span-3"><TrendChart data={ch.over_time} xKey="year" series={[{ key: "naive_bpd", name: t("naive"), color: C.red, type: "bar" }, { key: "causal_bpd", name: t("core"), color: C.amber, type: "bar" }, { key: "n", name: "jobs", type: "line", color: C.blue, axis: "right" }]} height={220} name="over_time" /></Card>
      </div>
      <Card title={t("mem_title")} subtitle="* cost is an illustrative assumption where no record exists (observed restarts)"><DataTable id="interventions" rows={data.rows} rowKey="intervention_id" columns={cols} onRow={(r) => nav(`/interventions/${r.intervention_id}`)} defaultSort={{ key: "date", dir: "desc" }} searchKeys={["intervention_id", "well_id", "type", "date", "confidence"]} /></Card>
    </div>
  );
}

export function InterventionDetail() {
  const { id } = useParams();
  const { t } = useT();
  const nav = useNavigate();
  const toast = useToast();
  const { data, error, loading, reload } = useFetch<Any>(`/api/interventions/${id}`);
  const [note, setNote] = useState("");
  const [steps, setSteps] = useState<string[] | null>(null);
  const [analysis, setAnalysis] = useState<Any>(null);
  const donorsRef = useRef<HTMLDivElement>(null);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={500} />;
  const r = data.row, a = analysis || data.analysis, ev = data.type_evidence;
  const rerun = async () => { setSteps(["Queued"]); try { const j = await api.post(`/api/wells/${r.well_id}/causal/run`, { pre_end: r.pre_end_t, post_start: r.post_start_t, model: "auto", kind: r.kind }); const res = await api.job(j.job_id, setSteps); setAnalysis(res); setSteps(null); toast(`${t("rerun")} ✓`); } catch (e: Any) { setSteps(null); toast(e.message, "err"); } };
  const addNote = async () => { if (!note.trim()) return; await api.post(`/api/notes/${id}`, { text: note }); setNote(""); toast(t("note_saved")); reload(); };
  const review = async () => { await api.post(`/api/reviewed/${id}`); toast(t("reviewed") + " ✓"); reload(); };
  return (
    <div className="grid gap-3">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><div className="flex items-center gap-2 flex-wrap"><h1 style={{ fontSize: 30 }}>{id}</h1><Badge label={r.confidence} /><Badge label={r.evidence_status} color={r.evidence_status === "COMPLETE" ? "green" : "grey"} small />{data.reviewed && <Badge label={t("reviewed")} color="blue" small />}</div>
            <div className="subtle text-[13px] mt-1"><button className="hover:underline font-medium" onClick={() => nav(`/wells/${r.well_id}`)}>{r.well_id}</button> · {r.date} · {iType(t, r.type)} {r.recorded ? "" : "(observed restart, no record)"} · {r.field} · {r.archetype}</div></div>
          <div className="flex gap-2 flex-wrap">
            <button className="btn" onClick={() => donorsRef.current?.scrollIntoView({ behavior: "smooth" })}>{t("view_evidence")}</button>
            <button className="btn" onClick={() => nav(`/wells/${r.well_id}?tab=causal`)}>{t("view_donors")}</button>
            <button className="btn primary" onClick={rerun} disabled={!!steps}><Icon name="play" size={14} />{t("rerun")}</button>
            <button className="btn" onClick={() => nav("/settings")}>{t("change_assumptions")}</button>
            <button className="btn" onClick={review}>{t("mark_reviewed")}</button>
            <a className="btn" href={`/api/export/well/${r.well_id}/report.pdf`}><Icon name="download" size={14} />{t("export_pdf")}</a>
            <button className="btn" onClick={() => download(`${id}.csv`, toCSV([r], Object.keys(r).filter((k) => typeof r[k] !== "object")))}><Icon name="download" size={14} />{t("export_csv")}</button>
          </div>
        </div>
      </Card>
      {steps && <Progress steps={steps} label={t("rerun")} />}
      {a && <Card title={<span className="flex items-center gap-2">{t("hero_cf")} <Provenance data={{ model: a.model_label, donors: a.diagnostics?.donor_count, pre_window: a.diagnostics?.pre_window, post_window: a.diagnostics?.post_window, pre_r2: a.diagnostics?.pre_r2, interval_80: `${a.effect_lo_bpd}–${a.effect_hi_bpd} bbl/d`, last_run: a.created_at, model_version: a.meta?.model_version }} /></span>}><HeroChart analysis={a} /></Card>}
      <div className="grid md:grid-cols-3 gap-3">
        <Card title={t("value")}><div className="grid grid-cols-2 gap-3 text-[13px]"><LabeledValue label={t("cost")} value={fmt.money(r.cost)} sub={r.cost_source} /><LabeledValue label={t("npv")} value={fmt.money(r.net_value)} sub={r.value_basis} /><LabeledValue label={t("payback")} value={r.payback_months ? `${r.payback_months} ${t("months")}` : "—"} /><LabeledValue label={t("cumulative_oil")} value={`${fmt.n(r.cumulative_oil_bbl)} bbl`} /><LabeledValue label="Δ water" value={`${fmt.n(r.water_change_bpd, 1)} bbl/d`} /><LabeledValue label={t("duration")} value={r.duration_months !== null ? `${r.duration_months} ${t("months")}` : "—"} /></div>{r.truth && <div className="glass-inner p-2 mt-3 text-[12px]"><Badge label={t("x_synth_truth")} color="blue" small /> planted effect {fmt.n(r.truth.true_effect_bpd_12m, 1)} bbl/d</div>}</Card>
        <Card title={t("operating_memory")}>{ev.n ? <div className="text-[13px] space-y-1"><div>{ev.n} {iType(t, r.type)} jobs analysed</div><div>median effect <b>{fmt.n(ev.median_effect_bpd, 1)}</b> bbl/d (P20 {fmt.n(ev.p20_effect_bpd, 1)} · P80 {fmt.n(ev.p80_effect_bpd, 1)})</div><div>paid back {fmt.pct(ev.success_rate)} · positive effect {fmt.pct(ev.positive_effect_rate)}</div><div>median cost {fmt.money(ev.median_cost)} · Δ water {fmt.n(ev.median_water_change_bpd, 1)} bbl/d</div><div className="faint">failures: {ev.failures.join(", ") || "none"}</div></div> : <div className="subtle">{t("x_insuff_ev")}</div>}</Card>
        <Card title={t("notes")}><textarea className="w-full" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("add_note")} /><button className="btn sm mt-2" onClick={addNote}>{t("add_note")}</button><div className="space-y-1 mt-2 text-[12px]">{data.notes.map((n: Any) => <div key={n.note_id} className="glass-inner p-2"><span className="faint">{fmt.date(n.timestamp)}</span> {n.text}</div>)}</div></Card>
      </div>
      <div ref={donorsRef}>
        {a && <Card title={t("donors")} subtitle={`${a.diagnostics?.donor_count} donors · ${a.model_label}`}><DataTable id="int-donors" rows={a.donors} columns={[{ key: "well_id", label: t("well") }, { key: "similarity", label: t("similarity"), num: true, render: (x: Any) => fmt.n(x.similarity, 3) }, { key: "pre_rate_bpd", label: "pre bbl/d", num: true, render: (x: Any) => fmt.n(x.pre_rate_bpd, 1) }, { key: "water_cut", label: t("water_cut"), num: true, render: (x: Any) => fmt.pct(x.water_cut) }, { key: "weight", label: t("weight"), num: true, render: (x: Any) => fmt.n(x.weight, 3) }, { key: "reasons", label: t("reason_selected"), render: (x: Any) => <span className="faint">{(x.reasons || []).join("; ")}</span> }]} onRow={(x) => nav(`/wells/${x.well_id}`)} dense defaultSort={{ key: "weight", dir: "desc" }} /></Card>}
      </div>
      <Card title={t("tab_documents")}>{data.documents.length ? data.documents.map((d: Any) => <button key={d.document_id} className="block glass-inner p-2 text-[12px] mb-1 w-full text-left hover:bg-white/10" onClick={() => nav(`/archive?doc=${d.document_id}`)}>{d.file_name} <Badge label={d.review_status} small /></button>) : <div className="subtle text-[13px]">{t("x_no_src_docs")} <button className="btn sm ml-2" onClick={() => nav("/archive")}>{t("upload")}</button></div>}</Card>
    </div>
  );
}

export function CompareTreatments() {
  const { t } = useT();
  const { data, error, loading, reload } = useFetch<Any>("/api/interventions");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (loading || !data) return <Skeleton h={300} />;
  const types = ["pump_optimisation", "pump_replacement", "cleanout", "water_shutoff", "stimulation", "workover", "restart", "observed_restart"];
  const rows = types.map((ty) => ({ type: ty, ...(data.type_evidence[ty] || { n: 0, status: "INSUFFICIENT EVIDENCE" }) }));
  return (
    <Card title={t("compare_title")} subtitle={t("x_rows_families")}>
      <table className="core"><thead><tr><th>{t("type")}</th><th className="num">{t("evidence")} (n)</th><th className="num">median oil effect</th><th className="num">P20–P80</th><th className="num">Δ water</th><th className="num">{t("success_prob")}</th><th className="num">median {t("cost")}</th><th className="num">median {t("duration")}</th><th>{t("confidence")}</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.type}><td>{iType(t, r.type)}</td><td className="num">{r.n}</td>{r.n >= 3 ? <><td className="num">{fmt.n(r.median_effect_bpd, 1)} bbl/d</td><td className="num">{fmt.range(r.p20_effect_bpd, r.p80_effect_bpd, 1)}</td><td className="num">{fmt.n(r.median_water_change_bpd, 1)}</td><td className="num">{fmt.pct(r.positive_effect_rate)}</td><td className="num">{fmt.money(r.median_cost)}</td><td className="num">{r.median_duration ?? "—"}</td><td><Badge label={r.n >= 8 ? "MODERATE CONFIDENCE" : "LOW CONFIDENCE"} small /></td></> : <td colSpan={7}><Badge label={t("x_insuff_ev")} /> <span className="faint text-[12px]">fewer than 3 analysed jobs</span></td>}</tr>)}</tbody></table>
    </Card>
  );
}
