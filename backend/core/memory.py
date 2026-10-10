"""M1 — Intervention memory: what the operator's own past jobs actually changed."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import val
from . import economics, engine


def analyse_all(ctx, progress=None, bootstrap: int = 40, placebo_wells: int = 10) -> list[dict]:
    rows = []
    events = engine.all_events(ctx)
    for i, e in enumerate(events):
        if progress:
            progress(f"Analysing {e['well_id']} ({i + 1}/{len(events)})")
        a = engine.analysis(ctx, e["well_id"], e["pre_end"], e["post_start"], kind=e["kind"], bootstrap=bootstrap, placebo_wells=placebo_wells, event_label=e["label"])
        rows.append(summarise(ctx, e, a))
    return rows


def _water_change(ctx, well_id: str, pre_end: int, post_start: int, post_len: int) -> float | None:
    w = ctx.ds.panel("water_bpd")[well_id].to_numpy(dtype=float)
    pre = w[max(0, pre_end - 5): pre_end + 1]
    post = w[post_start: post_start + post_len]
    if np.isfinite(pre).sum() < 2 or np.isfinite(post).sum() < 2:
        return None
    return float(np.nanmean(post) - np.nanmean(pre))


def summarise(ctx, e: dict, a: dict) -> dict:
    s = ctx.settings
    post_len = len(a["post_idx"])
    cost = e.get("cost")
    if cost is None:
        cost = val(s["economics"]["intervention_costs"]["restart"])
        cost_source = "ILLUSTRATIVE ECONOMIC ASSUMPTION"
    else:
        cost_source = "RECORD"
    eff = [x if x is not None else 0.0 for x in a["effect_bpd"]]
    wchg = _water_change(ctx, e["well_id"], e["pre_end"], e["post_start"], post_len)
    handling = _handling(ctx, e["well_id"])
    if e["kind"] == "restart":
        # do-nothing for a restart = the well stays idle → value is the whole post-restart stream (and its water)
        post_act = [x if x is not None else 0.0 for x in a["actual"][-post_len:]]
        wpost = ctx.ds.panel("water_bpd")[e["well_id"]].to_numpy(dtype=float)[a["post_idx"][0]: a["post_idx"][0] + post_len]
        econ = economics.evaluate(s, post_act, [float(np.nan_to_num(w, nan=0.0)) for w in wpost], cost, days=a["days"][-post_len:], handling=handling, label=e["label"]) if a["status"] == "COMPLETE" else None
        value_basis = "vs staying idle"
    else:
        econ = economics.evaluate(s, eff, [wchg or 0.0] * post_len, cost, days=a["days"][-post_len:], handling=handling, label=e["label"]) if a["status"] == "COMPLETE" else None
        value_basis = "vs counterfactual baseline"
    persistence = {}
    for m in (3, 6, 12, 24):
        if m <= post_len:
            persistence[str(m)] = round(float(np.mean(eff[:m])), 2)
    # duration of effect: months until cumulative effect stops growing (or effect < 10% of initial)
    dur = None
    if a["status"] == "COMPLETE" and eff:
        e0 = max(abs(eff[0]), 1e-6)
        dur = next((i for i, x in enumerate(eff) if abs(x) < 0.1 * e0), post_len)
    return {
        "intervention_id": e.get("intervention_id") or f"OBS-{e['well_id']}-{a['post_idx'][0]}", "well_id": e["well_id"], "date": e["month"], "type": e["type"], "kind": e["kind"], "recorded": e["recorded"],
        "cost": float(cost), "cost_source": cost_source, "value_basis": value_basis, "pre_rate_bpd": a["naive_pre_level"], "post_rate_bpd": a["naive_post_level"],
        "naive_gain_bpd": a["naive_effect_bpd"], "causal_gain_bpd": a["mean_effect_bpd"], "gain_lo_bpd": a["effect_lo_bpd"], "gain_hi_bpd": a["effect_hi_bpd"],
        "cumulative_oil_bbl": a["cumulative_effect_bbl"], "naive_cumulative_bbl": a["naive_cumulative_bbl"], "water_change_bpd": None if wchg is None else round(wchg, 1),
        "duration_months": dur, "net_value": econ["npv"] if econ else None, "gross_value": econ["gross_value"] if econ else None, "payback_months": econ["payback_months"] if econ else None,
        "confidence": a["confidence"], "evidence_status": a["status"], "model": a["model"], "analysis_id": a["analysis_id"], "persistence": persistence,
        "donor_count": a["diagnostics"].get("donor_count"), "post_start_t": int(a["post_idx"][0]), "pre_end_t": int(a["pre_idx"][-1]), "pre_r2": a["diagnostics"].get("pre_r2"), "field": _field(ctx, e["well_id"]), "archetype": archetype(ctx, e["well_id"], e["pre_end"]),
        "truth": a.get("truth"),
        **restart_features(ctx, e, a),
    }


def restart_features(ctx, e: dict, a: dict) -> dict:
    """Features used to find analogous restarts for currently idle wells (causal recovery ratio, not naive)."""
    if e["kind"] != "restart" or a["status"] != "COMPLETE":
        return {}
    n_post = len(a["post_idx"])
    act = np.array([x if x is not None else np.nan for x in a["actual"][-n_post:]], dtype=float)
    cf = np.array([x if x is not None else np.nan for x in a["counterfactual"][-n_post:]], dtype=float)
    k = min(6, n_post)
    rr = float(np.nanmean(act[:k]) / max(np.nanmean(cf[:k]), 1e-6)) if np.isfinite(cf[:k]).any() else None
    oil = ctx.ds.panel("oil_bpd")[e["well_id"]].to_numpy(dtype=float)
    wc = ctx.ds.panel("water_cut")[e["well_id"]].to_numpy(dtype=float)
    pe = e["pre_end"]
    pre = oil[max(0, pe - 11): pe + 1]
    wc_pre = float(np.nanmean(wc[max(0, pe - 2): pe + 1])) if np.isfinite(wc[max(0, pe - 2): pe + 1]).any() else None
    first, last = float(np.nanmean(pre[:3])), float(np.nanmean(pre[-3:]))
    post_prod = oil[e["post_start"]: e["post_start"] + 6]
    sustained = bool(np.nan_to_num(post_prod, nan=0.0).__gt__(0.5).sum() >= min(6, len(post_prod)))
    from . import idle as _idle
    prof = _idle.pre_shutin_profile(ctx, e["well_id"], e["pre_end"] + 1)
    reasons = _idle.classify_reason(prof, 3.0)
    idle_m = int(e["post_start"] - e["pre_end"] - 1)
    own_base = float(np.nanmean(pre[-3:])) * (0.99 ** idle_m) if np.isfinite(pre[-3:]).any() else None
    rr_own = float(np.nanmean(act[:k]) / max(own_base, 1e-6)) if own_base else None
    return {"recovery_ratio": None if rr is None else round(min(rr, 3.0), 3), "recovery_ratio_own": None if rr_own is None else round(min(rr_own, 3.0), 3), "wc_pre": wc_pre, "estimated_reason": reasons[0]["reason"] if reasons else "UNKNOWN", "decline_ratio": (last / first) if first > 0 else None, "sustained": sustained, "idle_months": int(e["post_start"] - e["pre_end"] - 1)}


def _field(ctx, wid):
    w = ctx.ds.wells.set_index("well_id")
    return str(w.loc[wid, "field"]) if wid in w.index else None


def _handling(ctx, wid):
    w = ctx.ds.wells.set_index("well_id")
    fac = ctx.ds.facilities.set_index("facility_id") if len(ctx.ds.facilities) else None
    if fac is not None and wid in w.index and "facility_id" in w.columns and w.loc[wid, "facility_id"] in fac.index:
        return str(fac.loc[w.loc[wid, "facility_id"], "water_handling"])
    return "disposal"


def archetype(ctx, wid: str, t: int) -> str:
    oil = ctx.ds.panel("oil_bpd")[wid].to_numpy(dtype=float)
    wc = ctx.ds.panel("water_cut")[wid].to_numpy(dtype=float)
    pre = slice(max(0, t - 5), t + 1)
    r = float(np.nanmean(oil[pre])) if np.isfinite(oil[pre]).any() else 0.0
    w = float(np.nanmean(wc[pre])) if np.isfinite(wc[pre]).any() else 0.5
    rate = "high-rate" if r >= 60 else "mid-rate" if r >= 20 else "low-rate"
    water = "high-water" if w >= 0.85 else "mid-water" if w >= 0.6 else "low-water"
    return f"{rate}, {water}"


#: Chart keys the intervention page always expects. Returning a partial shape made
#: the page crash on `charts.scatter.map(...)` for any data set with no intervention
#: history (for example public volumetric data, which contains none).
CHART_KEYS = ("scatter", "outcome_bins", "by_type", "by_archetype", "persistence",
              "confidence", "over_time")

EMPTY_KPIS = {
    "jobs_analysed": 0, "recorded_jobs": 0, "observed_restarts": 0, "total_spend": 0.0,
    "value_created": 0.0, "value_destroyed": 0.0, "naive_uplift_bpd": 0.0,
    "causal_uplift_bpd": 0.0, "positive_payback": 0, "negative_payback": 0,
    "insufficient_evidence": 0, "would_have_improved_anyway": 0, "restart_median_recovery": None,
}


def empty_overview() -> dict:
    """Full-shaped, all-empty response so the UI renders an empty state, never crashes."""
    return {"kpis": dict(EMPTY_KPIS),
            "charts": {k: ({} if k == "persistence" else []) for k in CHART_KEYS},
            "has_history": False}


def overview(rows: list[dict]) -> dict:
    df = pd.DataFrame(rows)
    if df.empty:
        return empty_overview()
    comp = df[df.evidence_status == "COMPLETE"]
    ci = comp[comp.kind == "intervention"]
    val_created = float(comp.loc[comp.net_value > 0, "net_value"].sum()) if len(comp) else 0.0
    val_destroyed = float(-comp.loc[comp.net_value < 0, "net_value"].sum()) if len(comp) else 0.0
    kpis = {
        "jobs_analysed": int(len(df)), "recorded_jobs": int(df.recorded.sum()), "observed_restarts": int((~df.recorded).sum()), "total_spend": float(df.cost.sum()),
        "value_created": val_created, "value_destroyed": val_destroyed, "naive_uplift_bpd": float(ci.naive_gain_bpd.sum()) if len(ci) else 0.0,
        "causal_uplift_bpd": float(ci.causal_gain_bpd.sum()) if len(ci) else 0.0, "positive_payback": int((comp.net_value > 0).sum()), "negative_payback": int((comp.net_value <= 0).sum()),
        "insufficient_evidence": int((df.evidence_status != "COMPLETE").sum()), "would_have_improved_anyway": int(((ci.naive_gain_bpd > 0) & (ci.causal_gain_bpd <= 0.25 * ci.naive_gain_bpd)).sum()),
        "restart_median_recovery": round(float(comp[comp.kind == "restart"].recovery_ratio.dropna().median()), 3) if (comp.kind == "restart").any() and "recovery_ratio" in comp.columns else None,
    }
    by_type = []
    for t, g in comp.groupby("type"):
        by_type.append({"type": t, "n": int(len(g)), "success_rate": round(float((g.net_value > 0).mean()), 3), "median_payback": float(g.payback_months.dropna().median()) if g.payback_months.notna().any() else None,
                        "median_causal_bpd": round(float(g.causal_gain_bpd.median()), 2), "median_naive_bpd": round(float(g.naive_gain_bpd.median()), 2), "water_change_bpd": round(float(g.water_change_bpd.dropna().median()), 2) if g.water_change_bpd.notna().any() else None,
                        "total_cost": float(g.cost.sum()), "total_value": float(g.net_value.sum())})
    by_arch = [{"archetype": a, "n": int(len(g)), "median_causal_bpd": round(float(g.causal_gain_bpd.median()), 2)} for a, g in comp.groupby("archetype")]
    persistence = {}
    for m in ("3", "6", "12", "24"):
        vals = [r["persistence"].get(m) for r in rows if r["persistence"].get(m) is not None]
        if vals:
            persistence[m] = round(float(np.mean(vals)), 2)
    conf = df.confidence.value_counts().to_dict()
    over_time = [{"year": y, "n": int(len(g)), "causal_bpd": round(float(g.causal_gain_bpd.mean()), 2), "naive_bpd": round(float(g.naive_gain_bpd.mean()), 2)} for y, g in comp.groupby(comp.date.str[:4])]
    scatter = [{"intervention_id": r.intervention_id, "well_id": r.well_id, "naive": r.naive_gain_bpd, "causal": r.causal_gain_bpd, "cost": r.cost, "value": r.net_value, "type": r.type, "confidence": r.confidence} for r in comp.itertuples()]
    outcome_bins = np.histogram(comp.causal_gain_bpd.dropna(), bins=[-50, -5, -1, 0, 1, 3, 6, 12, 25, 100])[0].tolist()
    return {"kpis": kpis, "has_history": True,
            "charts": {"by_type": by_type, "by_archetype": by_arch, "persistence": persistence, "confidence": conf, "over_time": over_time, "scatter": scatter,
                       "outcome_bins": {"edges": [-50, -5, -1, 0, 1, 3, 6, 12, 25, 100], "counts": outcome_bins}}}


def type_evidence(rows: list[dict], itype: str) -> dict:
    """Operating memory: what happened the last N times we performed this intervention."""
    g = [r for r in rows if r["type"] == itype and r["evidence_status"] == "COMPLETE"]
    if not g:
        return {"type": itype, "n": 0, "status": "INSUFFICIENT EVIDENCE"}
    eff = np.array([r["causal_gain_bpd"] for r in g], dtype=float)
    pre = np.array([r["pre_rate_bpd"] for r in g], dtype=float)
    ratio = eff / np.maximum(pre, 1e-6)
    return {"type": itype, "n": len(g), "status": "OK", "median_effect_bpd": round(float(np.median(eff)), 2), "p20_effect_bpd": round(float(np.percentile(eff, 20)), 2), "p80_effect_bpd": round(float(np.percentile(eff, 80)), 2),
            "median_effect_ratio": round(float(np.median(ratio)), 3), "p20_ratio": round(float(np.percentile(ratio, 20)), 3), "p80_ratio": round(float(np.percentile(ratio, 80)), 3),
            "success_rate": round(float(np.mean([r["net_value"] > 0 for r in g])), 3), "positive_effect_rate": round(float(np.mean(eff > 0)), 3),
            "median_duration": float(np.median([r["duration_months"] for r in g if r["duration_months"] is not None])) if any(r["duration_months"] is not None for r in g) else None,
            "median_water_change_bpd": round(float(np.median([r["water_change_bpd"] for r in g if r["water_change_bpd"] is not None])), 2) if any(r["water_change_bpd"] is not None for r in g) else None,
            "median_cost": float(np.median([r["cost"] for r in g])), "failures": [r["intervention_id"] for r in g if r["net_value"] <= 0], "source_wells": [r["well_id"] for r in g]}
