"""M4 — Water economics: every produced barrel of water gets a cost; capacity limits get a shadow price."""
from __future__ import annotations

import numpy as np

from ..config import OPERATOR_DATA_REQUIRED, val
from . import economics, memory


def facility_load(ctx) -> dict:
    """Fluid throughput per facility over the last 3 months vs (illustrative) capacity."""
    n = ctx.ds.n_months
    p = ctx.ds.production
    recent = p[p.t >= n - 3]
    w = ctx.ds.wells[["well_id", "facility_id"]] if "facility_id" in ctx.ds.wells.columns else None
    out = {}
    if w is None or not len(ctx.ds.facilities):
        return out
    m = recent.merge(w, on="well_id", how="left")
    g = m.groupby("facility_id").agg(oil=("oil_bpd", "sum"), water=("water_bpd", "sum")).reset_index()
    g["oil"] = g.oil / 3.0
    g["water"] = g.water / 3.0
    fac = ctx.ds.facilities.set_index("facility_id")
    for r in g.itertuples():
        raw_cap = fac.loc[r.facility_id, "fluid_capacity_bpd"] if r.facility_id in fac.index else None
        try:
            cap = float(raw_cap) if raw_cap is not None and np.isfinite(float(raw_cap)) else None
        except (TypeError, ValueError):
            cap = None
        util = (r.oil + r.water) / cap if cap else None
        out[r.facility_id] = {"facility_id": r.facility_id, "oil_bpd": round(float(r.oil), 0), "water_bpd": round(float(r.water), 0), "fluid_capacity_bpd": cap, "utilisation": None if util is None else round(float(util), 3),
                              "handling": str(fac.loc[r.facility_id, "water_handling"]) if r.facility_id in fac.index else "disposal", "capacity_source": OPERATOR_DATA_REQUIRED + " (illustrative in demo)"}
    return out


def table(ctx, memory_rows: list[dict]) -> dict:
    s = ctx.settings
    n = ctx.ds.n_months
    loads = facility_load(ctx)
    wells = ctx.ds.wells.set_index("well_id")
    oil_p, wat_p, wc_p = ctx.ds.panel("oil_bpd"), ctx.ds.panel("water_bpd"), ctx.ds.panel("water_cut")
    ws_ev = memory.type_evidence(memory_rows, "water_shutoff")
    rows = []
    unit_costs = {}
    for wid, st in ctx.status.iterrows():
        if st.status != "producing":
            continue
        oil = float(np.nanmean(oil_p[wid].to_numpy(dtype=float)[n - 3:]))
        wat = float(np.nanmean(wat_p[wid].to_numpy(dtype=float)[n - 3:]))
        wc = float(np.nanmean(wc_p[wid].to_numpy(dtype=float)[n - 3:]))
        if not np.isfinite(wat):
            continue
        fac_id = str(wells.loc[wid, "facility_id"]) if "facility_id" in wells.columns else None
        fl = loads.get(fac_id, {})
        handling = fl.get("handling", "disposal")
        if handling not in unit_costs:
            unit_costs[handling] = economics.water_unit_cost(s, handling)
        visible = unit_costs[handling]["value"]
        util = fl.get("utilisation")
        shadow = economics.shadow_cost(s, util if util is not None else 0.0, oil_fraction_marginal=max(0.0, 1 - wc)) if util is not None else {"value": 0.0, "active": False}
        total = visible + shadow["value"]
        cost_day = wat * total
        constraint = "constrained" if shadow.get("active") else "near limit" if (util or 0) >= 0.75 else "ok"
        intervention, water_avoided, value = None, None, None
        if wc >= 0.85 and ws_ev.get("n", 0) >= 3:
            intervention = "water_shutoff"
            water_avoided = max(0.0, -ws_ev["median_water_change_bpd"]) if ws_ev.get("median_water_change_bpd") is not None else None
            oil_eff = oil * ws_ev["median_effect_ratio"]
            horizon = int(val(s["economics"]["horizon_months"]))
            econ = economics.evaluate(s, economics.decay_profile(oil_eff, horizon), [-(water_avoided or 0.0)] * horizon, val(economics.intervention_cost(s, "water_shutoff")), handling=handling, success_probability=ws_ev["positive_effect_rate"], label="water_shutoff")
            value = econ["npv"]
        rows.append({"well_id": wid, "field": str(wells.loc[wid, "field"]), "oil_bpd": round(oil, 1), "water_bpd": round(wat, 1), "water_cut": round(wc, 3), "facility": fac_id, "handling": handling,
                     "visible_cost_per_bbl": round(visible, 3), "shadow_cost_per_bbl": round(shadow["value"], 3), "total_cost_per_bbl": round(total, 3), "water_cost_per_day": round(cost_day, 0), "water_cost_per_year": round(cost_day * 365, 0),
                     "utilisation": util, "constraint_status": constraint, "potential_intervention": intervention, "water_avoided_bpd": None if water_avoided is None else round(water_avoided, 1), "expected_value": value})
    rows.sort(key=lambda r: -r["water_cost_per_year"])
    tot_cost = sum(r["water_cost_per_day"] for r in rows)
    tot_visible = sum(r["water_bpd"] * r["visible_cost_per_bbl"] for r in rows)
    return {"rows": rows, "facilities": list(loads.values()), "unit_costs": unit_costs,
            "kpi": {"produced_water_bpd": round(sum(r["water_bpd"] for r in rows), 0), "visible_cost_per_day": round(tot_visible, 0), "hidden_capacity_cost_per_day": round(tot_cost - tot_visible, 0), "total_cost_per_day": round(tot_cost, 0),
                    "total_cost_per_year": round(tot_cost * 365, 0), "shutoff_candidates": sum(1 for r in rows if r["potential_intervention"])},
            "mode": "PUBLIC DATA MODE", "note": "Production and water volumes come from the loaded dataset. Cost and capacity components are illustrative assumptions because operator economics are not published."}


def trajectory(ctx) -> list[dict]:
    p = ctx.ds.production
    g = p.groupby("t").agg(oil=("oil_bpd", "sum"), water=("water_bpd", "sum")).reset_index()
    return [{"t": int(r.t), "month": ctx.ds.months[int(r.t)], "oil_bpd": round(float(r.oil), 0), "water_bpd": round(float(r.water), 0), "water_cut": round(float(r.water / max(r.oil + r.water, 1e-6)), 3)} for r in g.itertuples()]


def shutoff_scenario(ctx, well_id: str, water_reduction_bpd: float, oil_effect_bpd: float, cost: float, success_probability: float, duration_months: int) -> dict:
    s = ctx.settings
    handling = memory._handling(ctx, well_id)
    econ = economics.evaluate(s, economics.decay_profile(oil_effect_bpd, duration_months), [-water_reduction_bpd] * duration_months, cost, handling=handling, success_probability=success_probability, label="water_shutoff")
    lo = economics.evaluate(s, economics.decay_profile(oil_effect_bpd * 0.6, duration_months), [-water_reduction_bpd * 0.6] * duration_months, cost, handling=handling, success_probability=success_probability)
    hi = economics.evaluate(s, economics.decay_profile(oil_effect_bpd * 1.3, duration_months), [-water_reduction_bpd * 1.2] * duration_months, cost, handling=handling, success_probability=success_probability)
    return {"expected_net_value": econ["npv"], "npv": econ["npv"], "payback_months": econ["payback_months"], "range": [lo["npv"], hi["npv"]], "economics": econ}
