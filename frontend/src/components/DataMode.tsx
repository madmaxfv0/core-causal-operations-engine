/**
 * Data mode selector: SYNTHETIC (the existing demo, default) or REAL (public data).
 *
 * Switching is a full page reload on purpose. Every page holds fetched state, and the
 * requirement is that no value from one mode can survive into the other — a reload is
 * the cheapest guarantee of that, and mode changes are rare.
 */
import React, { useState } from "react";
import { Badge, Icon, useFetch, useToast } from "./ui";
import { Tip } from "./overlay";
import { Any, api, fmt } from "../lib/api";
import { useT } from "../lib/i18n";

export function DataModeSwitch() {
  const { t } = useT();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const { data, reload } = useFetch<Any>("/api/data/mode");
  const mode = data?.mode || "SYNTHETIC";
  const real = mode === "REAL";

  const choose = async (next: string) => {
    if (next === mode || busy) return;
    setBusy(true);
    try {
      const r = await api.post("/api/data/mode", { mode: next });
      if (r.ready === false && r.needs_import) {
        toast(r.needs_import, "err");
        reload(); setBusy(false); return;
      }
      window.location.reload();
    } catch (e: Any) {
      toast(e.message, "err"); setBusy(false); reload();
    }
  };

  const detail = (
    <div className="text-[12px] space-y-1" style={{ maxWidth: 300 }}>
      <div className="font-semibold">{data?.source_line}</div>
      {data?.reporting_date && <div className="faint">{t("dm_reporting")}: {data.reporting_date}</div>}
      {data?.st37_retrieved && <div className="faint">AER ST37: {fmt.date(data.st37_retrieved)}</div>}
      <div className={real ? "faint" : ""} style={real ? undefined : { color: "#FFD97A" }}>
        {real ? t("dm_scada_off") : t("dm_scada_sim")}
      </div>
      {data?.needs_import && <div style={{ color: "#FFB3A8" }}>{data.needs_import}</div>}
    </div>
  );

  return (
    <Tip label={detail} side="bottom">
      <span className="chip" style={{ gap: 6, paddingLeft: 10, paddingRight: 6 }}>
        <Icon name={real ? "data" : "sparkle"} size={14} />
        <span className="faint hidden lg:inline">{t("dm_label")}</span>
        <span className="flex items-center gap-1">
          {[["SYNTHETIC", t("dm_synthetic")], ["REAL", t("dm_real")]].map(([value, label]) => (
            <button
              key={value}
              className={`badge ${mode === value ? (value === "REAL" ? "blue" : "amber") : "grey"}`}
              style={{ cursor: busy ? "wait" : "pointer", border: "none", fontSize: 10 }}
              disabled={busy}
              aria-pressed={mode === value}
              onClick={() => choose(value)}
            >
              {label}
            </button>
          ))}
        </span>
        {data?.ready === false && <Badge label="!" color="red" small />}
      </span>
    </Tip>
  );
}
