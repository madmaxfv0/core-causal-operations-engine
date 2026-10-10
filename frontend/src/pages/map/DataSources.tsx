/**
 * Dataset installer / refresher.
 *
 * Each official source can be installed and re-installed from here.  A refresh
 * that fails leaves the previously validated cache in place — the map keeps
 * working and the failure is reported instead of being papered over.
 */
import React, { useState } from "react";
import { Badge, Card, Progress, useToast } from "../../components/ui";
import { Any, api, fmt } from "../../lib/api";
import { useT } from "../../lib/i18n";

const MONTH_CHOICES = [3, 6, 12, 24, 36];

export function DataSources({ status, onDone }: { status: Any; onDone: () => void }) {
  const { t } = useT();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [steps, setSteps] = useState<string[]>([]);
  const [months, setMonths] = useState(12);
  const sources: Any[] = status?.sources || [];
  const petrinex = status?.petrinex;

  const run = async (kind: string, body?: Any) => {
    setBusy(kind); setSteps([]);
    try {
      const { job_id } = await api.post(`/api/alberta/sync/${kind}`, body || {});
      await api.job(job_id, setSteps);
      toast(`${kind} updated from the official source`);
      onDone();
    } catch (e: Any) {
      toast(`${kind}: ${e.message}`, "err");
    } finally {
      setBusy(null); setSteps([]);
    }
  };

  return (
    <div className="grid gap-3">
      <Card
        title={t("m_ds_title")}
        subtitle={t("x_install_note")}
      >
        <div className="grid gap-2">
          {sources.map((s: Any) => (
            <div key={s.kind} className="glass-inner p-3 flex flex-wrap items-center gap-3">
              <div className="min-w-[240px] flex-1">
                <div className="font-medium flex items-center gap-2">
                  {s.name}
                  <Badge label={s.connected ? "INSTALLED" : "NOT INSTALLED"} color={s.connected ? "green" : "grey"} small />
                </div>
                <div className="faint text-[11px]">{s.provides}</div>
                {s.meta && (
                  <div className="faint text-[11px]">
                    {fmt.n(s.meta.stats?.rows || s.rows)} rows · retrieved {fmt.date(s.meta.retrieved_at)}
                    {s.meta.source_last_edit ? ` · source last edited ${fmt.date(s.meta.source_last_edit)}` : ""}
                  </div>
                )}
                {s.note && <div className="faint text-[11px] mt-0.5">{s.note}</div>}
              </div>
              {s.refreshable ? (
                <div className="flex flex-col items-end gap-1">
                  <button className="btn sm" disabled={!!busy} onClick={() => run(s.kind)}>
                    {s.connected ? "Refresh" : "Install"}
                  </button>
                  {["casing_failures", "vent_flow"].includes(s.kind) && (
                    <div className="faint text-[10px] max-w-[220px] text-right">
                      Some networks block AER's report host. If Install fails, download the CSV from{" "}
                      <a href={s.landing_page} target="_blank" rel="noreferrer" className="underline">{t("x_aer_gwd")}</a>{" "}
                      and run <code>--file {s.kind}=path.csv</code>.
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-[11px] faint max-w-[260px]">
                  AER distributes this as a file. Download it from{" "}
                  <a href={s.landing_page} target="_blank" rel="noreferrer" className="underline">the AER catalogue</a>{" "}
                  then run <code>python scripts/update_alberta_data.py --file {s.kind}=/path/to/file.csv</code>
                </div>
              )}
            </div>
          ))}

          <div className="glass-inner p-3 flex flex-wrap items-center gap-3">
            <div className="min-w-[240px] flex-1">
              <div className="font-medium flex items-center gap-2">
                Petrinex — Alberta Conventional Volumetrics
                <Badge label={petrinex ? "INSTALLED" : "NOT INSTALLED"} color={petrinex ? "green" : "grey"} small />
              </div>
              <div className="faint text-[11px]">{t("x_rep_month_vol")}</div>
              {petrinex && (
                <div className="faint text-[11px]">
                  {fmt.n(petrinex.records)} monthly records · {fmt.n(petrinex.wells)} wells ·
                  {" "}{petrinex.months?.[0]} → {petrinex.latest_month} · retrieved {fmt.date(petrinex.retrieved_at)}
                </div>
              )}
            </div>
            <select value={months} onChange={(e) => setMonths(Number(e.target.value))} aria-label={t("m_ds_months")}>
              {MONTH_CHOICES.map((m) => <option key={m} value={m}>{m} months</option>)}
            </select>
            <button className="btn sm" disabled={!!busy} onClick={() => run("petrinex", { months })}>
              {petrinex ? "Refresh" : "Install"}
            </button>
          </div>
        </div>
        {busy && <div className="mt-3"><Progress steps={steps.length ? steps : ["contacting the official source"]} label={`Updating ${busy}`} /></div>}
        <div className="faint text-[11px] mt-3">
          Downloads are retried with backoff and written atomically. If a source is unreachable or its schema
          has changed, the import aborts and the previously validated cache stays active.
        </div>
      </Card>

      {status?.join?.available && (
        <Card title={t("m_join_title")} subtitle={t("x_join_note")}>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-[12px]">
            {[
              ["ST37 wells imported", status.join.st37_wells_imported],
              ["Legal locations parsed", status.join.st37_with_parsed_legal_location],
              ["Distinct legal cells", status.join.st37_distinct_legal_cells],
              ["Petrinex reporting wells", status.join.petrinex_reporting_wells],
              ["Production records", status.join.petrinex_production_records],
              ["Wells linked to production", status.join.st37_wells_linked],
              ["Wells with no production link", status.join.st37_wells_unlinked],
              ["Ambiguous cells excluded", status.join.ambiguous_cells_excluded],
              ["Petrinex cells with no ST37 match", status.join.petrinex_cells_without_st37_match],
            ].map(([label, value]: Any) => (
              <div key={label} className="glass-inner px-3 py-2 flex justify-between gap-2">
                <span className="faint">{label}</span><span className="font-medium">{fmt.n(value)}</span>
              </div>
            ))}
          </div>
          <div className="faint text-[11px] mt-2">{status.join.join_key}</div>
          <div className="faint text-[11px]">{status.join.ambiguity_rule}</div>
        </Card>
      )}
    </div>
  );
}
