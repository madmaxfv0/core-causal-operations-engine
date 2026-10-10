/**
 * First-run onboarding guide.
 *
 * Explains, visually, what CORE does, where every number comes from, and what is
 * deliberately NOT connected. Built from the same glass/chip/badge vocabulary as the
 * rest of the app — no new design system — and driven by the live data context so the
 * numbers it quotes are the real ones, never illustrations.
 */
import React from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Card, Icon, Kpi, useFetch } from "../components/ui";
import { HoverCard } from "../components/overlay";
import { Any, fmt, ls } from "../lib/api";
import { useT } from "../lib/i18n";

const GUIDE_SEEN = "core.guide.seen";
export const markGuideSeen = () => ls.set(GUIDE_SEEN, "1");
export const guideSeen = () => !!ls.get(GUIDE_SEEN, "");

function Step({ n, icon, title, body, action }: Any) {
  return (
    <div className="glass-inner p-4 flex gap-3 items-start">
      <div className="shrink-0 flex flex-col items-center gap-1">
        <span className="rail-btn active" style={{ width: 36, height: 36 }}><Icon name={icon} size={17} /></span>
        <span className="faint text-[10px]">{n}</span>
      </div>
      <div className="min-w-0">
        <div className="font-semibold text-[14px] mb-0.5">{title}</div>
        <div className="subtle text-[12px] leading-snug">{body}</div>
        {action}
      </div>
    </div>
  );
}

function Flow({ t }: { t: (k: any) => string }) {
  // Source → normalise → calculate → explain. Drawn inline so it scales with the theme.
  const stages: [string, string, string][] = [
    [t("g_flow_source"), t("g_flow_source_d"), "#5CC489"],
    [t("g_flow_validate"), t("g_flow_validate_d"), "#4F6BE8"],
    [t("g_flow_calc"), t("g_flow_calc_d"), "#F2B632"],
    [t("g_flow_explain"), t("g_flow_explain_d"), "#B7C4FF"],
  ];
  return (
    <div className="grid gap-2 md:grid-cols-4">
      {stages.map(([label, desc, colour], i) => (
        <div key={label} className="glass-inner p-3 relative">
          <div className="flex items-center gap-2 mb-1">
            <span style={{ width: 9, height: 9, borderRadius: 999, background: colour, display: "inline-block" }} />
            <b className="text-[13px]">{label}</b>
          </div>
          <div className="faint text-[11px] leading-snug">{desc}</div>
          {i < stages.length - 1 && (
            <span className="faint hidden md:block" style={{ position: "absolute", right: -13, top: "50%", transform: "translateY(-50%)" }}>→</span>
          )}
        </div>
      ))}
    </div>
  );
}

export function Guide() {
  const { t } = useT();
  const nav = useNavigate();
  const { data } = useFetch<Any>("/api/data/context");
  const { data: mapSummary } = useFetch<Any>("/api/map/summary");
  const ds = data?.dataset;
  const ab = data?.alberta_public?.domains;
  const s = mapSummary?.summary;

  React.useEffect(() => { markGuideSeen(); }, []);

  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 style={{ fontSize: 28 }}>{t("g_title")}</h1>
        <Badge label={t("g_badge")} color="blue" />
        <span className="flex-1" />
        <button className="btn sm primary" onClick={() => nav("/map")}>{t("g_open_map")}</button>
        <button className="btn sm" onClick={() => nav("/")}>{t("g_open_overview")}</button>
      </div>
      <div className="subtle text-[13px] -mt-1">{t("g_sub")}</div>

      {/* live proof, not illustrations */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi small label={t("g_kpi_wells")} value={fmt.n(s?.wells_loaded)} sub={ab?.wells?.source}
             provenance={{ source: ab?.wells?.source, kind: "reported", retrieved_at: ab?.wells?.retrieved_at,
                           formula: "COUNT(imported AER ST37 records with valid Alberta coordinates)" }} />
        <Kpi small label={t("g_kpi_prod")} value={fmt.n(ab?.production?.rows)} sub={ab?.production?.period}
             provenance={{ source: ab?.production?.source, kind: "reported",
                           limitations: ab?.production?.limitations,
                           formula: "COUNT(Petrinex monthly volumetric rows imported)" }} />
        <Kpi small label={t("g_kpi_linked")} value={fmt.n(s?.matched_to_production)} sub={t("g_kpi_linked_sub")}
             provenance={{ kind: "derived", formula: "ST37 record ↔ Petrinex well, joined on Alberta Township System legal location, unique in both directions" }} />
        <Kpi small label={t("g_kpi_scada")} value="—" sub={t("g_kpi_scada_sub")}
             badge={<Badge label={t("g_not_connected")} color="grey" small />} />
      </div>

      <Card title={t("g_how_title")} subtitle={t("g_how_sub")}>
        <Flow t={t} />
      </Card>

      <div className="grid lg:grid-cols-2 gap-3">
        <Card title={t("g_start_title")} subtitle={t("g_start_sub")}>
          <div className="grid gap-2">
            <Step n="1" icon="map" title={t("g_s1")} body={t("g_s1_d")}
                  action={<button className="btn sm mt-2" onClick={() => nav("/map")}>{t("g_open_map")}</button>} />
            <Step n="2" icon="data" title={t("g_s2")} body={t("g_s2_d")}
                  action={<button className="btn sm mt-2" onClick={() => nav("/data")}>{t("nav_datahub")}</button>} />
            <Step n="3" icon="grid" title={t("g_s3")} body={t("g_s3_d")}
                  action={<button className="btn sm mt-2" onClick={() => nav("/")}>{t("nav_overview")}</button>} />
            <Step n="4" icon="why" title={t("g_s4")} body={t("g_s4_d")} />
          </div>
        </Card>

        <div className="grid gap-3 content-start">
          <Card title={t("g_trust_title")} subtitle={t("g_trust_sub")}>
            <div className="grid gap-1.5 text-[12px]">
              {[
                ["reported", t("g_k_reported"), "green"],
                ["derived", t("g_k_derived"), "blue"],
                ["model estimate", t("g_k_model"), "amber"],
                ["illustrative assumption", t("g_k_assumption"), "amber"],
                ["synthetic", t("g_k_synthetic"), "grey"],
                ["not available", t("g_k_missing"), "grey"],
              ].map(([label, desc, colour]: Any) => (
                <div key={label} className="flex items-start gap-2">
                  <Badge label={String(label).toUpperCase()} color={colour} small />
                  <span className="subtle flex-1">{desc}</span>
                </div>
              ))}
            </div>
            <div className="faint text-[11px] mt-3">
              <HoverCard side="top" width={340} content={<div>{t("g_i_explain")}</div>}>
                <span className="underline decoration-dotted underline-offset-4 cursor-pointer">{t("g_i_hint")}</span>
              </HoverCard>
            </div>
          </Card>

          <Card title={t("g_not_title")} subtitle={t("g_not_sub")}>
            <div className="grid gap-1.5 text-[12px]">
              {[t("g_not_scada"), t("g_not_interventions"), t("g_not_costs"), t("g_not_operator")].map((line) => (
                <div key={line} className="flex gap-2"><span className="faint">—</span><span className="subtle">{line}</span></div>
              ))}
            </div>
            <div className="glass-inner p-2 mt-2 text-[11px]" style={{ color: "#FFD97A" }}>
              {data?.scada?.statement}
            </div>
          </Card>
        </div>
      </div>

      <Card title={t("g_ctx_title")} subtitle={t("g_ctx_sub")}>
        <div className="grid md:grid-cols-2 gap-3 text-[12px]">
          <div className="glass-inner p-3">
            <div className="font-semibold mb-1 flex items-center gap-2">
              {t("g_ctx_analytical")} <Badge label={ds?.is_synthetic ? "SYNTHETIC" : "REAL"} color={ds?.is_synthetic ? "amber" : "blue"} small />
            </div>
            <div className="faint mb-2">{t("g_ctx_analytical_d")}</div>
            <div className="subtle">{ds?.label}</div>
          </div>
          <div className="glass-inner p-3">
            <div className="font-semibold mb-1 flex items-center gap-2">{t("g_ctx_public")} <Badge label={t("x_public")} color="blue" small /></div>
            <div className="faint mb-2">{t("g_ctx_public_d")}</div>
            <div className="subtle">{[ab?.wells?.source, ab?.production?.source].filter(Boolean).join(" · ")}</div>
          </div>
        </div>
      </Card>
    </div>
  );
}
