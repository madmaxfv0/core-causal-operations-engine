"""M3 — Ghost barrels: quiet under-performance against a donor-based counterfactual baseline.

The counterfactual core is reused with a *pseudo* event: 'what would this well be producing now if it had kept
tracking its comparable wells?' No alarm needed, no failure needed.
"""
from __future__ import annotations

import numpy as np

from ..config import val
from . import decline as dc
from . import economics, engine, memory

LOOKBACK = 6


def screen(ctx, progress=None, bootstrap: int = 30, placebo_wells: int = 6) -> dict:
    s = ctx.settings
    n = ctx.ds.n_months
    if n <= LOOKBACK + 1:
        return {
            "kpi": {
                "wells_screened": 0,
                "candidates": 0,
                "estimated_recoverable_bpd": 0.0,
                "estimated_range_bpd": [0.0, 0.0],
                "label": "Unavailable: at least 8 monthly periods are required for this screen",
            },
            "rows": [],
            "lookback_months": LOOKBACK,
            "unavailable": "Insufficient reported monthly history for a 6-month lookback and pre-period.",
        }
    post_start = n - LOOKBACK
    pre_end = post_start - 1
    producing = [w for w, r in ctx.status.iterrows() if r.status == "producing"]
    rows = []
    for i, wid in enumerate(producing):
        if progress:
            progress(f"Screening {wid} ({i + 1}/{len(producing)})")
        # skip wells with their own event inside the look-back (they belong to intervention memory, not ghost barrels)
        own = [(a, b) for (a, b) in ctx.event_index.get(wid, []) if not (b < pre_end - 12 or a > n)]
        if own:
            continue
        a = engine.analysis(ctx, wid, pre_end, post_start, kind="pseudo", post_window=LOOKBACK, bootstrap=bootstrap, placebo_wells=placebo_wells, event_label="Ghost-barrel screen")
        if a["status"] != "COMPLETE":
            continue
        eff = np.array([x if x is not None else np.nan for x in a["effect_bpd"]], dtype=float)
        gap = -float(np.nanmean(eff))  # positive = producing below baseline
        actual = float(np.nanmean([x for x in a["actual"][-LOOKBACK:] if x is not None]))
        expected = float(np.nanmean([x for x in a["counterfactual"][-LOOKBACK:] if x is not None]))
        gap_pct = gap / max(expected, 1e-6)
        lo, hi = -a["effect_hi_bpd"], -a["effect_lo_bpd"]
        # duration: consecutive recent months below the baseline lower band
        below = [(x is not None and c is not None and x < c) for x, c in zip(a["actual"][-LOOKBACK:], a["cf_lo"][-LOOKBACK:])]
        dur = 0
        for b in reversed(below):
            if b:
                dur += 1
            else:
                break
        rows.append({"well_id": wid, "field": memory._field(ctx, wid), "observed_bpd": round(actual, 1), "expected_bpd": round(expected, 1), "gap_bpd": round(gap, 1), "gap_lo": round(lo, 1), "gap_hi": round(hi, 1), "gap_pct": round(gap_pct, 3),
                     "duration_months": dur, "confidence": a["confidence"], "analysis_id": a["analysis_id"], "model": a["model"], "water_cut": _wc(ctx, wid), "dq_score": float(ctx.quality.loc[wid, "dq_score"]) if wid in ctx.quality.index else None})
    # opportunity: below baseline beyond the lower band, positive gap, not flagged by DQ
    for r in rows:
        signif = r["gap_lo"] > 0 and r["gap_pct"] >= 0.08 and (r["dq_score"] or 0) >= 60
        r["is_opportunity"] = bool(signif and r["confidence"] != "INSUFFICIENT EVIDENCE")
        r["oil_opportunity_bpd"] = round(max(r["gap_bpd"], 0.0), 1) if r["is_opportunity"] else 0.0
        nb = economics.netback(s)["value"]
        r["annual_value"] = round(r["oil_opportunity_bpd"] * 365 * nb, 0)
    decomp_all = {}
    for r in rows:
        if r["is_opportunity"]:
            d = decompose(ctx, r)
            r["probable_driver"] = d["probable_driver"]
            r["decomposition"] = d
    opps = [r for r in rows if r["is_opportunity"]]
    opps.sort(key=lambda r: -r["oil_opportunity_bpd"])
    others = [r for r in rows if not r["is_opportunity"]]
    others.sort(key=lambda r: -r["gap_bpd"])
    return {"kpi": {"wells_screened": len(rows), "candidates": len(opps), "estimated_recoverable_bpd": round(sum(r["oil_opportunity_bpd"] for r in opps), 1),
                    "estimated_range_bpd": [round(sum(r["gap_lo"] for r in opps), 1), round(sum(r["gap_hi"] for r in opps), 1)], "label": "Estimated opportunity under current model assumptions"},
            "rows": opps + others, "lookback_months": LOOKBACK}


def _wc(ctx, wid):
    wc = ctx.ds.panel("water_cut")[wid].to_numpy(dtype=float)[-3:]
    return round(float(np.nanmean(wc)), 3) if np.isfinite(wc).any() else None


def decompose(ctx, row: dict) -> dict:
    """Lost-production decomposition from the data that exists. Components without supporting data are marked unavailable."""
    wid = row["well_id"]
    n = ctx.ds.n_months
    oil = ctx.ds.panel("oil_bpd")[wid].to_numpy(dtype=float)
    wat = ctx.ds.panel("water_bpd")[wid].to_numpy(dtype=float)
    wc = ctx.ds.panel("water_cut")[wid].to_numpy(dtype=float)
    hrs = ctx.ds.panel("hours")[wid].to_numpy(dtype=float)
    pre = slice(n - LOOKBACK - 12, n - LOOKBACK)
    post = slice(n - LOOKBACK, n)
    gap = row["gap_bpd"]
    comps = []
    # natural decline: what the well's own decline fit says it should have lost vs the pre-period mean
    fit = dc.fit_arps(np.nan_to_num(oil[pre], nan=0.0))
    if fit.get("ok") and not fit.get("poor_fit"):
        pre_mean = float(np.nanmean(oil[pre]))
        proj = float(np.mean(dc.extrapolate(fit, np.arange(12, 12 + LOOKBACK))))
        nat = max(0.0, pre_mean - proj)
        # the counterfactual baseline already embeds the field's typical decline, so only the *excess* over donors' decline is attributed here
        exp_decline = pre_mean - row["expected_bpd"]
        comps.append({"component": "natural_decline", "label": "Natural decline (beyond comparable wells)", "bpd": round(max(0.0, nat - exp_decline), 1), "status": "STRONG INFERENCE" if fit["r2"] > 0.6 else "HYPOTHESIS", "note": f"Arps {fit['model']} fit r²={fit['r2']:.2f}"})
    else:
        comps.append({"component": "natural_decline", "label": "Natural decline", "bpd": None, "status": "UNVERIFIED", "note": "decline fit unstable"})
    # water effect: with total fluid held at pre level, extra water cut displaces oil
    fl_pre = float(np.nanmean(oil[pre] + wat[pre]))
    wc_pre, wc_post = float(np.nanmean(wc[pre])), float(np.nanmean(wc[post]))
    if np.isfinite(wc_pre) and np.isfinite(wc_post) and fl_pre > 0:
        water_eff = max(0.0, fl_pre * (wc_post - wc_pre))
        comps.append({"component": "water_increase", "label": "Water-cut increase", "bpd": round(water_eff, 1), "status": "STRONG INFERENCE" if wc_post - wc_pre > 0.03 else "HYPOTHESIS", "note": f"water cut {wc_pre:.0%} → {wc_post:.0%} at constant fluid"})
    else:
        comps.append({"component": "water_increase", "label": "Water-cut increase", "bpd": None, "status": "UNVERIFIED", "note": "no water data"})
    # downtime
    h_pre, h_post = float(np.nanmean(hrs[pre])), float(np.nanmean(hrs[post]))
    if np.isfinite(h_pre) and np.isfinite(h_post) and h_pre > 0:
        down = max(0.0, row["expected_bpd"] * (1 - h_post / h_pre))
        comps.append({"component": "downtime", "label": "Operating hours / downtime", "bpd": round(down, 1), "status": "CONFIRMED" if h_post < 0.97 * h_pre else "HYPOTHESIS", "note": f"{h_post:.0f} h/month vs {h_pre:.0f} h/month before"})
    else:
        comps.append({"component": "downtime", "label": "Operating hours / downtime", "bpd": None, "status": "UNVERIFIED", "note": "no hours reported"})
    for c, lbl in (("artificial_lift", "Pump / artificial-lift efficiency"), ("settings", "Operating setting changes"), ("injector_response", "Nearby injector/producer response"), ("mechanical", "Mechanical restriction")):
        comps.append({"component": c, "label": lbl, "bpd": None, "status": "UNVERIFIED", "note": "OPERATOR DATA REQUIRED (lift diagnostics / SCADA / injection data)"})
    dq = ctx.quality.loc[wid] if wid in ctx.quality.index else None
    comps.append({"component": "measurement", "label": "Measurement / data issue", "bpd": None, "status": "HYPOTHESIS" if dq is not None and dq.dq_score < 85 else "UNVERIFIED", "note": f"data-quality score {dq.dq_score:.0f}" if dq is not None else ""})
    explained = sum(c["bpd"] for c in comps if c["bpd"] is not None)
    residual = gap - explained
    comps.append({"component": "unexplained", "label": "Unexplained residual", "bpd": round(residual, 1), "status": "CALCULATED", "note": "gap minus attributed components"})
    driver = max((c for c in comps if c["bpd"] is not None and c["component"] != "unexplained"), key=lambda c: c["bpd"], default=None)
    probable = driver["label"] if driver and driver["bpd"] > 0.25 * max(gap, 1e-6) else "Unexplained"
    return {"expected_bpd": row["expected_bpd"], "observed_bpd": row["observed_bpd"], "gap_bpd": gap, "components": comps, "probable_driver": probable,
            "waterfall": [{"step": "Expected production", "value": row["expected_bpd"], "kind": "total"}] + [{"step": c["label"], "value": -c["bpd"], "kind": "delta"} for c in comps if c["bpd"] is not None] + [{"step": "Observed production", "value": row["observed_bpd"], "kind": "total"}]}


def why_panel(ctx, row: dict, memory_rows: list[dict]) -> dict:
    d = row.get("decomposition") or decompose(ctx, row)
    driver = d["probable_driver"]
    action = "water_shutoff" if "Water" in driver else "pump_optimisation" if "downtime" in driver.lower() or "hours" in driver.lower() else "diagnostic_test"
    ev = memory.type_evidence(memory_rows, action) if action != "diagnostic_test" else {"n": 0, "status": "n/a"}
    lines = [f"Production is {row['gap_pct']:.0%} below the estimated baseline ({row['observed_bpd']} vs {row['expected_bpd']} bbl/d) for {row['duration_months']} months.",
             f"Comparable wells did not experience the same decline (pre-period fit used {row['model'].replace('_', ' ')}).", f"Most likely contributor from available data: {driver}."]
    if ev.get("n"):
        lines.append(f"Historical {action.replace('_', ' ')} jobs on {ev['n']} wells produced a median causal effect of {ev['median_effect_bpd']} bbl/d.")
    return {"why": lines, "evidence": {"comparable_wells": ctx and None, "historic_interventions": ev.get("n", 0), "archive_documents": 0}, "uncertainty": row["confidence"],
            "could_be_wrong": ["No downhole pressure or pump diagnostics in the data set", "Facility constraints not observable in monthly volumes", "Economic assumptions are illustrative"],
            "action": action, "action_status": "TEST FIRST" if action == "diagnostic_test" else "REVIEW", "decomposition": d}
