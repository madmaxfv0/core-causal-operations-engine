"""Synthetic mature-field generator.

Everything produced here is labelled SYNTHETIC — FOR METHOD VALIDATION. It exists so that CORE can be
tested against a *known* truth: every planted intervention effect and every shut-in reason is recorded in
truth tables that the analysis layer never reads.

Design choices that matter for the method demonstration:
- Wells share field-level shocks (so donor-based counterfactuals beat pure decline curves).
- Interventions are triggered by a *transient* production dip that partially recovers on its own —
  the mean-reversion trap that makes naive before/after estimates overstate value.
- Some interventions have zero or negative true effect.
- Restart events (shut-in then resumed) are generated separately from intervention records; only some
  restarts carry an explicit intervention record, mirroring real archives.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import M3_TO_BBL

INTERVENTION_TYPES = ["pump_replacement", "cleanout", "water_shutoff", "stimulation", "workover"]
BASE_COST = {"pump_replacement": 45000, "cleanout": 30000, "water_shutoff": 120000, "stimulation": 150000, "workover": 200000, "restart": 25000}
SHUTIN_REASONS = ["WATER-RELATED", "MECHANICAL", "ECONOMIC", "GEOLOGICAL", "OPERATIONAL"]


def _ar1(rng, n, phi, sigma):
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + rng.normal(0, sigma)
    return x


def _arps(qi, di, b, t):
    t = np.asarray(t, dtype=float)
    if b < 1e-3:
        return qi * np.exp(-di * t)
    return qi / np.power(1.0 + b * di * t, 1.0 / b)


def generate(seed: int = 42, n_wells: int = 180, n_months: int = 84, start: str = "2019-01") -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    months = pd.period_range(start, periods=n_months, freq="M")
    month_str = [str(p) for p in months]
    days = np.array([p.days_in_month for p in months], dtype=float)
    fields = ["Synthetic Field A", "Synthetic Field B", "Synthetic Field C"]
    pools = {f: [f"{f[-1]}-Pool-{i}" for i in (1, 2)] for f in fields}
    facilities = pd.DataFrame({
        "facility_id": [f"FAC-{i:02d}" for i in range(1, 7)],
        "field": [fields[i % 3] for i in range(6)],
        "fluid_capacity_bpd": [9000, 6500, 8000, 5500, 7000, 6000],
        "water_handling": ["disposal", "reinjection", "disposal", "reinjection", "disposal", "reinjection"],
    })
    field_shock = {f: _ar1(rng, n_months, 0.8, 0.09) for f in fields}
    seasonal = 0.04 * np.sin(2 * np.pi * np.arange(n_months) / 12.0)

    wells, prod_rows, interventions, truth_events, truth_monthly = [], [], [], [], []

    # Role assignment
    idx = np.arange(n_wells)
    rng.shuffle(idx)
    n_int, n_restart, n_idle = 45, 40, 45
    roles = {}
    for i in idx[:n_int]:
        roles[i] = "intervention"
    for i in idx[n_int:n_int + n_restart]:
        roles[i] = "restart"
    for i in idx[n_int + n_restart:n_int + n_restart + n_idle]:
        roles[i] = "idle"
    for i in idx[n_int + n_restart + n_idle:]:
        roles[i] = "producer"
    restart_ids = [i for i in idx[n_int:n_int + n_restart]]
    blind_forced = set(restart_ids[:18])  # guarantee restarts after the blind-test cut-off (t=60)

    for i in range(n_wells):
        wid = f"SYN-{i + 1:03d}"
        field = fields[i % 3]
        pool = pools[field][(i // 3) % 2]
        fac = facilities[facilities.field == field].facility_id.tolist()
        facility = fac[(i // 3) % len(fac)]
        spud_year = int(rng.integers(1978, 2015))
        qi = float(np.clip(rng.lognormal(np.log(230), 0.65), 30, 1500))  # m3/month at t=0
        di = float(rng.uniform(0.008, 0.03))
        b = float(rng.uniform(0.3, 0.9))
        wc0 = float(rng.uniform(0.30, 0.78))
        wc_inf = float(rng.uniform(wc0 + 0.05, 0.97))
        kw = float(rng.uniform(0.01, 0.04))
        gor = float(rng.uniform(0.05, 0.3))
        lift = rng.choice(["rod_pump", "esp", "pcp", "gas_lift"], p=[0.55, 0.25, 0.12, 0.08])
        t = np.arange(n_months)
        base = _arps(qi, di, b, t)
        noise = _ar1(rng, n_months, 0.4, 0.05)
        mult = np.exp(field_shock[field] + noise + seasonal)
        hours = np.full(n_months, 720.0)
        down = rng.random(n_months) < 0.08
        hours[down] = rng.uniform(300, 700, down.sum())
        wc = wc_inf - (wc_inf - wc0) * np.exp(-kw * t)
        cf_oil = base * mult * hours / 720.0  # counterfactual (no event) oil m3/month
        actual = cf_oil.copy()
        role = roles[i]
        status_series = np.array(["producing"] * n_months, dtype=object)
        shutin_reason, shutin_t, restart_t = None, None, None

        if role == "intervention":
            # interventions tend to be scheduled when the field is having a bad month (curtailment, weather,
            # facility limits) — so the whole field "recovers" afterwards and before/after gets the credit.
            cand = np.arange(24, 67)
            fs = field_shock[field][cand]
            low = cand[fs <= np.quantile(fs, 0.3)]
            e = int(rng.choice(low)) if rng.random() < 0.7 else int(rng.integers(24, 67))
            itype = INTERVENTION_TYPES[int(rng.integers(0, len(INTERVENTION_TYPES)))]
            dip = np.ones(n_months)
            pre_dip = [0.90, 0.82, 0.72]
            for k, m in enumerate(pre_dip):
                if e - 3 + k >= 0:
                    dip[e - 3 + k] = m
            r_inf = float(rng.uniform(0.88, 1.0))  # without intervention the dip mostly heals
            recov = [0.85, 0.95]
            for k in range(e, n_months):
                dip[k] = min(recov[k - e], r_inf) if k - e < len(recov) else r_inf
            cf_oil = cf_oil * dip
            actual = cf_oil.copy()
            u = rng.random()
            if u < 0.30:
                E = 0.0
            elif u < 0.90:
                E = float(rng.uniform(0.25, 0.90)) if itype in ("workover", "stimulation", "water_shutoff") else float(rng.uniform(0.15, 0.60))
            else:
                E = float(rng.uniform(-0.20, -0.05))
            tau = float(rng.uniform(8, 30))
            eff = np.zeros(n_months)
            for tt in range(e, n_months):
                eff[tt] = E * np.exp(-(tt - e) / tau)
            actual = cf_oil * (1 + eff)
            if itype == "water_shutoff" and E > 0:
                wc_after = wc.copy()
                wc_after[e:] = np.clip(wc[e:] - 0.10 * np.exp(-(np.arange(n_months - e)) / tau), 0.05, 0.99)
                wc_actual = wc_after
            else:
                wc_actual = wc.copy()
            cost = BASE_COST[itype] * float(rng.uniform(0.75, 1.25))
            interventions.append({"intervention_id": f"INT-{len(interventions) + 1:03d}", "well_id": wid, "date": month_str[e],
                                  "t": e, "type": itype, "cost": round(cost, -2), "duration_months": 0.5 if itype in ("pump_replacement", "cleanout") else 1.0,
                                  "source": "SYNTHETIC RECORD", "confidence": "CONFIRMED", "kind": "intervention"})
            post = slice(e, min(e + 12, n_months))
            true_eff_bpd = float(np.mean((actual[post] - cf_oil[post]) * M3_TO_BBL / days[post]))
            truth_events.append({"well_id": wid, "event_t": e, "kind": "intervention", "type": itype, "true_effect_bpd_12m": true_eff_bpd,
                                 "true_effect_fraction": E, "tau": tau})
        else:
            wc_actual = wc.copy()

        if role in ("restart", "idle"):
            if role == "restart":
                if i in blind_forced:
                    s = int(rng.integers(44, 58))
                    d = int(rng.integers(3, min(14, 72 - s)))
                else:
                    s = int(rng.integers(12, 58))
                    d = int(rng.integers(3, 19))
                r = s + d
            else:
                s = int(rng.integers(30, 79))
                r = None
            reason = SHUTIN_REASONS[int(rng.integers(0, len(SHUTIN_REASONS)))]
            # imprint a reason signature on the months before shut-in
            if reason == "WATER-RELATED":
                ramp = np.linspace(0, 1, 8)
                for k in range(8):
                    tt = s - 8 + k
                    if tt >= 0:
                        wc_actual[tt] = min(0.985, wc_actual[tt] + (0.985 - wc_actual[tt]) * ramp[k])
                        cf_oil[tt] = cf_oil[tt] * (1 - 0.55 * ramp[k])
                wc_actual[s:] = np.minimum(0.985, wc_actual[s:] + (0.985 - wc_actual[s:]) * 0.9)
                cf_oil[s:] = cf_oil[s:] * 0.45
            elif reason == "MECHANICAL":
                if s - 1 >= 0:
                    hours[s - 1] = rng.uniform(120, 360)
                    cf_oil[s - 1] *= hours[s - 1] / 720.0 * 0.6
            elif reason == "ECONOMIC":
                k0 = max(0, s - 36)
                cf_oil[k0:s] = cf_oil[k0:s] * np.linspace(1, 0.10, s - k0)
                cf_oil[s:] = cf_oil[s:] * 0.10
            elif reason == "GEOLOGICAL":
                k0 = max(0, s - 24)
                cf_oil[k0:s] = cf_oil[k0:s] * np.linspace(1, 0.40, s - k0)
                cf_oil[s:] = cf_oil[s:] * 0.40
            actual = cf_oil.copy()
            cf_continue = cf_oil.copy()
            actual[s:] = 0.0
            hours_actual = hours.copy()
            hours_actual[s:] = 0.0
            status_series[s:] = "idle"
            shutin_reason, shutin_t = reason, s
            if r is not None and r < n_months:
                R = float(np.clip(rng.normal({"MECHANICAL": 1.05, "WATER-RELATED": 0.7, "ECONOMIC": 0.75, "GEOLOGICAL": 0.65, "OPERATIONAL": 0.95}[reason], 0.15), 0.2, 1.3))
                sustained = rng.random() > 0.2
                end = n_months if sustained else min(n_months, r + int(rng.integers(2, 6)))
                for tt in range(r, end):
                    hours_actual[tt] = hours[tt]
                    ramp = min(1.0, 0.7 + 0.1 * (tt - r))
                    actual[tt] = cf_continue[tt] * R * ramp
                    status_series[tt] = "producing"
                if end < n_months:
                    status_series[end:] = "idle"
                restart_t = r
                post = slice(r, min(r + 6, n_months))
                truth_events.append({"well_id": wid, "event_t": r, "kind": "restart", "type": "restart", "shutin_t": s,
                                     "true_recovery_ratio": R, "sustained": sustained, "true_reason": reason,
                                     "true_effect_bpd_12m": float(np.mean((actual[post] - cf_continue[post]) * M3_TO_BBL / days[post]))})
                if rng.random() < 0.5:
                    interventions.append({"intervention_id": f"INT-{len(interventions) + 1:03d}", "well_id": wid, "date": month_str[r], "t": r,
                                          "type": "workover" if reason == "MECHANICAL" else "restart", "cost": round(BASE_COST["workover" if reason == "MECHANICAL" else "restart"] * float(rng.uniform(0.8, 1.2)), -2),
                                          "duration_months": 1.0, "source": "SYNTHETIC RECORD", "confidence": "CONFIRMED", "kind": "intervention"})
            else:
                truth_events.append({"well_id": wid, "event_t": s, "kind": "shutin", "type": "shutin", "shutin_t": s, "true_reason": reason})
            hours = hours_actual
            for tt in range(n_months):
                truth_monthly.append({"well_id": wid, "t": tt, "cf_oil_m3": float(cf_continue[tt])})
        elif role == "intervention":
            for tt in range(n_months):
                truth_monthly.append({"well_id": wid, "t": tt, "cf_oil_m3": float(cf_oil[tt])})

        oil = np.maximum(actual, 0.0)
        water = oil * wc_actual / np.clip(1 - wc_actual, 0.01, 1)
        gas = oil * gor
        for tt in range(n_months):
            prod_rows.append({"well_id": wid, "month": month_str[tt], "t": tt, "oil_m3": float(oil[tt]), "water_m3": float(water[tt]),
                              "gas_e3m3": float(gas[tt]), "hours": float(hours[tt]), "status": status_series[tt], "source": "SYNTHETIC"})
        final_status = "idle" if status_series[-1] == "idle" else "producing"
        wells.append({"well_id": wid, "source_id": wid, "field": field, "pool": pool, "operator": "Synthetic Operator", "jurisdiction": "SYNTHETIC",
                      "facility_id": facility, "latitude": None, "longitude": None, "spud_date": f"{spud_year}-06-01", "completion_date": f"{spud_year}-09-01",
                      "status": final_status, "well_type": "producer", "lift_type": str(lift), "role": role})
    prod = pd.DataFrame(prod_rows)

    # Data-quality imperfections (so the DQ layer has something real to find)
    dq_wells = [w["well_id"] for w in wells if w["role"] == "producer"][:9]
    for w in dq_wells[:5]:
        drop_t = rng.choice(np.arange(10, n_months - 10), size=int(rng.integers(2, 5)), replace=False)
        prod = prod[~((prod.well_id == w) & (prod.t.isin(drop_t)))]
    for w in dq_wells[5:7]:
        dup = prod[(prod.well_id == w) & (prod.t == 20)]
        prod = pd.concat([prod, dup], ignore_index=True)
    for w in dq_wells[7:8]:
        prod.loc[(prod.well_id == w) & (prod.t == 33), "water_m3"] = -12.0
    for w in dq_wells[8:9]:
        prod.loc[(prod.well_id == w) & (prod.t == 40), "oil_m3"] *= 5.0
    prod = prod.sort_values(["well_id", "t"]).reset_index(drop=True)
    # illustrative facility capacities set relative to the final-quarter fluid load so that some facilities are near their limit
    wdf = pd.DataFrame(wells)[["well_id", "facility_id"]]
    recent = prod[prod.t >= n_months - 3].merge(wdf, on="well_id")
    load = (recent.groupby("facility_id").apply(lambda g: (g.oil_m3.sum() + g.water_m3.sum()) / 3.0 / 30.4 * M3_TO_BBL)).to_dict()
    factors = [1.06, 1.12, 1.35, 1.6, 1.9, 2.3]
    facilities["fluid_capacity_bpd"] = [round(load.get(f, 5000.0) * factors[i], -1) for i, f in enumerate(facilities.facility_id)]

    return {
        "wells": pd.DataFrame(wells),
        "production_monthly": prod,
        "interventions": pd.DataFrame(interventions),
        "facilities": facilities,
        "truth_events": pd.DataFrame(truth_events),
        "truth_monthly": pd.DataFrame(truth_monthly),
        "calendar": pd.DataFrame({"t": np.arange(n_months), "month": month_str, "days": days}),
    }
