"""Economic engine. Every output carries a provenance block: formula, inputs, sources."""
from __future__ import annotations

import numpy as np

from ..config import CALCULATED, MODEL_ESTIMATE, OPERATOR_DATA_REQUIRED, val


def netback(settings: dict) -> dict:
    e = settings["economics"]
    price, roy, lift = val(e["oil_price"]), val(e["royalty_rate"]), val(e["lifting_cost"])
    nb = price * (1 - roy) - lift
    return {"value": round(nb, 2), "unit": "$/bbl", "source": CALCULATED, "formula": "oil_price × (1 − royalty_rate) − lifting_cost",
            "inputs": {"oil_price": e["oil_price"], "royalty_rate": e["royalty_rate"], "lifting_cost": e["lifting_cost"]}}


def water_unit_cost(settings: dict, handling: str = "disposal") -> dict:
    w = settings["economics"]["water"]
    comps = {}
    for k in ("lift_energy", "separation", "treatment", "chemicals", "transport"):
        comps[k] = w[k]
    comps["disposal" if handling == "disposal" else "reinjection"] = w["disposal" if handling == "disposal" else "reinjection"]
    comps["corrosion_scale"] = w["corrosion_scale"]
    included = {k: v for k, v in comps.items() if val(v) is not None}
    excluded = [k for k, v in comps.items() if val(v) is None]
    total = float(sum(val(v) for v in included.values()))
    return {"value": round(total, 3), "unit": "$/bbl water", "source": CALCULATED, "formula": "sum of included component costs", "components": comps,
            "excluded": excluded, "note": ("Components marked OPERATOR DATA REQUIRED are excluded: " + ", ".join(excluded)) if excluded else ""}


def shadow_cost(settings: dict, utilisation: float, oil_fraction_marginal: float) -> dict:
    """Capacity shadow cost per bbl of water when a facility is near its fluid limit."""
    thr = val(settings["economics"]["water"]["capacity_threshold"])
    nb = netback(settings)["value"]
    active = utilisation >= thr
    value = nb * oil_fraction_marginal if active else 0.0
    return {"value": round(value, 3), "unit": "$/bbl water", "source": MODEL_ESTIMATE, "active": bool(active), "utilisation": round(float(utilisation), 3), "threshold": thr,
            "formula": "if utilisation ≥ threshold: netback × oil fraction of the marginal barrel of fluid displaced, else 0",
            "note": "Facility capacities are illustrative in demo mode (OPERATOR DATA REQUIRED)."}


def evaluate(settings: dict, oil_bpd_series: list[float], water_bpd_change_series: list[float], cost: float, days: list[float] | None = None,
             handling: str = "disposal", success_probability: float = 1.0, label: str = "") -> dict:
    """Monthly cash-flow valuation of an incremental oil (and water change) profile.

    oil_bpd_series: incremental oil per month (bbl/day, positive = more oil)
    water_bpd_change_series: change in produced water per month (bbl/day, positive = more water)
    """
    e = settings["economics"]
    nb = netback(settings)["value"]
    wc = water_unit_cost(settings, handling)["value"]
    r_m = (1 + val(e["discount_rate"])) ** (1 / 12) - 1
    n = len(oil_bpd_series)
    days = days or [30.4] * n
    cash = []
    for t in range(n):
        o = (oil_bpd_series[t] or 0.0) * days[t]
        w = (water_bpd_change_series[t] if t < len(water_bpd_change_series) and water_bpd_change_series[t] is not None else 0.0) * days[t]
        cash.append(o * nb - w * wc)
    disc = [c / (1 + r_m) ** (t + 1) for t, c in enumerate(cash)]
    npv_success = -cost + float(np.sum(disc))
    npv = -cost + success_probability * float(np.sum(disc))
    cum = np.cumsum(cash)
    payback = next((t + 1 for t, c in enumerate(cum) if c >= cost), None)
    return {
        "label": label, "cost": round(cost, 0), "npv": round(npv, 0), "npv_if_success": round(npv_success, 0), "gross_value": round(float(np.sum(cash)), 0),
        "payback_months": payback, "success_probability": round(success_probability, 3), "incremental_oil_bbl": round(float(sum((oil_bpd_series[t] or 0.0) * days[t] for t in range(n))), 0),
        "water_change_bbl": round(float(sum(((water_bpd_change_series[t] or 0.0) if t < len(water_bpd_change_series) else 0.0) * days[t] for t in range(n))), 0),
        "provenance": {"formula": "NPV = −cost + p_success × Σ_t (oil_t × netback − Δwater_t × water_cost) / (1+r_m)^t", "netback": netback(settings), "water_unit_cost": water_unit_cost(settings, handling),
                        "discount_rate": e["discount_rate"], "horizon_months": n, "cost_source": "ILLUSTRATIVE ECONOMIC ASSUMPTION" if cost else CALCULATED},
    }


def decay_profile(mean_bpd: float, months: int, tau: float = 18.0) -> list[float]:
    """Spread a mean effect over a horizon with exponential decay (mean preserved)."""
    if months <= 0:
        return []
    w = np.exp(-np.arange(months) / tau)
    w = w / w.mean()
    return [float(mean_bpd * x) for x in w]


def intervention_cost(settings: dict, itype: str) -> dict:
    c = settings["economics"]["intervention_costs"].get(itype)
    if c is None:
        return {"value": None, "source": OPERATOR_DATA_REQUIRED, "unit": "$"}
    return c
