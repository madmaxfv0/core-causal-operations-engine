"""M5 — Portfolio planner: constrained optimisation (PuLP/CBC), not an LLM."""
from __future__ import annotations

import pulp

from ..config import val
from . import economics

OBJECTIVES = ["npv", "oil", "cash", "water", "balanced", "custom"]
RIG_JOBS = {"workover", "stimulation", "water_shutoff"}


def candidates(idle_rows: list[dict], ghost_rows: list[dict], water_rows: list[dict], settings: dict, manual: list[dict] | None = None) -> list[dict]:
    out = []
    dur = settings["economics"]["intervention_duration_months"]
    horizon = int(val(settings["economics"]["horizon_months"]))
    for r in idle_rows:
        if r.get("status") in ("ACT", "TEST", "REVIEW"):
            act = r["intervention_type"]
            job_type = "diagnostic_test" if r["status"] == "TEST" else act
            cost = val(economics.intervention_cost(settings, job_type)) or 0.0
            # re-price under the *current* settings so budget/price/cost changes genuinely flow through
            p_s = float(r.get("restart_probability") or 0.6)
            oil = float(r.get("expected_oil_bpd") or 0.0)
            wat = float(r.get("expected_water_bpd") or 0.0)
            econ = economics.evaluate(settings, economics.decay_profile(oil, horizon, tau=36), [wat] * horizon, cost, success_probability=p_s)
            econ_lo = economics.evaluate(settings, economics.decay_profile(float(r.get("expected_oil_lo") or 0.0), horizon, tau=36), [wat] * horizon, cost, success_probability=p_s)
            econ_hi = economics.evaluate(settings, economics.decay_profile(float(r.get("expected_oil_hi") or 0.0), horizon, tau=36), [wat] * horizon, cost, success_probability=p_s)
            npv = econ["npv"] if r["status"] != "TEST" else max(0.0, 0.25 * econ["npv"])  # value of information proxy, illustrative
            r = {**r, "npv_lo": econ_lo["npv"], "npv_hi": econ_hi["npv"]}
            out.append({"candidate_id": f"IDLE-{r['well_id']}", "well_id": r["well_id"], "module": "idle", "action": job_type, "label": f"{job_type.replace('_', ' ')} on {r['well_id']}",
                        "cost": float(cost), "npv": float(npv), "npv_lo": float(r.get("npv_lo") or 0), "npv_hi": float(r.get("npv_hi") or 0), "oil_bpd": float(r["expected_oil_bpd"]) if r["status"] != "TEST" else 0.0,
                        "water_bpd": 0.0, "duration_months": float(dur.get(job_type, 1.0)), "crew_type": "rig" if job_type in RIG_JOBS else "rigless", "risk": round(1 - float(r.get("restart_probability") or 0.5), 2),
                        "confidence": r["confidence"], "status": r["status"], "safety_block": r.get("safety_block")})
    for r in ghost_rows:
        if r.get("is_opportunity"):
            d = r.get("decomposition") or {}
            drv = d.get("probable_driver", "")
            act = "water_shutoff" if "Water" in drv else "pump_optimisation" if ("hours" in drv.lower() or "downtime" in drv.lower()) else "diagnostic_test"
            cost = val(economics.intervention_cost(settings, act)) or 0.0
            oil = r["oil_opportunity_bpd"] * (0.6 if act != "diagnostic_test" else 0.0)
            horizon = int(val(settings["economics"]["horizon_months"]))
            econ = economics.evaluate(settings, economics.decay_profile(oil, horizon), [0.0] * horizon, cost, success_probability=0.6 if act != "diagnostic_test" else 1.0)
            npv = econ["npv"] if act != "diagnostic_test" else max(0.0, 0.15 * r["annual_value"] - cost)
            out.append({"candidate_id": f"GHOST-{r['well_id']}", "well_id": r["well_id"], "module": "ghost", "action": act, "label": f"{act.replace('_', ' ')} on {r['well_id']}", "cost": float(cost), "npv": float(npv),
                        "npv_lo": float(npv * 0.4), "npv_hi": float(npv * 1.5), "oil_bpd": float(oil), "water_bpd": 0.0, "duration_months": float(dur.get(act, 0.5)), "crew_type": "rig" if act in RIG_JOBS else "rigless",
                        "risk": 0.4, "confidence": r["confidence"], "status": "REVIEW", "safety_block": None})
    for r in water_rows:
        if r.get("potential_intervention") and r.get("expected_value") is not None and f"GHOST-{r['well_id']}" not in {c["candidate_id"] for c in out}:
            cost = val(economics.intervention_cost(settings, "water_shutoff"))
            out.append({"candidate_id": f"WATER-{r['well_id']}", "well_id": r["well_id"], "module": "water", "action": "water_shutoff", "label": f"water shutoff on {r['well_id']}", "cost": float(cost), "npv": float(r["expected_value"]),
                        "npv_lo": float(r["expected_value"] * 0.3), "npv_hi": float(r["expected_value"] * 1.4), "oil_bpd": 0.0, "water_bpd": float(r.get("water_avoided_bpd") or 0.0), "duration_months": float(dur.get("water_shutoff", 1.0)),
                        "crew_type": "rig", "risk": 0.45, "confidence": "MODERATE CONFIDENCE", "status": "REVIEW", "safety_block": None})
    for m in manual or []:
        out.append({**m, "module": "manual", "candidate_id": m.get("candidate_id") or f"MANUAL-{m['well_id']}-{m['action']}", "label": m.get("label") or f"{m['action']} on {m['well_id']} (manual)"})
    return out


def optimise(cands: list[dict], constraints: dict, objective: str = "npv", weights: dict | None = None, locked: dict | None = None, removed: set | None = None) -> dict:
    """MILP: choose jobs and start quarters. locked: {candidate_id: quarter or None}."""
    locked = locked or {}
    removed = removed or set()
    budget = float(constraints.get("budget", 1e6))
    crews = int(constraints.get("crews", 2))
    rigs = int(constraints.get("rigs", 1))
    horizon = int(constraints.get("horizon_months", 12))
    Q = max(1, horizon // 3)
    max_conc = int(constraints.get("max_concurrent", 3))
    min_npv = float(constraints.get("min_npv", 0))
    risk_tol = float(constraints.get("risk_tolerance", 0.6))
    eligible, excluded = [], []
    for c in cands:
        if c["candidate_id"] in removed:
            excluded.append({**c, "excluded_reason": "removed by user"})
        elif c.get("safety_block"):
            excluded.append({**c, "excluded_reason": f"SAFETY BLOCK: {c['safety_block']}"})
        elif c["candidate_id"] not in locked and c["npv"] < min_npv:
            excluded.append({**c, "excluded_reason": f"NPV below minimum {min_npv:,.0f}"})
        elif c["candidate_id"] not in locked and c["risk"] > risk_tol:
            excluded.append({**c, "excluded_reason": f"risk {c['risk']:.2f} above tolerance {risk_tol:.2f}"})
        else:
            eligible.append(c)
    prob = pulp.LpProblem("core_portfolio", pulp.LpMaximize)
    x = {(c["candidate_id"], q): pulp.LpVariable(f"x_{i}_{q}", cat="Binary") for i, c in enumerate(eligible) for q in range(Q)}
    w = weights or {}
    scale = {"npv": max(1.0, max((abs(c["npv"]) for c in eligible), default=1.0)), "oil": max(1.0, max((c["oil_bpd"] for c in eligible), default=1.0)), "water": max(1.0, max((c["water_bpd"] for c in eligible), default=1.0))}

    def score(c):
        if objective == "npv":
            return c["npv"]
        if objective == "oil":
            return c["oil_bpd"] * 1000 + c["npv"] * 1e-3
        if objective == "cash":
            return (c["npv"] + c["cost"]) / max(1.0, c["duration_months"] + 1)  # front-loaded gross value proxy
        if objective == "water":
            return c["water_bpd"] * 1000 + c["npv"] * 1e-3
        if objective == "balanced":
            return 1e5 * (0.5 * c["npv"] / scale["npv"] + 0.3 * c["oil_bpd"] / scale["oil"] + 0.2 * c["water_bpd"] / scale["water"])
        return 1e5 * (w.get("economic", 0.4) * c["npv"] / scale["npv"] + w.get("production", 0.2) * c["oil_bpd"] / scale["oil"] + w.get("water", 0.1) * c["water_bpd"] / scale["water"]
                      + w.get("confidence", 0.2) * (1 - c["risk"]) + w.get("urgency", 0.1) * (1.0 if c["status"] == "ACT" else 0.5))

    prob += pulp.lpSum(score(c) * x[(c["candidate_id"], q)] + 1e-3 * (Q - q) * x[(c["candidate_id"], q)] for c in eligible for q in range(Q))
    for c in eligible:
        prob += pulp.lpSum(x[(c["candidate_id"], q)] for q in range(Q)) <= 1
    prob += pulp.lpSum(c["cost"] * x[(c["candidate_id"], q)] for c in eligible for q in range(Q)) <= budget
    for q in range(Q):
        prob += pulp.lpSum(x[(c["candidate_id"], q)] for c in eligible) <= max_conc
        prob += pulp.lpSum((c["duration_months"] / 3.0) * x[(c["candidate_id"], q)] for c in eligible if c["crew_type"] == "rig") <= rigs
        prob += pulp.lpSum((c["duration_months"] / 3.0) * x[(c["candidate_id"], q)] for c in eligible if c["crew_type"] == "rigless") <= crews
    for cid, q in locked.items():
        if any(c["candidate_id"] == cid for c in eligible):
            if q is None:
                prob += pulp.lpSum(x[(cid, qq)] for qq in range(Q)) == 1
            else:
                prob += x[(cid, min(int(q), Q - 1))] == 1
    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=20))
    selected = []
    for c in eligible:
        for q in range(Q):
            v = x[(c["candidate_id"], q)].value()
            if v is not None and v > 0.5:
                selected.append({**c, "quarter": q, "locked": c["candidate_id"] in locked})
    selected.sort(key=lambda r: (r["quarter"], -r["npv"]))
    rig_used = sum(c["duration_months"] / 3.0 for c in selected if c["crew_type"] == "rig")
    crew_used = sum(c["duration_months"] / 3.0 for c in selected if c["crew_type"] == "rigless")
    avoided = [c for c in cands if c["npv"] <= 0 and c["candidate_id"] not in {s["candidate_id"] for s in selected}]
    return {"status": pulp.LpStatus[status], "objective": objective, "quarters": Q, "selected": selected, "excluded": excluded, "not_selected": [c for c in eligible if c["candidate_id"] not in {s["candidate_id"] for s in selected}],
            "kpi": {"available": len(cands), "eligible": len(eligible), "total_candidate_cost": sum(c["cost"] for c in cands), "budget": budget, "selected": len(selected), "investment": sum(c["cost"] for c in selected),
                    "expected_oil_bpd": round(sum(c["oil_bpd"] for c in selected), 1), "expected_water_reduction_bpd": round(sum(c["water_bpd"] for c in selected), 1), "expected_value": round(sum(c["npv"] for c in selected), 0),
                    "value_lo": round(sum(c["npv_lo"] for c in selected), 0), "value_hi": round(sum(c["npv_hi"] for c in selected), 0), "avoided_poor_spend": round(sum(c["cost"] for c in avoided), 0),
                    "rig_utilisation": round(rig_used / max(rigs * Q, 1e-6), 3), "crew_utilisation": round(crew_used / max(crews * Q, 1e-6), 3), "downside_risk": round(sum(c["risk"] * c["cost"] for c in selected), 0)}}


def baseline_plan(cands: list[dict], budget: float, rule: str = "highest_previous_production") -> dict:
    """Transparent baseline rules — never an invented 'engineer plan'."""
    ranked = list(cands)
    if rule == "highest_previous_production":
        ranked.sort(key=lambda c: -(c.get("oil_bpd") or 0))
    elif rule == "lowest_cost_first":
        ranked.sort(key=lambda c: c["cost"])
    elif rule == "naive_npv":
        ranked.sort(key=lambda c: -(c.get("naive_npv") if c.get("naive_npv") is not None else c["npv"]))
    spent, chosen = 0.0, []
    for c in ranked:
        if spent + c["cost"] <= budget:
            chosen.append(c)
            spent += c["cost"]
    return {"rule": rule, "selected": chosen, "kpi": {"selected": len(chosen), "investment": spent, "expected_oil_bpd": round(sum(c["oil_bpd"] for c in chosen), 1), "expected_water_reduction_bpd": round(sum(c["water_bpd"] for c in chosen), 1),
                                                       "expected_value": round(sum(c["npv"] for c in chosen), 0), "downside_risk": round(sum(c["risk"] * c["cost"] for c in chosen), 0), "bad_job_exposure": round(sum(c["cost"] for c in chosen if c["npv"] <= 0), 0)}}


def sensitivity(ctx_settings: dict, cands: list[dict], constraints: dict, objective: str, recompute) -> list[dict]:
    """Tornado: re-run the optimiser under perturbed economic assumptions. `recompute(settings) -> cands`."""
    import copy
    base = optimise(cands, constraints, objective)["kpi"]["expected_value"]
    rows = []
    for name, path, lo, hi in (("Oil price", ["economics", "oil_price", "value"], 0.7, 1.3), ("Intervention cost", ["economics", "intervention_costs"], 0.7, 1.3), ("Discount rate", ["economics", "discount_rate", "value"], 0.5, 1.5), ("Water disposal cost", ["economics", "water", "disposal", "value"], 0.5, 2.0)):
        vals = []
        for f in (lo, hi):
            s = copy.deepcopy(ctx_settings)
            node = s
            for k in path[:-1]:
                node = node[k]
            if path[-1] == "intervention_costs":
                for k in node["intervention_costs"]:
                    node["intervention_costs"][k]["value"] = node["intervention_costs"][k]["value"] * f
            else:
                node[path[-1]] = node[path[-1]] * f
            vals.append(optimise(recompute(s), constraints, objective)["kpi"]["expected_value"])
        rows.append({"factor": name, "low": vals[0], "high": vals[1], "base": base, "range": [lo, hi]})
    rows.sort(key=lambda r: -abs(r["high"] - r["low"]))
    return rows
