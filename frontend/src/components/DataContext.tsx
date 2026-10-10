/**
 * Global data-context selector and provenance banner.
 *
 * Replaces a passive "data mode" label with a control that states, truthfully and
 * per domain, what CORE is analysing and where each domain's numbers come from —
 * and lets the analytical data set be switched from anywhere in the app.
 *
 * It deliberately does NOT imply that one data set supplies fields that actually
 * come from another: the analytical data set and the Alberta public map caches are
 * listed as the two separate planes they really are.
 */
import React, { useState } from "react";
import { Badge, Icon, useFetch, useToast } from "./ui";
import { Dropdown } from "./overlay";
import { Any, api, fmt } from "../lib/api";
import { useT } from "../lib/i18n";

const STATUS_COLOR: Record<string, string> = {
  Available: "green",
  "Not available": "grey",
  "Not applicable": "grey",
  "Not mapped": "amber",
  "Operator data required": "amber",
  "Adapter not implemented": "amber",
};

function DomainRow({ name, d }: { name: string; d: Any }) {
  if (!d) return null;
  return (
    <div className="flex items-start justify-between gap-3 py-1">
      <span className="faint capitalize min-w-[92px]">{name.replace(/_/g, " ")}</span>
      <span className="flex-1 text-right">
        <span className="block">{d.source || <span className="faint">—</span>}</span>
        {d.rows ? <span className="faint text-[10px]">{fmt.n(d.rows)} rows</span> : null}
        {d.period ? <span className="faint text-[10px]"> · {d.period}</span> : null}
        {d.note ? <span className="block faint text-[10px] leading-tight">{d.note}</span> : null}
      </span>
      <Badge label={d.status} color={STATUS_COLOR[d.status] || "grey"} small />
    </div>
  );
}

export function DataContextChip({ onChanged }: { onChanged?: () => void }) {
  const { t } = useT();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const anchor = React.useRef<HTMLButtonElement>(null);
  const { data, reload } = useFetch<Any>("/api/data/context");
  const ds = data?.dataset;
  const synthetic = !!ds?.is_synthetic;

  const activate = async (name: string) => {
    setBusy(true);
    try {
      await api.post(`/api/data/activate/${name}`);
      toast(t("ctx_switched"));
      reload(); onChanged?.();
      window.location.reload();
    } catch (e: Any) {
      toast(e.message, "err");
    } finally { setBusy(false); }
  };

  return (
    <>
      <button
        ref={anchor}
        className={`chip ${synthetic ? "amber" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={t("ctx_title")}
      >
        <Icon name="data" size={14} />
        <span className="font-semibold">{ds ? (synthetic ? t("data_mode_synthetic") : ds.data_mode || t("data_mode_real")) : "…"}</span>
        <Icon name="chev" size={12} />
      </button>

      <Dropdown open={open} onClose={() => setOpen(false)} anchorRef={anchor} width={430} align="start">
        <div className="text-[12px] p-1">
          <div className="faint text-[10px] uppercase tracking-wide mb-1">{t("ctx_title")}</div>

          <div className="glass-inner p-2 mb-2">
            <div className="flex items-center justify-between gap-2 mb-1">
              <b>{ds?.label || "—"}</b>
              <Badge label={synthetic ? "SYNTHETIC" : "REAL"} color={synthetic ? "amber" : "blue"} small />
            </div>
            {ds?.date_range && <div className="faint text-[10px]">{ds.date_range[0]} → {ds.date_range[1]}</div>}
            {!ds?.usable && ds?.reason && <div className="text-[11px] mt-1" style={{ color: "#FFB3A8" }}>{ds.reason}</div>}
            <div className="mt-1">{Object.entries(ds?.domains || {}).map(([k, v]: Any) => <DomainRow key={k} name={k} d={v} />)}</div>
          </div>

          <div className="faint text-[10px] uppercase tracking-wide mb-1">{t("ctx_switch")}</div>
          <div className="faint text-[11px] mb-2">Choose the analytical workspace. Synthetic is for demonstrations and method validation; Alberta is public reported data with model estimates clearly identified.</div>
          <div className="flex flex-wrap gap-1 mb-2">
            {(data?.available_datasets || []).map((d: Any) => (
              <button
                key={d.name}
                className={`chip ${d.name === ds?.name ? "amber" : ""}`}
                style={{ fontSize: 11, padding: "3px 9px" }}
                disabled={busy || !d.usable || d.name === ds?.name}
                title={d.usable ? d.label : d.name}
                onClick={() => activate(d.name)}
              >
                {d.name === "synthetic" ? "SYNTHETIC DEMO" : "REAL ALBERTA DATA"}{!d.usable && " ⚠"}
              </button>
            ))}
          </div>

          <div className="glass-inner p-2">
            <div className="flex items-center justify-between mb-1">
              <b>{data?.alberta_public?.label}</b>
              <Badge label={t("x_public")} color="blue" small />
            </div>
            <div className="faint text-[10px] mb-1">{data?.alberta_public?.note}</div>
            {Object.entries(data?.alberta_public?.domains || {}).map(([k, v]: Any) => <DomainRow key={k} name={k} d={v} />)}
          </div>

          <div className="faint text-[10px] mt-2">{data?.scada?.statement}</div>
        </div>
      </Dropdown>
    </>
  );
}
