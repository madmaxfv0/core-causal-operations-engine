"""M8 — Model Lab: CORE tries to falsify itself."""
from __future__ import annotations

import numpy as np
from scipy.stats import spearmanr

from ..config import MODEL_VERSION
from . import decline as dc
from . import engine, idle


def planted_truth(memory_rows: list[dict]) -> dict:
    rows = [r for r in memory_rows if r.get("truth") and r["truth"].get("kind") == "intervention" and r["evidence_status"] == "COMPLETE"]
    if not rows:
        return {"available": False, "note": "Planted-truth test requires the synthetic validation data set."}
    truth = np.array([r["truth"]["true_effect_bpd_12m"] for r in rows])
    core = np.array([r["causal_gain_bpd"] for r in rows])
    naive = np.array([r["naive_gain_bpd"] for r in rows])
    lo = np.array([r["gain_lo_bpd"] if r["gain_lo_bpd"] is not None else np.nan for r in rows])
    hi = np.array([r["gain_hi_bpd"] if r["gain_hi_bpd"] is not None else np.nan for r in rows])
    cov = np.nanmean((truth >= lo) & (truth <= hi))
    zero = truth <= 0.05
    return {"available": True, "n": len(rows), "label": "SYNTHETIC VALIDATION DATA",
            "metrics": {"core": {"mae": round(float(np.mean(np.abs(core - truth))), 2), "bias": round(float(np.mean(core - truth)), 2), "coverage_80": round(float(cov), 2), "spearman": round(float(spearmanr(truth, core).statistic), 3)},
                        "naive": {"mae": round(float(np.mean(np.abs(naive - truth))), 2), "bias": round(float(np.mean(naive - truth)), 2), "coverage_80": None, "spearman": round(float(spearmanr(truth, naive).statistic), 3)},
                        "zero_effect_jobs": {"n": int(zero.sum()), "core_mean": round(float(core[zero].mean()), 2) if zero.any() else None, "naive_mean": round(float(naive[zero].mean()), 2) if zero.any() else None}},
            "rows": [{"intervention_id": r["intervention_id"], "well_id": r["well_id"], "type": r["type"], "truth": round(float(t), 2), "naive": float(n_), "core": float(c), "lo": r["gain_lo_bpd"], "hi": r["gain_hi_bpd"], "confidence": r["confidence"]} for r, t, n_, c in zip(rows, truth, naive, core)]}


def placebo_summary(memory_rows: list[dict]) -> dict:
    out = {"in_time": [], "wells": []}
    for r in memory_rows:
        a = engine.cache_get(r["analysis_id"]) if r.get("analysis_id") else None
        if not a:
            continue
        pt = (a.get("placebo") or {}).get("in_time")
        pw = (a.get("placebo") or {}).get("wells")
        if pt:
            out["in_time"].append({"well_id": r["well_id"], "fake_effect_bpd": pt["fake_effect_bpd"], "actual_effect_bpd": pt["actual_effect_bpd"], "score": pt["score"]})
        if pw:
            out["wells"].append({"well_id": r["well_id"], "treated_rmspe_ratio": pw["treated_rmspe_ratio"], "p_value": pw["p_value"], "placebo_effects": [p["effect_bpd"] for p in pw["placebos"]]})
    ft = np.array([x["fake_effect_bpd"] for x in out["in_time"]]) if out["in_time"] else np.array([])
    at = np.array([x["actual_effect_bpd"] for x in out["in_time"]]) if out["in_time"] else np.array([])
    pe = np.concatenate([np.array(x["placebo_effects"]) for x in out["wells"]]) if out["wells"] else np.array([])
    out["summary"] = {"in_time_n": len(ft), "in_time_mean_abs_fake": round(float(np.mean(np.abs(ft))), 2) if len(ft) else None, "in_time_mean_abs_actual": round(float(np.mean(np.abs(at))), 2) if len(at) else None,
                      "placebo_well_effects_n": len(pe), "placebo_well_effects_mean": round(float(pe.mean()), 2) if len(pe) else None, "placebo_well_effects_sd": round(float(pe.std()), 2) if len(pe) else None,
                      "note": "Placebo effects should centre on zero: the method should find nothing where nothing happened."}
    out["placebo_hist"] = np.histogram(pe, bins=np.linspace(-10, 10, 21))[0].tolist() if len(pe) else []
    return out


def blind_test(ctx, memory_rows: list[dict], cutoff_t: int = 60) -> dict:
    """Hide everything after cutoff. Rank wells that were idle at the cutoff and later restarted; then reveal.

    CORE is compared with transparent baseline rules only — no engineer plan is invented.
    """
    ds = ctx.ds
    oil = ds.panel("oil_bpd")
    ev = ctx.restart_events
    cands = ev[(ev.shutin_t <= cutoff_t) & (ev.restart_t > cutoff_t)]
    if len(cands) < 5:
        return {"available": False, "note": f"Only {len(cands)} wells were idle at the cut-off and restarted afterwards."}
    hist = [r for r in memory_rows if r["kind"] == "restart" and r["evidence_status"] == "COMPLETE" and (r.get("post_start_t") or 0) <= cutoff_t]
    rows = []
    for r in cands.itertuples():
        wid = r.well_id
        s = int(r.shutin_t)
        prof = idle.pre_shutin_profile(ctx, wid, s)
        fit = dc.fit_arps(np.array([v or 0 for v in prof["series"]]))
        months_since = cutoff_t - s
        proj = float(dc.extrapolate(fit, np.array([len(prof["series"]) - 1 + months_since]))[0]) if fit.get("ok") else prof["last_rate_bpd"] * max(0.3, 1 - 0.01 * months_since)
        proj = min(max(proj, 0.0), prof["last_rate_bpd"] * 1.05)
        reasons = idle.classify_reason(prof, 3.0)
        analogs = idle.analog_restarts(hist, prof, reason=reasons[0]["reason"] if reasons else None)
        rec = idle._recovery_stats(analogs)
        core_score = proj * rec["p50"] * rec["sustain_rate"] if rec else proj * 0.7 * 0.7
        post = oil[wid].to_numpy(dtype=float)[int(r.restart_t): int(r.restart_t) + 6]
        actual = float(np.nanmean(post)) if np.isfinite(post).any() else 0.0
        rows.append({"well_id": wid, "shutin_month": ds.months[s], "restart_month": ds.months[int(r.restart_t)], "last_rate_bpd": round(prof["last_rate_bpd"], 1), "peak_bpd": round(prof["peak_bpd"], 1), "water_cut": prof["wc_last"],
                     "core_expected_bpd": round(core_score, 1), "analogs": len(analogs), "estimated_reason": reasons[0]["reason"] if reasons else None, "actual_6m_bpd": round(actual, 1), "naive_expected_bpd": round(prof["last_rate_bpd"], 1)})
    def ranking(key, reverse=True):
        order = sorted(rows, key=lambda x: (x[key] if x[key] is not None else 0), reverse=reverse)
        return [x["well_id"] for x in order]
    actual = {x["well_id"]: x["actual_6m_bpd"] for x in rows}
    total = sum(actual.values()) or 1.0
    methods = {"CORE (analogue-adjusted counterfactual)": ranking("core_expected_bpd"), "Highest previous production": ranking("peak_bpd"), "Lowest water cut": ranking("water_cut", reverse=False), "Naive restart ranking (last rate)": ranking("naive_expected_bpd")}
    k = max(3, len(rows) // 3)
    results = []
    for name, order in methods.items():
        sc = [dict(zip(order, range(len(order))))[w] for w in [x["well_id"] for x in rows]]
        act = [x["actual_6m_bpd"] for x in rows]
        rho = spearmanr(-np.array(sc), act).statistic if len(rows) > 2 else None
        captured = sum(actual[w] for w in order[:k]) / total
        results.append({"method": name, "spearman": round(float(rho), 3) if rho is not None and np.isfinite(rho) else None, "top_k": k, "top_k_captured_share": round(float(captured), 3), "top_k_wells": order[:k]})
    return {"available": True, "cutoff_month": ds.months[cutoff_t], "n": len(rows), "rows": rows, "results": results, "label": ds.meta.get("data_mode"),
            "note": "Rankings use only information before the cut-off. Comparators are transparent rules, not an engineer plan."}


def calibration(memory_rows: list[dict], idle_rows: list[dict]) -> dict:
    """Does '80% confidence' mean 80%? Uses confidence scores vs realised positive causal effect on completed analyses."""
    pts = []
    for r in memory_rows:
        a = engine.cache_get(r["analysis_id"]) if r.get("analysis_id") else None
        if not a or a["status"] != "COMPLETE" or r["kind"] != "intervention":
            continue
        pts.append((a["diagnostics"].get("confidence_score", 0.5), 1.0 if r["causal_gain_bpd"] > 0 else 0.0, r.get("truth")))
    bins = [0, 0.5, 0.65, 0.8, 1.01]
    out = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        g = [p for p in pts if lo <= p[0] < hi]
        if g:
            truth_pos = [1.0 if (p[2] and p[2].get("true_effect_bpd_12m", 0) > 0) else 0.0 for p in g if p[2]]
            out.append({"bin": f"{lo:.2f}–{min(hi, 1):.2f}", "n": len(g), "mean_confidence": round(float(np.mean([p[0] for p in g])), 3), "positive_effect_rate": round(float(np.mean([p[1] for p in g])), 3),
                        "true_positive_rate": round(float(np.mean(truth_pos)), 3) if truth_pos else None})
    return {"bins": out, "note": "Confidence is a score of evidence quality, not a probability of success; calibration checks whether higher-scored analyses are more often right."}


def reason_accuracy(ctx, idle_rows: list[dict]) -> dict:
    te = ctx.ds.truth_events
    if te is None:
        return {"available": False}
    tr = te[te.kind == "shutin"].set_index("well_id").true_reason.to_dict()
    n = hit = 0
    conf = {}
    for r in idle_rows:
        t = tr.get(r["well_id"])
        if t is None:
            continue
        n += 1
        hit += int(r["estimated_reason"] == t)
        conf.setdefault(t, {}).setdefault(r["estimated_reason"], 0)
        conf[t][r["estimated_reason"]] += 1
    return {"available": n > 0, "n": n, "accuracy": round(hit / n, 3) if n else None, "confusion": conf, "note": "Rule-based classifier vs planted shut-in reasons (synthetic only). OPERATIONAL shut-ins have no production signature and are expected to be UNKNOWN."}


def model_cards() -> list[dict]:
    return [
        {"model": "Synthetic control", "purpose": "Counterfactual production from a convex combination of comparable untreated wells", "fit_data": "Pre-event window of treated well and donor pool", "features": "monthly oil rate", "assumptions": "treated well lies in donor convex hull; no spill-over; donors untreated in window", "limitations": "cannot capture well-specific transients; needs ≥5 donors", "validation": "pre-fit R², placebo-in-time, placebo wells, planted-truth", "version": MODEL_VERSION, "owner": "CORE causal core"},
        {"model": "Matched wells", "purpose": "Level-scaled mean of the 5 most similar wells", "fit_data": "Pre-event window", "features": "log rate, decline, water cut, variability, uptime", "assumptions": "proportional dynamics", "limitations": "weaker pre-fit than synthetic control", "validation": "same suite", "version": MODEL_VERSION, "owner": "CORE causal core"},
        {"model": "Difference-in-differences (log)", "purpose": "Treated pre level × donor post/pre ratio", "fit_data": "Pre-event window", "features": "donor mean trajectory", "assumptions": "parallel (log) trends", "limitations": "sensitive to donor composition", "validation": "same suite", "version": MODEL_VERSION, "owner": "CORE causal core"},
        {"model": "Decline curve (Arps)", "purpose": "Transparent benchmark; fallback when donors are insufficient", "fit_data": "Pre-event window", "features": "time", "assumptions": "stable decline", "limitations": "ignores field-wide effects; flagged on unstable wells", "validation": "fit R², rising-trend flag", "version": MODEL_VERSION, "owner": "CORE causal core"},
        {"model": "Idle-well reason classifier", "purpose": "Evidence-carrying shut-in reason hypotheses", "fit_data": "12 months before shut-in", "features": "water cut trend, hours, rate decline", "assumptions": "production signatures reflect causes", "limitations": "OPERATIONAL/INFRASTRUCTURE causes have no signature", "validation": "accuracy vs planted reasons", "version": MODEL_VERSION, "owner": "CORE idle module"},
        {"model": "Portfolio MILP", "purpose": "Select and schedule jobs under budget, crews, rigs, concurrency", "fit_data": "candidate table", "features": "cost, NPV, oil, water, duration, risk", "assumptions": "independent jobs; quarter granularity", "limitations": "no travel/spares constraints", "validation": "constraint tests", "version": MODEL_VERSION, "owner": "CORE planner"},
        {"model": "Archive extraction (LLM/mock)", "purpose": "Structure scanned intervention reports", "fit_data": "n/a", "features": "document text", "assumptions": "fields present in text", "limitations": "never decides economics; unreadable → manual review", "validation": "reviewed sample accuracy", "version": MODEL_VERSION, "owner": "CORE archive AI"},
    ]
