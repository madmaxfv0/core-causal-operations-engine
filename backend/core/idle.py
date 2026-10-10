"""M2 — Idle well recovery. Screens inactive wells; never implies every idle well should be restarted."""
from __future__ import annotations

import numpy as np

from ..config import val
from . import decline as dc
from . import economics, memory

REASONS = ["GEOLOGICAL", "MECHANICAL", "WATER-RELATED", "ECONOMIC", "OPERATIONAL", "INFRASTRUCTURE", "UNKNOWN"]
REASON_TO_ACTION = {"WATER-RELATED": "water_shutoff", "MECHANICAL": "pump_replacement", "GEOLOGICAL": "stimulation", "ECONOMIC": "cleanout", "OPERATIONAL": "restart", "INFRASTRUCTURE": "restart", "UNKNOWN": "restart"}
SCENARIOS = ["do_nothing", "restart", "pump_replacement", "cleanout", "water_shutoff", "stimulation", "workover"]


def pre_shutin_profile(ctx, wid: str, shutin_t: int, window: int = 12) -> dict:
    oil = ctx.ds.panel("oil_bpd")[wid].to_numpy(dtype=float)
    wc = ctx.ds.panel("water_cut")[wid].to_numpy(dtype=float)
    hrs = ctx.ds.panel("hours")[wid].to_numpy(dtype=float)
    lo = max(0, shutin_t - window)
    seg_oil, seg_wc, seg_h = oil[lo:shutin_t], wc[lo:shutin_t], hrs[lo:shutin_t]
    valid = np.isfinite(seg_oil) & (seg_oil > 0)
    peak = float(np.nanmax(oil[:shutin_t])) if shutin_t > 0 and np.isfinite(oil[:shutin_t]).any() else 0.0
    last_rate = float(np.nanmean(seg_oil[-3:])) if valid[-3:].any() else 0.0
    first_rate = float(np.nanmean(seg_oil[:3])) if valid[:3].any() else last_rate
    wc_last = float(np.nanmean(seg_wc[-3:])) if np.isfinite(seg_wc[-3:]).any() else None
    wc_first = float(np.nanmean(seg_wc[:3])) if np.isfinite(seg_wc[:3]).any() else None
    h_last = float(np.nanmean(seg_h[-1:])) if np.isfinite(seg_h[-1:]).any() else None
    h_mean = float(np.nanmean(seg_h[:-1])) if np.isfinite(seg_h[:-1]).any() else None
    r24 = float(np.nanmean(oil[max(0, shutin_t - 26): max(1, shutin_t - 22)])) if shutin_t >= 24 and np.isfinite(oil[max(0, shutin_t - 26): max(1, shutin_t - 22)]).any() else None
    return {"months_available": int(valid.sum()), "rate_24m_ago": r24, "last_rate_bpd": last_rate, "first_rate_bpd": first_rate, "peak_bpd": peak, "wc_last": wc_last, "wc_first": wc_first,
            "hours_last": h_last, "hours_mean": h_mean, "decline_ratio": (last_rate / first_rate) if first_rate > 0 else None, "series": [None if not np.isfinite(v) else round(float(v), 2) for v in seg_oil],
            "wc_series": [None if not np.isfinite(v) else round(float(v), 3) for v in seg_wc], "hours_series": [None if not np.isfinite(v) else round(float(v), 0) for v in seg_h], "t_from": lo}


def classify_reason(profile: dict, econ_limit_bpd: float, has_docs: bool = False) -> list[dict]:
    """Rule-based, evidence-carrying classification. Probabilities are normalised heuristic scores, labelled as such."""
    scores = {r: 0.0 for r in REASONS}
    ev = {r: [] for r in REASONS}
    wl, wf, lr, fr, peak = profile["wc_last"], profile["wc_first"], profile["last_rate_bpd"], profile["first_rate_bpd"], profile["peak_bpd"]
    hl, hm = profile["hours_last"], profile["hours_mean"]
    r24 = profile.get("rate_24m_ago")
    ser = [v for v in profile["series"] if v is not None]
    if profile["months_available"] < 4:
        scores["UNKNOWN"] += 3
        ev["UNKNOWN"].append("fewer than 4 producing months before shut-in")
    wc_rise = (wl - wf) if (wl is not None and wf is not None) else 0.0
    if wl is not None and wf is not None:
        if wl >= 0.93 and wc_rise >= 0.08:
            scores["WATER-RELATED"] += 3
            ev["WATER-RELATED"].append(f"water cut rose from {wf:.0%} to {wl:.0%} in the last year")
        elif wl >= 0.90:
            scores["WATER-RELATED"] += 1.0
            ev["WATER-RELATED"].append(f"water cut {wl:.0%} at shut-in")
    if hl is not None and hm is not None and hm > 0 and hl < 0.6 * hm:
        scores["MECHANICAL"] += 3
        ev["MECHANICAL"].append(f"operating hours fell to {hl:.0f} h in the final month (avg {hm:.0f} h)")
    elif len(ser) >= 4 and ser[-1] < 0.5 * (sum(ser[-4:-1]) / 3) and wc_rise < 0.05:
        scores["MECHANICAL"] += 1.5
        ev["MECHANICAL"].append("abrupt rate drop in the final month without a water-cut change")
    econ_level = max(econ_limit_bpd, 0.15 * peak)
    if lr <= econ_level and wc_rise < 0.08:
        scores["ECONOMIC"] += 2.5
        ev["ECONOMIC"].append(f"rate {lr:.1f} bbl/d is below {econ_level:.1f} bbl/d ({'economic limit' if econ_level == econ_limit_bpd else '15% of historical peak'})")
    decline24 = (lr / r24) if (r24 and r24 > 0) else None
    if decline24 is not None and decline24 <= 0.65 and wc_rise < 0.05 and lr > econ_level:
        scores["GEOLOGICAL"] += 2.5
        ev["GEOLOGICAL"].append(f"rate fell to {decline24:.0%} of its level two years earlier with stable water cut (depletion signature)")
    elif fr > 0 and lr < 0.6 * fr and wc_rise < 0.05 and lr > econ_level:
        scores["GEOLOGICAL"] += 1.2
        ev["GEOLOGICAL"].append(f"decline from {fr:.1f} to {lr:.1f} bbl/d over the last year")
    if sum(scores.values()) < 1.0:
        scores["OPERATIONAL"] += 1.0
        ev["OPERATIONAL"].append("no production signature before shut-in (possible facility or operational cause)")
        scores["UNKNOWN"] += 1.0
        ev["UNKNOWN"].append("no distinguishing evidence in production data")
    tot = sum(scores.values()) or 1.0
    out = []
    for r in REASONS:
        p = scores[r] / tot
        if p <= 0.02:
            continue
        quality = "STRONG INFERENCE" if p >= 0.55 and ev[r] else "HYPOTHESIS" if ev[r] else "UNVERIFIED"
        out.append({"reason": r, "probability": round(p, 2), "evidence": ev[r], "evidence_quality": quality, "source": "production history" + (" + archive documents" if has_docs else "")})
    out.sort(key=lambda x: -x["probability"])
    return out


def analog_restarts(memory_rows: list[dict], profile: dict, k: int = 8, reason: str | None = None) -> list[dict]:
    """Nearest historical restart events by pre-shut-in features and estimated shut-in cause."""
    cands = [r for r in memory_rows if r["kind"] == "restart" and r["evidence_status"] == "COMPLETE" and r.get("pre_rate_bpd")]
    if not cands:
        return []
    f0 = np.array([np.log(max(profile["last_rate_bpd"], 0.5)), profile["wc_last"] or 0.5, profile["decline_ratio"] or 1.0])
    rows = []
    for r in cands:
        f = np.array([np.log(max(r["pre_rate_bpd"], 0.5)), r.get("wc_pre") or 0.5, r.get("decline_ratio") or 1.0])
        d = float(np.sqrt(np.sum(((f - f0) * np.array([1.0, 2.0, 1.0])) ** 2)))
        if reason and r.get("estimated_reason") and r["estimated_reason"] != reason:
            d += 1.0
        rows.append({**r, "distance": d, "same_reason": bool(reason and r.get("estimated_reason") == reason)})
    rows.sort(key=lambda x: x["distance"])
    return rows[:k]


def _recovery_stats(analogs: list[dict]) -> dict | None:
    if len(analogs) < 4:
        return None
    ratios = np.array([a.get("recovery_ratio_own") if a.get("recovery_ratio_own") is not None else a["recovery_ratio"] for a in analogs if (a.get("recovery_ratio_own") is not None or a.get("recovery_ratio") is not None)], dtype=float)
    if len(ratios) < 4:
        return None
    sustained = np.mean([1.0 if a.get("sustained") else 0.0 for a in analogs])
    return {"p20": float(np.percentile(ratios, 20)), "p50": float(np.median(ratios)), "p80": float(np.percentile(ratios, 80)), "sustain_rate": float(sustained), "n": int(len(ratios))}


def screen(ctx, memory_rows: list[dict], progress=None) -> dict:
    s = ctx.settings
    econ_limit = 3.0
    idle = [w for w, r in ctx.status.iterrows() if r.status == "idle"]
    horizon = int(val(s["economics"]["horizon_months"]))
    rows, funnel = [], {"all_idle": len(idle), "sufficient_data": 0, "plausible": 0, "positive_value": 0, "fits_constraints": 0, "recommended": 0}
    for wid in idle:
        st = ctx.status.loc[wid]
        shutin_t = int(st.last_production_t) + 1
        prof = pre_shutin_profile(ctx, wid, shutin_t)
        dq = ctx.quality.loc[wid] if wid in ctx.quality.index else None
        row = {"well_id": wid, "field": str(ctx.ds.wells.set_index("well_id").loc[wid, "field"]), "last_production_month": ctx.ds.months[int(st.last_production_t)], "idle_months": int(st.idle_months),
               "last_oil_bpd": round(prof["last_rate_bpd"], 1), "historical_peak_bpd": round(prof["peak_bpd"], 1), "last_water_cut": None if prof["wc_last"] is None else round(prof["wc_last"], 3),
               "dq_score": float(dq.dq_score) if dq is not None else None, "safety_block": None}
        reasons = classify_reason(prof, econ_limit)
        row["reasons"] = reasons
        row["estimated_reason"] = reasons[0]["reason"] if reasons else "UNKNOWN"
        row["reason_quality"] = reasons[0]["evidence_quality"] if reasons else "UNVERIFIED"
        if prof["months_available"] < 6 or (dq is not None and dq.dq_score < 50):
            row.update({"status": "INSUFFICIENT DATA", "confidence": "INSUFFICIENT EVIDENCE", "why": ["fewer than 6 producing months before shut-in" if prof["months_available"] < 6 else "data quality below threshold"]})
            rows.append(row)
            continue
        funnel["sufficient_data"] += 1
        # undisturbed rate projected to today via decline fit on the pre-shut-in year
        fit = dc.fit_arps(np.array([v or 0 for v in prof["series"]]))
        months_since = ctx.ds.n_months - shutin_t
        if fit.get("ok"):
            proj = float(dc.extrapolate(fit, np.array([len(prof["series"]) - 1 + months_since]))[0])
            proj = min(max(proj, 0.0), prof["last_rate_bpd"] * 1.05)
        else:
            proj = prof["last_rate_bpd"] * max(0.3, 1 - 0.01 * months_since)
        analogs = analog_restarts(memory_rows, prof, reason=row["estimated_reason"])
        rec = _recovery_stats(analogs)
        row["analog_count"] = len(analogs)
        row["analogs_same_reason"] = sum(1 for a in analogs if a.get("same_reason"))
        row["analogs"] = [{"intervention_id": a["intervention_id"], "well_id": a["well_id"], "recovery_ratio": a.get("recovery_ratio_own"), "recovery_vs_baseline": a.get("recovery_ratio"), "sustained": a.get("sustained"), "causal_gain_bpd": a["causal_gain_bpd"], "same_reason": a.get("same_reason"), "estimated_reason": a.get("estimated_reason")} for a in analogs]
        row["projected_undisturbed_bpd"] = round(proj, 1)
        row["decline_fit"] = {"model": fit.get("model"), "r2": round(fit.get("r2", 0), 3), "poor_fit": fit.get("poor_fit")} if fit.get("ok") else {"model": None, "reason": fit.get("reason")}
        if rec is None:
            row.update({"status": "INSUFFICIENT DATA", "confidence": "INSUFFICIENT EVIDENCE", "why": [f"only {len(analogs)} comparable historical restarts (minimum 4)"]})
            rows.append(row)
            continue
        plausible = row["estimated_reason"] not in ("GEOLOGICAL",) or prof["last_rate_bpd"] > econ_limit
        if not plausible:
            row.update({"status": "DO NOT PRIORITISE", "confidence": "LOW CONFIDENCE", "why": ["depletion signature and rate below economic limit"]})
            rows.append(row)
            continue
        funnel["plausible"] += 1
        p50, p20, p80 = proj * rec["p50"], proj * rec["p20"], proj * rec["p80"]
        action = REASON_TO_ACTION.get(row["estimated_reason"], "restart")
        cost = val(economics.intervention_cost(s, action))
        handling = memory._handling(ctx, wid)
        wc_l = prof["wc_last"] if prof["wc_last"] is not None else 0.8
        water_bpd = p50 * wc_l / max(1 - wc_l, 0.02)
        econ = economics.evaluate(s, economics.decay_profile(p50, horizon, tau=36), [water_bpd] * horizon, cost, handling=handling, success_probability=rec["sustain_rate"], label=action)
        econ_lo = economics.evaluate(s, economics.decay_profile(p20, horizon, tau=36), [p20 * wc_l / max(1 - wc_l, 0.02)] * horizon, cost, handling=handling, success_probability=rec["sustain_rate"])
        econ_hi = economics.evaluate(s, economics.decay_profile(p80, horizon, tau=36), [p80 * wc_l / max(1 - wc_l, 0.02)] * horizon, cost, handling=handling, success_probability=rec["sustain_rate"])
        spread = (p80 / max(p20, 0.1))
        mean_dist = float(np.mean([a["distance"] for a in analogs])) if analogs else 9.9
        conf = "HIGH CONFIDENCE" if (rec["n"] >= 6 and spread < 2.0 and mean_dist < 1.05 and row["analogs_same_reason"] >= 4 and rec["sustain_rate"] >= 0.7 and (dq is None or dq.dq_score >= 80) and row["reason_quality"] == "STRONG INFERENCE") else "MODERATE CONFIDENCE" if rec["n"] >= 4 and spread < 3.5 and mean_dist < 1.2 else "LOW CONFIDENCE"
        row["analog_mean_distance"] = round(mean_dist, 3)
        row.update({"restart_probability": round(rec["sustain_rate"], 2), "expected_oil_bpd": round(p50, 1), "expected_oil_lo": round(p20, 1), "expected_oil_hi": round(p80, 1), "expected_water_bpd": round(water_bpd, 1),
                    "intervention_type": action, "intervention_cost": cost, "expected_npv": econ["npv"], "npv_lo": econ_lo["npv"], "npv_hi": econ_hi["npv"], "payback_months": econ["payback_months"], "confidence": conf,
                    "economics": econ})
        if econ["npv"] <= 0:
            row.update({"status": "DO NOT PRIORITISE" if econ_hi["npv"] <= 0 else "WAIT", "why": ["expected NPV not positive under current assumptions"]})
            rows.append(row)
            continue
        funnel["positive_value"] += 1
        min_npv = val(s["portfolio"]["min_npv"])
        if econ["npv"] < min_npv:
            row.update({"status": "WAIT", "why": [f"NPV below configured minimum {min_npv:,.0f}"]})
            rows.append(row)
            continue
        funnel["fits_constraints"] += 1
        if spread >= 3.0 and econ_lo["npv"] < 0:
            row["status"] = "TEST"
            row["why"] = [f"outcome range {p20:.0f}–{p80:.0f} bbl/d is wide; a diagnostic test before committing {cost:,.0f} is worth it"]
        elif conf == "HIGH CONFIDENCE":
            row["status"] = "ACT"
            row["why"] = [f"{rec['n']} comparable restarts recovered a median {rec['p50']:.0%} of projected rate", f"expected NPV {econ['npv']:,.0f} with {rec['sustain_rate']:.0%} of analogues sustaining"]
        else:
            row["status"] = "REVIEW"
            row["why"] = [f"positive expected value ({econ['npv']:,.0f}) with {conf.lower()}", f"{rec['n']} comparable restarts"]
        funnel["recommended"] += 1
        rows.append(row)
    order = {"ACT": 0, "TEST": 1, "REVIEW": 2, "WAIT": 3, "DO NOT PRIORITISE": 4, "INSUFFICIENT DATA": 5}
    rows.sort(key=lambda r: (order.get(r["status"], 9), -(r.get("expected_npv") or -1e12)))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return {"funnel": funnel, "rows": rows, "assumptions": {"economic_limit_bpd": {"value": econ_limit, "source": "PUBLIC ASSUMPTION"}, "note": "Costs, prices and facility capacities are illustrative in demo mode."}}


def scenarios(ctx, row: dict, memory_rows: list[dict]) -> list[dict]:
    """Reactivation scenarios priced from the intervention memory by type. No evidence → INSUFFICIENT EVIDENCE."""
    s = ctx.settings
    horizon = int(val(s["economics"]["horizon_months"]))
    base = row.get("expected_oil_bpd") or 0.0
    proj = row.get("projected_undisturbed_bpd") or 0.0
    wc_l = row.get("last_water_cut") if row.get("last_water_cut") is not None else 0.8
    handling = memory._handling(ctx, row["well_id"])
    out = [{"scenario": "do_nothing", "label": "Do nothing", "oil_bpd": 0.0, "oil_lo": 0.0, "oil_hi": 0.0, "water_bpd": 0.0, "cost": 0.0, "duration_months": 0, "success_probability": 1.0, "npv": 0.0, "payback_months": None, "evidence": "baseline", "status": "OK"}]
    for sc in SCENARIOS[1:]:
        ev = memory.type_evidence(memory_rows, sc if sc != "restart" else "restart")
        if sc == "restart":
            ev_r = memory.type_evidence(memory_rows, "observed_restart")
            if ev["n"] + ev_r["n"] == 0:
                out.append({"scenario": sc, "label": sc.replace("_", " "), "status": "INSUFFICIENT EVIDENCE", "evidence": "no historical restarts"})
                continue
            uplift_ratio = 0.0
            oil, lo, hi = base, row.get("expected_oil_lo", base * 0.6), row.get("expected_oil_hi", base * 1.3)
            p = row.get("restart_probability", 0.7)
            n_ev = ev["n"] + ev_r["n"]
        else:
            if ev["n"] < 3:
                out.append({"scenario": sc, "label": sc.replace("_", " "), "status": "INSUFFICIENT EVIDENCE", "evidence": f"{ev['n']} historical {sc.replace('_', ' ')} jobs with complete analysis (minimum 3)"})
                continue
            # restart gives 'base'; the downhole job adds its historical causal effect ratio on top of the projected undisturbed rate
            oil = base + proj * ev["median_effect_ratio"]
            lo = row.get("expected_oil_lo", base * 0.6) + proj * ev["p20_ratio"]
            hi = row.get("expected_oil_hi", base * 1.3) + proj * ev["p80_ratio"]
            p = min(0.95, max(0.2, row.get("restart_probability", 0.7) * ev["positive_effect_rate"] / max(ev["positive_effect_rate"], 0.5)))
            n_ev = ev["n"]
        cost = val(economics.intervention_cost(s, sc)) or 0.0
        water_bpd = oil * wc_l / max(1 - wc_l, 0.02)
        if sc == "water_shutoff" and ev.get("median_water_change_bpd") is not None:
            water_bpd = max(0.0, water_bpd + ev["median_water_change_bpd"])
        econ = economics.evaluate(s, economics.decay_profile(oil, horizon, tau=36), [water_bpd] * horizon, cost, handling=handling, success_probability=p, label=sc)
        econ_lo = economics.evaluate(s, economics.decay_profile(lo, horizon, tau=36), [water_bpd] * horizon, cost, handling=handling, success_probability=p)
        econ_hi = economics.evaluate(s, economics.decay_profile(hi, horizon, tau=36), [water_bpd] * horizon, cost, handling=handling, success_probability=p)
        out.append({"scenario": sc, "label": sc.replace("_", " "), "oil_bpd": round(oil, 1), "oil_lo": round(lo, 1), "oil_hi": round(hi, 1), "water_bpd": round(water_bpd, 1), "cost": cost,
                    "duration_months": s["economics"]["intervention_duration_months"].get(sc, 1.0), "success_probability": round(p, 2), "npv": econ["npv"], "npv_lo": econ_lo["npv"], "npv_hi": econ_hi["npv"],
                    "payback_months": econ["payback_months"], "evidence": f"{n_ev} historical events", "status": "OK", "economics": econ})
    return out
