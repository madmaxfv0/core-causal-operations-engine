/**
 * Public well record panel.
 *
 * Rule enforced throughout: a value is shown only when a real public record
 * supplies it.  Anything with no public source reads "Not publicly available",
 * and every section states which dataset it came from.
 */
import React, { useEffect, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Card, ErrorBox, Skeleton, Tabs, useFetch } from "../../components/ui";
import { HoverCard } from "../../components/overlay";
import { Any, api, fmt } from "../../lib/api";
import { useT } from "../../lib/i18n";

const M3_TO_BBL = 6.28981;
const E3M3_TO_MSCF = 35.3147;

/** Module-level, so it takes the translator explicitly. */
const naText = (t: (k: any) => string) => <span className="faint">{t("x_not_public")}</span>;

function Row({ label, value, note }: { label: React.ReactNode; value: React.ReactNode; note?: React.ReactNode }) {
  const { t } = useT();
  const NA = naText(t);
  return (
    <div className="min-w-0">
      <div className="faint text-[11px]">{label}</div>
      <div className="text-[13px] font-medium break-words">{value ?? NA}</div>
      {note && <div className="faint text-[11px]">{note}</div>}
    </div>
  );
}

function Explain({ calc, children }: { calc: Any; children: React.ReactNode }) {
  const { t } = useT();
  if (!calc) return <>{children}</>;
  return (
    <HoverCard
      side="left" align="center" width={330} label={t("m_how_calc")}
      content={
        <div className="space-y-1.5">
          <div className="font-semibold">{t("x_how_calc2")}</div>
          <div><span className="faint">{t("x_formula2")} </span>{calc.formula}</div>
          {calc.days && <div><span className="faint">{t("x_days_month")} </span>{calc.days}</div>}
          <div><span className="faint">{t("x_result")} </span>{fmt.n(calc.value, 2)} {calc.unit}</div>
          <div className="flex gap-1 pt-1"><Badge label={calc.value_type} color="blue" small /></div>
          <div className="faint">Source: {calc.source}</div>
        </div>
      }
    >
      <span className="underline decoration-dotted underline-offset-4">{children}</span>
    </HoverCard>
  );
}

export function WellPanel({ data, loading, error }: { data: Any; loading: boolean; error: Any }) {
  const { t } = useT();
  const NA = naText(t);
  const [tab, setTab] = useState("overview");
  const [live, setLive] = useState<Any>(null);
  const recordId = data?.well?.record_id;
  useEffect(() => {
    if (!recordId) return;
    let alive = true;
    const load = () => api.get(`/api/scada/wells/${encodeURIComponent(recordId)}/telemetry`).then((value) => {
      if (alive) setLive(value);
    }).catch(() => { if (alive) setLive(null); });
    load();
    const timer = window.setInterval(load, 30_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [recordId]);
  if (loading) return <Skeleton h={360} />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const w = data.well || {};
  const calc = data.calculated || {};
  const history: Any[] = data.production_history || [];
  const latest = data.production_latest;
  const integrity = data.integrity || {};
  const chart = history.map((h) => ({
    month: h.month,
    oil_bbl: h.oil_m3 == null ? null : h.oil_m3 * M3_TO_BBL,
    water_bbl: h.water_m3 == null ? null : h.water_m3 * M3_TO_BBL,
    gas_mscf: h.gas_e3m3 == null ? null : h.gas_e3m3 * E3M3_TO_MSCF,
    water_cut: h.water_cut == null ? null : h.water_cut * 100,
  }));

  return (
    <div className="grid gap-3 text-[13px]">
      <div className="flex flex-wrap gap-2 items-center">
        <Badge label={w.status || "Status not reported"} color={w.status === "Abandoned" ? "red" : w.status === "Active" ? "green" : "amber"} />
        <Badge label={w.fluid || "Fluid not reported"} color="grey" />
        <Badge label={t("m_real_public")} color="blue" small />
        {w.uwi && <Badge label={t("m_linked_petrinex")} color="green" small />}
      </div>

      <Tabs
        value={tab} onChange={setTab}
        tabs={[
          { key: "overview", label: "Overview" },
          { key: "production", label: "Production" },
          { key: "integrity", label: "Integrity" },
          { key: "calculator", label: "Calculator" },
          { key: "details", label: "Well details" },
          { key: "sources", label: "Data sources" },
        ]}
      />

      {tab === "overview" && (
        <>
          <Card title={t("m_identification")}>
            <div className="grid grid-cols-2 gap-3">
              <Row label={t("m_st37_record")} value={w.record_id} />
              <Row label={t("m_uwi")} value={w.uwi || NA} note={w.uwi ? "matched by legal location" : "no unique match"} />
              <Row label={t("m_operator_licensee")} value={w.operator || NA} note={w.operator ? "Petrinex reporting operator" : undefined} />
              <Row label={t("m_aer_category")} value={w.well_category} />
              <Row label={t("m_derived_status")} value={w.status} note="derived from AER category" />
              <Row label={t("m_derived_fluid")} value={w.fluid} note="derived from AER category" />
            </div>
            <div className="faint text-[11px] mt-2">{data.identity_note}</div>
          </Card>
          <Card title={t("m_location")}>
            <div className="grid grid-cols-2 gap-3">
              <Row label={t("m_latitude")} value={w.latitude?.toFixed(6)} />
              <Row label={t("m_longitude")} value={w.longitude?.toFixed(6)} />
              <Row label={t("m_surface_loc")} value={w.surface_location} />
              <Row label={t("m_legal_loc")} value={w.legal_location_text} />
              <Row label={t("m_bottomhole")} value={NA} note="not in the imported ST37 package" />
              <Row label={t("m_crs")} value="WGS84 (EPSG:4326), as served by AER" />
            </div>
          </Card>
          {latest && (
            <Card title={`Latest reported month — ${latest.month}`}>
              <div className="grid grid-cols-3 gap-3">
                <Row label="Oil" value={latest.oil_m3 == null ? NA : <>{fmt.n(latest.oil_m3, 1)} m³ <span className="faint">≈ {fmt.n(latest.oil_m3 * M3_TO_BBL, 0)} bbl</span></>} />
                <Row label="Gas" value={latest.gas_e3m3 == null ? NA : <>{fmt.n(latest.gas_e3m3, 1)} e3m³</>} />
                <Row label={t("x_water2")} value={latest.water_m3 == null ? NA : <>{fmt.n(latest.water_m3, 1)} m³</>} />
                <Row label={t("m_avg_oil")} value={calc.oil_rate ? <Explain calc={calc.oil_rate}>{fmt.n(calc.oil_rate.value, 2)} m³/d</Explain> : NA} note="calculated" />
                <Row label={t("m_water_cut")} value={calc.water_cut?.value == null ? NA : <Explain calc={calc.water_cut}>{fmt.pct(calc.water_cut.value, 1)}</Explain>} note="calculated" />
                <Row label={t("m_hours")} value={latest.hours == null ? NA : fmt.n(latest.hours, 0)} />
              </div>
            </Card>
          )}
          <Card title={t("m_live_telemetry")}>
            <div className="grid grid-cols-2 gap-2">
              {Object.keys(data.telemetry || {}).map((k) => (
                <div key={k} className="flex justify-between glass-inner px-3 py-1.5">
                  <span className="subtle">{k.replace(/_/g, " ")}</span><span className="faint">
                    {live?.telemetry?.[k] == null ? "—" : live.telemetry[k]}
                  </span>
                </div>
              ))}
            </div>
            <div className="faint text-[11px] mt-2">{live?.message || data.telemetry_note}</div>
            {live?.observed_at && <div className="faint text-[11px]">Observed at: {fmt.date(live.observed_at)}</div>}
          </Card>
        </>
      )}

      {tab === "production" && (
        <>
          {!history.length ? (
            <Card title={t("m_reported_prod")}>
              <div className="subtle">{t("x_not_public_rec")}</div>
              <div className="faint text-[12px] mt-1">{data.identity_note}</div>
            </Card>
          ) : (
            <>
              <Card title={t("x_rep_month_prod")} subtitle={t("x_petrinex_note")}>
                <div style={{ width: "100%", height: 240 }}>
                  <ResponsiveContainer>
                    <ComposedChart data={chart} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                      <CartesianGrid stroke="rgba(255,255,255,0.07)" />
                      <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                      <YAxis yAxisId="l" tick={{ fontSize: 10 }} />
                      <YAxis yAxisId="r" orientation="right" domain={[0, 100]} tick={{ fontSize: 10 }} />
                      <Tooltip contentStyle={{ background: "rgba(16,22,36,0.94)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12, fontSize: 12 }} />
                      <Area yAxisId="l" dataKey="oil_bbl" name="Oil (bbl)" stroke="#5CC489" fill="rgba(92,196,137,0.22)" />
                      <Area yAxisId="l" dataKey="water_bbl" name="Water (bbl)" stroke="#5AC8E0" fill="rgba(90,200,224,0.14)" />
                      <Line yAxisId="r" dataKey="water_cut" name="Water cut (%)" stroke="#F2B632" dot={false} strokeWidth={2} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <div className="faint text-[11px] mt-1">
                  Reported in m³ / e3m³; barrels shown alongside using 1 m³ = 6.28981 bbl. Both are kept visible.
                </div>
              </Card>
              {calc.trend && (
                <Card title={t("m_prod_trend")} subtitle={t("x_calc_monthly")}>
                  <div className="grid grid-cols-3 gap-3">
                    <Row label={t("x_recent3")} value={`${fmt.n(calc.trend.recent_3_month_avg_m3, 1)} m³/mo`} />
                    <Row label={`Prior ${calc.trend.prior_months}-month avg`} value={`${fmt.n(calc.trend.prior_average_m3, 1)} m³/mo`} />
                    <Row label={t("x_change")} value={calc.trend.change_fraction == null ? NA : fmt.pct(calc.trend.change_fraction, 1)} />
                  </div>
                  {calc.trend.flag && <div className="mt-2"><Badge label={calc.trend.flag} color="amber" /></div>}
                  <div className="faint text-[11px] mt-2">{calc.trend.formula}. Source: {calc.trend.source}.</div>
                </Card>
              )}
              <Card title={t("m_reported_months")}>
                <div className="max-h-56 overflow-auto space-y-1">
                  {[...history].reverse().map((h: Any) => (
                    <div key={h.month} className="glass-inner px-3 py-1.5 flex justify-between gap-2 text-[12px]">
                      <span className="font-medium">{h.month}</span>
                      <span>{h.oil_m3 == null ? "—" : `${fmt.n(h.oil_m3, 1)} m³ oil`}</span>
                      <span className="faint">{h.gas_e3m3 == null ? "—" : `${fmt.n(h.gas_e3m3, 1)} e3m³ gas`}</span>
                      <span className="faint">{h.water_m3 == null ? "—" : `${fmt.n(h.water_m3, 1)} m³ water`}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </>
          )}
        </>
      )}

      {tab === "integrity" && (
        <Card title={t("m_integrity")} subtitle={t("x_matched_integrity")}>
          <div className="space-y-2">
            <div className="flex justify-between glass-inner px-3 py-2">
              <span>{t("x_casing_failure")}</span>
              <b>{integrity.casing_failure?.length ? "Reported" : "No matching public record"}</b>
            </div>
            <div className="flex justify-between glass-inner px-3 py-2">
              <span>{t("x_vent_flow2")}</span>
              <b>{integrity.vent_flow?.length ? "Reported" : "No matching public record"}</b>
            </div>
            <div className="flex justify-between glass-inner px-3 py-2">
              <span>{t("x_aer_abandoned_ds")}</span>
              <b>{integrity.abandoned?.length ? "Matched" : "No matching public record"}</b>
            </div>
            {(integrity.casing_failure || []).concat(integrity.vent_flow || []).map((rec: Any, i: number) => (
              <pre key={i} className="glass-inner p-2 text-[11px] whitespace-pre-wrap">{JSON.stringify(rec, null, 1)}</pre>
            ))}
          </div>
          <div className="faint text-[11px] mt-3">
            Absence from a public report does not prove that no condition exists. Annulus pressure, casing
            pressure, sustained casing pressure and barrier telemetry have no public Alberta source and are
            <b> Not publicly available</b> until an operator connector is installed.
          </div>
        </Card>
      )}

      {tab === "calculator" && <PublicCalculator recordId={w.record_id} />}

      {tab === "details" && (
        <Card title={t("m_well_structure")}>
          <div className="grid grid-cols-2 gap-3">
            <Row label={t("x_surface_hole")} value={w.surface_location} />
            <Row label={t("x_bottom_hole")} value={NA} note="not in the imported ST37 package" />
            <Row label={t("x_prod_strings")} value={NA} note="ST37 full package required" />
            <Row label={t("x_deviation")} value={NA} note="ST37 full package required" />
            <Row label={t("x_spud")} value={NA} note="AER well licence list required" />
            <Row label={t("x_field_pool")} value={NA} note="AER field & pool code datasets required" />
            <Row label={t("x_rep_facility")} value={w.facility_name || NA} note={w.facility_id ? `Petrinex ${w.facility_id}` : undefined} />
            <Row label={t("x_months_reported")} value={w.months_reported == null ? NA : fmt.n(w.months_reported)} />
          </div>
          <div className="faint text-[11px] mt-2">
            Missing rows are fields the imported public datasets do not contain. They are left empty rather
            than filled with an estimate.
          </div>
        </Card>
      )}

      {tab === "sources" && (
        <Card title={t("m_where_from")}>
          <div className="space-y-2">
            {Object.entries(data.sources || {}).map(([key, value]: Any) => (
              <div key={key} className="glass-inner p-3">
                <div className="font-medium mb-1">{key.replace(/_/g, " ")}</div>
                {typeof value === "string"
                  ? <div className="subtle">{value}</div>
                  : <div className="grid gap-0.5">{Object.entries(value || {}).map(([k, v]: Any) => (
                      <div key={k} className="flex gap-2 text-[12px]">
                        <span className="faint min-w-[130px]">{k.replace(/_/g, " ")}</span>
                        <span className="flex-1 break-words">{typeof v === "object" ? JSON.stringify(v) : String(v ?? "—")}</span>
                      </div>))}
                    </div>}
              </div>
            ))}
          </div>
          <div className="faint text-[11px] mt-3">
            Public well and production information is sourced from Alberta Energy Regulator and Petrinex
            public datasets. Availability and reporting frequency vary by dataset.
          </div>
        </Card>
      )}
    </div>
  );
}


/**
 * Public-data calculator.
 *
 * Runs CORE's own economics engine on this well's REPORTED Petrinex volumes.
 * Inputs with no public source are listed as unavailable and are never filled
 * with a generated value — the engineer enters them or connects SCADA.
 */
function PublicCalculator({ recordId }: { recordId: string }) {
  const { t } = useT();
  const inputs = useFetch<Any>(`/api/map/wells/${encodeURIComponent(recordId)}/calculator-inputs`, [recordId]);
  const [form, setForm] = useState({ uplift_fraction: 0.15, water_change_fraction: 0, success_probability: 0.7, horizon_months: 24, intervention_type: "cleanout" });
  const [run, setRun] = useState<Any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Any>(null);
  useEffect(() => { setRun(null); setErr(null); }, [recordId]);
  const available = inputs.data?.available || {};
  const unavailable = inputs.data?.unavailable || {};
  const hasBaseline = !!available.oil_bpd;

  const submit = async () => {
    setBusy(true); setErr(null);
    try { setRun(await api.post(`/api/map/wells/${encodeURIComponent(recordId)}/scenario`, form)); }
    catch (e: Any) { setErr(e); }
    finally { setBusy(false); }
  };

  if (inputs.loading) return <Skeleton h={280} />;
  if (inputs.error) return <ErrorBox error={inputs.error} onRetry={inputs.reload} />;

  return (
    <div className="grid gap-3">
      <Card title={t("x_inputs_public")} subtitle={t("x_filled_auto")}>
        {!Object.keys(available).length && <div className="subtle">{t("x_no_pub_prod")}</div>}
        <div className="grid gap-2">
          {Object.entries(available).map(([key, v]: Any) => (
            <div key={key} className="glass-inner px-3 py-2 flex flex-wrap items-center justify-between gap-2">
              <span className="subtle">{v.name}</span>
              <span className="flex items-center gap-2">
                <b>{v.value == null ? "—" : fmt.n(v.value, 2)} <span className="faint">{v.unit}</span></b>
                {v.formula
                  ? <Explain calc={v}><Badge label={v.value_type} color="blue" small /></Explain>
                  : <Badge label={v.value_type} color="blue" small />}
              </span>
            </div>
          ))}
        </div>
        {!!Object.keys(available).length && (
          <div className="faint text-[11px] mt-2">
            Source: Petrinex · production month {available.oil_bpd?.production_month || available.gas_e3m3_per_day?.production_month}.
            Reported monthly volumes converted to a daily average — not a measured rate.
          </div>
        )}
      </Card>

      <Card title={t("x_inputs_nopublic")} subtitle={t("x_never_gen")}>
        <div className="grid grid-cols-2 gap-2">
          {Object.keys(unavailable).map((key) => (
            <div key={key} className="glass-inner px-3 py-1.5 flex justify-between gap-2">
              <span className="subtle">{key.replace(/_/g, " ")}</span><span className="faint">—</span>
            </div>
          ))}
        </div>
        <div className="faint text-[11px] mt-2">
          SCADA value unavailable. Enter manually, or connect a SCADA/historian source. CORE does not
          substitute a generated number for a missing measurement.
        </div>
      </Card>

      <Card title={t("x_int_whatif")} subtitle={t("x_econ_engine")}>
        {!hasBaseline ? (
          <div className="subtle">
            No linked public production baseline, so no scenario can be evaluated. CORE will not invent one.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <label className="grid gap-1"><span className="faint text-[11px]">{t("x_intervention")}</span>
                <select value={form.intervention_type} onChange={(e) => setForm({ ...form, intervention_type: e.target.value })}>
                  {["cleanout", "pump_replacement", "pump_optimisation", "stimulation", "water_shutoff", "workover", "restart"].map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}
                </select>
              </label>
              <label className="grid gap-1"><span className="faint text-[11px]">{t("x_oil_uplift_frac")}</span>
                <input type="number" step="0.01" value={form.uplift_fraction} onChange={(e) => setForm({ ...form, uplift_fraction: Number(e.target.value) })} />
              </label>
              <label className="grid gap-1"><span className="faint text-[11px]">{t("x_success_prob")}</span>
                <input type="number" step="0.01" min="0" max="1" value={form.success_probability} onChange={(e) => setForm({ ...form, success_probability: Number(e.target.value) })} />
              </label>
              <label className="grid gap-1"><span className="faint text-[11px]">{t("x_horizon")}</span>
                <input type="number" min="1" max="60" value={form.horizon_months} onChange={(e) => setForm({ ...form, horizon_months: Number(e.target.value) })} />
              </label>
            </div>
            <button className="btn primary sm" onClick={submit} disabled={busy}>{busy ? "Running…" : "Run scenario"}</button>
            {err && <div className="mt-3"><ErrorBox error={err} /></div>}
            {run && (
              <div className="mt-3 grid gap-2">
                <div className="grid grid-cols-3 gap-2">
                  <Row label={t("x_baseline_oil")} value={`${fmt.n(run.baseline.oil_bpd, 1)} bbl/d`} note="from reported volumes" />
                  <Row label={t("x_incr_oil")} value={`${fmt.n(run.result.incremental_oil_bbl)} bbl`} note={`over ${run.scenario.horizon_months} months`} />
                  <Row label="Cost" value={fmt.money(run.scenario.cost)} note="illustrative assumption" />
                  <Row label={t("x_npv_risked")} value={fmt.money(run.result.npv)} />
                  <Row label={t("x_npv_success")} value={fmt.money(run.result.npv_if_success)} />
                  <Row label={t("x_payback")} value={run.result.payback_months == null ? "—" : `${run.result.payback_months} months`} />
                </div>
                <details className="glass-inner p-3">
                  <summary className="cursor-pointer text-[12px]">{t("x_how_calc2")}</summary>
                  <div className="mt-2 text-[11px] space-y-1">
                    <div><span className="faint">{t("x_formula2")} </span>{run.result.provenance.formula}</div>
                    <div><span className="faint">Netback </span>{run.result.provenance.netback.value} {run.result.provenance.netback.unit} — {run.result.provenance.netback.formula}</div>
                    <div><span className="faint">{t("x_water_unit")} </span>{run.result.provenance.water_unit_cost.value} {run.result.provenance.water_unit_cost.unit}</div>
                    {run.result.provenance.water_unit_cost.note && <div className="faint">{run.result.provenance.water_unit_cost.note}</div>}
                  </div>
                </details>
                <div className="glass-inner p-3 text-[11px] space-y-1">
                  <div className="font-semibold">{t("x_what_is")}</div>
                  {run.caveats.map((c: string, i: number) => <div key={i} className="faint">· {c}</div>)}
                </div>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
