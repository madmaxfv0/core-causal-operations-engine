/**
 * Provenance registry.
 *
 * One place that answers, for every important metric: what kind of number it is,
 * which dataset it came from, the exact formula, the period it covers and its
 * limitations. The `Provenance` "i" icon renders whatever this returns, so a metric
 * is documented by adding one entry here — not by hand-writing a tooltip per KPI.
 *
 * `kind` uses the same vocabulary as the backend (backend/data/context.py):
 *   reported · derived · model estimate · illustrative assumption · synthetic · not available
 */
import { useT } from "./i18n";
import { Any, useDataSource } from "./api";

type Entry = {
  kind: string;
  formulaKey?: string;      // i18n key describing the calculation in words
  formula?: string;         // literal formula, language-neutral
  unit?: string;
  windowKey?: string;       // i18n key describing the time window
  limitKeys?: string[];     // i18n keys for limitations
  sourceKind?: "dataset" | "alberta" | "assumption" | "model" | "none";
};

/**
 * Formulas are written the way an engineer would check them by hand. They are
 * deliberately literal: if the UI shows a number you cannot reproduce from this
 * line plus the inputs, that is a bug.
 */
export const REGISTRY: Record<string, Entry> = {
  // ---- field production
  ov_oil:            { kind: "derived", formula: "Σ(monthly oil volume ÷ days in month) over producing wells", unit: "bbl/d", windowKey: "p_w_latest", sourceKind: "dataset", limitKeys: ["p_l_monthly"] },
  ov_water:          { kind: "derived", formula: "Σ(monthly water volume ÷ days in month)", unit: "bbl/d", windowKey: "p_w_latest", sourceKind: "dataset", limitKeys: ["p_l_monthly"] },
  ov_idle:           { kind: "derived", formula: "COUNT(wells with oil rate ≤ zero-threshold for ≥ N consecutive months)", windowKey: "p_w_latest", sourceKind: "dataset", limitKeys: ["p_l_ruleset"] },
  ov_screened:       { kind: "derived", formula: "COUNT(wells with enough history to evaluate)", sourceKind: "dataset" },
  ov_underperf:      { kind: "model estimate", formula: "COUNT(wells producing below their estimated no-intervention baseline)", sourceKind: "model", limitKeys: ["p_l_counterfactual"] },
  ov_candidates:     { kind: "model estimate", formula: "COUNT(wells passing the screening funnel with positive expected value)", sourceKind: "model", limitKeys: ["p_l_counterfactual"] },
  ov_recoverable:    { kind: "model estimate", formula: "Σ(actual − estimated counterfactual) over candidate wells", unit: "bbl/d", sourceKind: "model", limitKeys: ["p_l_counterfactual", "p_l_range"] },
  ov_avoidable_water:{ kind: "model estimate", formula: "Σ(estimated water reduction from modelled water-shutoff candidates)", unit: "bbl/d", sourceKind: "model", limitKeys: ["p_l_counterfactual"] },
  ov_capital:        { kind: "illustrative assumption", formula: "Σ(assumed intervention cost of selected candidates)", sourceKind: "assumption", limitKeys: ["p_l_costs"] },
  ov_npv:            { kind: "model estimate", formula: "−cost + p(success) × Σₜ (oilₜ × netback − Δwaterₜ × water cost) ÷ (1+r)ᵗ", sourceKind: "model", limitKeys: ["p_l_costs", "p_l_range"] },

  // ---- water economics
  visible_cost:      { kind: "derived", formula: "water bbl/day × Σ(assumed cost components $/bbl)", unit: "$/day", sourceKind: "assumption", limitKeys: ["p_l_costs"] },
  total_cost:        { kind: "derived", formula: "(visible water cost + capacity shadow cost) × 365", unit: "$/yr", sourceKind: "assumption", limitKeys: ["p_l_costs", "p_l_capacity"] },
  shutoff:           { kind: "derived", formula: "COUNT(wells with water cut ≥ 85% and ≥ 3 comparable historical jobs)", sourceKind: "dataset" },
  water_cut:         { kind: "derived", formula: "water ÷ (oil + water) × 100", unit: "%", windowKey: "p_w_latest", sourceKind: "dataset", limitKeys: ["p_l_undefined"] },
  water_cost:        { kind: "derived", formula: "water bbl/day × assumed $/bbl", unit: "$/day", sourceKind: "assumption", limitKeys: ["p_l_costs"] },

  // ---- ghost barrels
  ghost_kpi:         { kind: "model estimate", formula: "Σ(estimated counterfactual − actual) for producing wells below baseline", unit: "bbl/d", sourceKind: "model", limitKeys: ["p_l_counterfactual", "p_l_range"] },
  annual_value:      { kind: "model estimate", formula: "recoverable bbl/d × 365 × netback", unit: "$/yr", sourceKind: "assumption", limitKeys: ["p_l_costs"] },

  // ---- intervention memory
  mem_jobs:          { kind: "derived", formula: "COUNT(recorded interventions + detected restarts analysed)", sourceKind: "dataset", limitKeys: ["p_l_interventions"] },
  mem_spend:         { kind: "illustrative assumption", formula: "Σ(recorded cost, or assumed cost where none was recorded)", sourceKind: "assumption", limitKeys: ["p_l_costs"] },
  mem_created:       { kind: "model estimate", formula: "Σ(NPV of jobs with positive causal effect)", sourceKind: "model", limitKeys: ["p_l_counterfactual"] },
  mem_destroyed:     { kind: "model estimate", formula: "Σ(NPV of jobs with negative causal effect)", sourceKind: "model", limitKeys: ["p_l_counterfactual"] },
  mem_naive:         { kind: "derived", formula: "mean(post-period rate) − mean(pre-period rate)", unit: "bbl/d", sourceKind: "dataset", limitKeys: ["p_l_naive"] },
  mem_causal:        { kind: "model estimate", formula: "mean(actual − estimated counterfactual) over the post window", unit: "bbl/d", sourceKind: "model", limitKeys: ["p_l_counterfactual", "p_l_range"] },
  mem_anyway:        { kind: "model estimate", formula: "COUNT(jobs where causal effect ≤ 25% of the naive before/after claim)", sourceKind: "model", limitKeys: ["p_l_counterfactual"] },

  // ---- portfolio
  expected_value:    { kind: "model estimate", formula: "Σ(probability-adjusted NPV of selected jobs)", sourceKind: "model", limitKeys: ["p_l_costs", "p_l_range"] },
  oil_uplift:        { kind: "model estimate", formula: "Σ(expected incremental oil of selected jobs)", unit: "bbl/d", sourceKind: "model", limitKeys: ["p_l_counterfactual"] },
  avoided:           { kind: "model estimate", formula: "Σ(assumed cost of candidates the optimiser rejected as negative-value)", sourceKind: "model", limitKeys: ["p_l_costs"] },

  // ---- well detail
  current_oil:       { kind: "derived", formula: "latest reported monthly oil volume ÷ days in that month", unit: "bbl/d", windowKey: "p_w_latest", sourceKind: "dataset", limitKeys: ["p_l_monthly"] },
  expected_baseline: { kind: "model estimate", formula: "estimated production had no intervention occurred (synthetic control / matched wells / decline curve)", unit: "bbl/d", sourceKind: "model", limitKeys: ["p_l_counterfactual", "p_l_range"] },
  gap:               { kind: "model estimate", formula: "estimated baseline − actual rate", unit: "bbl/d", sourceKind: "model", limitKeys: ["p_l_counterfactual"] },

  // ---- validation / model lab
  mae:               { kind: "derived", formula: "mean(|estimated effect − planted true effect|) across validation events", unit: "bbl/d", sourceKind: "dataset", limitKeys: ["p_l_synthetic_only"] },
  bias:              { kind: "derived", formula: "mean(estimated effect − planted true effect)", unit: "bbl/d", sourceKind: "dataset", limitKeys: ["p_l_synthetic_only"] },
  coverage:          { kind: "derived", formula: "share of planted true effects falling inside the 80% interval", sourceKind: "dataset", limitKeys: ["p_l_synthetic_only"] },
  spearman:          { kind: "derived", formula: "Spearman rank correlation between estimated and true effect ordering", sourceKind: "dataset", limitKeys: ["p_l_synthetic_only"] },

  // ---- Alberta map
  map_wells:         { kind: "reported", formula: "COUNT(AER ST37 records with valid Alberta coordinates)", sourceKind: "alberta" },
  map_active:        { kind: "derived", formula: "COUNT(records whose AER well category is not Abandoned/Suspended/Drilled-and-cased)", sourceKind: "alberta", limitKeys: ["p_l_derived_status"] },
  map_abandoned:     { kind: "derived", formula: "COUNT(records whose AER well category contains 'Abandoned')", sourceKind: "alberta", limitKeys: ["p_l_derived_status"] },
  map_linked:        { kind: "derived", formula: "COUNT(ST37 records uniquely matched to one reporting Petrinex well by legal location)", sourceKind: "alberta", limitKeys: ["p_l_unique_join"] },
  map_operators:     { kind: "reported", formula: "COUNT(DISTINCT Petrinex reporting operator)", sourceKind: "alberta" },
  map_scada:         { kind: "not available", formula: "—", sourceKind: "none", limitKeys: ["p_l_no_scada"] },

  // ---- data quality
  dq_wells:          { kind: "derived", formula: "COUNT(wells assessed for data quality)", sourceKind: "dataset" },
  dq_poor:           { kind: "derived", formula: "COUNT(wells failing completeness/consistency checks)", sourceKind: "dataset", limitKeys: ["p_l_ruleset"] },
};

/** Hook returning `prov(id)` — a translated provenance object for the "i" icon. */
export function useProv() {
  const { t } = useT();
  const source = useDataSource();
  return (id: string, extra?: Any): Any => {
    const e = REGISTRY[id];
    if (!e) return extra || null;
    const src =
      e.sourceKind === "alberta" ? source.alberta
      : e.sourceKind === "dataset" ? source.dataset
      : e.sourceKind === "assumption" ? t("p_src_assumption")
      : e.sourceKind === "model" ? t("p_src_model")
      : e.sourceKind === "none" ? t("p_src_none")
      : undefined;
    const out: Any = {
      [t("p_kind")]: t(`p_k_${e.kind.replace(/[^a-z]/g, "_")}` as Any),
      [t("p_source")]: src,
      [t("p_formula")]: e.formula || (e.formulaKey ? t(e.formulaKey as Any) : undefined),
    };
    if (e.unit) out[t("p_unit")] = e.unit;
    if (e.windowKey) out[t("p_window")] = t(e.windowKey as Any);
    if (e.limitKeys?.length) out[t("p_limits")] = e.limitKeys.map((k) => t(k as Any)).join(" · ");
    if (extra) Object.assign(out, extra);
    return out;
  };
}
