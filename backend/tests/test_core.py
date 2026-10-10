"""CORE test suite. Run: pytest backend/tests -q"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

from backend import config  # noqa: E402
from backend.config import M3_TO_BBL  # noqa: E402
from backend.core import causal, decline, economics, portfolio, restart  # noqa: E402
from backend.data import store  # noqa: E402


# ----------------------------------------------------------------------------- unit
def test_water_cut_and_conversion():
    cal = pd.DataFrame({"t": [0, 1], "month": ["2024-01", "2024-02"], "days": [31.0, 29.0]})
    prod = pd.DataFrame({"well_id": ["W", "W"], "month": ["2024-01", "2024-02"], "t": [0, 1], "oil_m3": [100.0, 0.0], "water_m3": [300.0, 0.0], "gas_e3m3": [1.0, 0.0], "hours": [720, 0], "status": ["producing", "idle"], "source": "t"})
    d = store.derive_production(prod, cal)
    assert abs(d.oil_bbl.iloc[0] - 100 * M3_TO_BBL) < 1e-6
    assert abs(d.water_cut.iloc[0] - 0.75) < 1e-9
    assert np.isnan(d.water_cut.iloc[1])  # no fluid → undefined, not zero
    assert abs(d.oil_bpd.iloc[0] - 100 * M3_TO_BBL / 31) < 1e-6
    assert d.oil_m3.iloc[0] == 100.0  # source units preserved


def test_restart_detection_configurable():
    s = np.array([10, 10, 0, 0, 0, 8, 9, 9, 9, 0, 0, 7, 7, 7, 7, 7])
    ev = restart.detect_restarts(s, min_inactive=3, min_producing=3)
    assert len(ev) == 1 and ev[0]["shutin_t"] == 2 and ev[0]["restart_t"] == 5
    ev2 = restart.detect_restarts(s, min_inactive=2, min_producing=3)
    assert len(ev2) == 2
    st = restart.current_status(np.array([5, 5, 0, 0, 0, 0]), min_inactive=3)
    assert st["status"] == "idle" and st["idle_months"] == 4 and st["last_production_t"] == 1
    assert restart.current_status(np.array([0, 0, 0]), 3)["status"] == "never_produced"


def test_decline_fit_and_flag():
    t = np.arange(24)
    q = decline.arps(t, 100, 0.03, 0.5) * (1 + np.random.default_rng(1).normal(0, 0.02, 24))
    f = decline.fit_arps(q)
    assert f["ok"] and f["r2"] > 0.95 and not f["poor_fit"]
    rising = decline.fit_arps(np.linspace(10, 40, 12))
    assert rising["ok"] and rising["poor_fit"]


def test_npv_and_payback():
    s = config.load_settings()
    e = economics.evaluate(s, [10.0] * 12, [0.0] * 12, cost=50000, days=[30.0] * 12)
    nb = economics.netback(s)["value"]
    assert e["incremental_oil_bbl"] == 3600
    assert e["payback_months"] == int(np.ceil(50000 / (10 * 30 * nb)))
    assert e["npv"] < 10 * 30 * 12 * nb - 50000  # discounting reduces value
    zero = economics.evaluate(s, [0.0] * 12, [0.0] * 12, cost=1000)
    assert zero["npv"] == -1000 and zero["payback_months"] is None
    w = economics.water_unit_cost(s)
    assert "corrosion_scale" in w["excluded"]  # OPERATOR DATA REQUIRED components never silently priced


def test_portfolio_constraints_bind():
    cands = [{"candidate_id": f"C{i}", "well_id": f"W{i}", "action": "restart", "cost": 100.0 * (i + 1), "npv": 1000.0 - i, "npv_lo": 0, "npv_hi": 0, "oil_bpd": 1.0, "water_bpd": 0.0, "duration_months": 1.0, "crew_type": "rigless", "risk": 0.2, "confidence": "HIGH CONFIDENCE", "status": "ACT", "safety_block": None} for i in range(10)]
    cands[3]["safety_block"] = "H2S exposure"
    cons = {"budget": 1000, "crews": 1, "rigs": 1, "horizon_months": 12, "max_concurrent": 2, "min_npv": 0, "risk_tolerance": 0.5}
    plan = portfolio.optimise(cands, cons, "npv")
    assert plan["status"] == "Optimal"
    assert plan["kpi"]["investment"] <= 1000
    assert "C3" not in {s["candidate_id"] for s in plan["selected"]}  # safety block always wins
    for q in range(plan["quarters"]):
        assert sum(1 for s in plan["selected"] if s["quarter"] == q) <= 2
    locked = portfolio.optimise(cands, cons, "npv", locked={"C9": 3})
    assert any(s["candidate_id"] == "C9" and s["quarter"] == 3 for s in locked["selected"])
    removed = portfolio.optimise(cands, cons, "npv", removed={"C0"})
    assert "C0" not in {s["candidate_id"] for s in removed["selected"]}
    bigger = portfolio.optimise(cands, {**cons, "budget": 5000, "max_concurrent": 10, "crews": 5}, "npv")
    assert bigger["kpi"]["selected"] > plan["kpi"]["selected"]  # budget genuinely changes the programme


def test_confidence_labels():
    thr = {"high": 0.8, "moderate": 0.55, "min_pre_r2": 0.4}
    lab, _ = causal.confidence_label({"pre_r2": 0.9, "donor_count": 12, "placebo_wells_p": 0.1, "placebo_time_score": 0.8, "missing_pct": 0.0}, thr, 3)
    assert lab == "HIGH CONFIDENCE"
    lab, _ = causal.confidence_label({"pre_r2": 0.1, "pre_nrmse": 0.4, "donor_count": 12, "placebo_wells_p": 0.1, "placebo_time_score": 0.8, "missing_pct": 0.0}, thr, 3)
    assert lab == "LOW CONFIDENCE"  # poor pre-fit gates the label
    lab, _ = causal.confidence_label({"insufficient": True}, thr, 3)
    assert lab == "INSUFFICIENT EVIDENCE"


# ----------------------------------------------------------------------------- causal (synthetic known effect)
def _toy_dataset(effect=0.3, n_donors=12, n=48, seed=3):
    """Tiny panel with a shared shock; treated well gets a multiplicative effect from t=30."""
    rng = np.random.default_rng(seed)
    shock = np.exp(np.cumsum(rng.normal(0, 0.03, n)) * 0.5)
    months = [str(p) for p in pd.period_range("2020-01", periods=n, freq="M")]
    cal = pd.DataFrame({"t": range(n), "month": months, "days": [30.0] * n})
    rows, wells = [], []
    for j in range(n_donors + 1):
        wid = f"W{j:02d}"
        base = 40 * (1 + 0.3 * rng.random()) * np.exp(-0.01 * np.arange(n)) * shock * np.exp(rng.normal(0, 0.03, n))
        if j == 0:
            base[30:] *= 1 + effect
        for t in range(n):
            rows.append({"well_id": wid, "month": months[t], "t": t, "oil_m3": base[t] * 30 / M3_TO_BBL, "water_m3": base[t] * 30 / M3_TO_BBL, "gas_e3m3": 0.0, "hours": 720.0, "status": "producing", "source": "t"})
        wells.append({"well_id": wid, "source_id": wid, "field": "F", "pool": "P", "operator": "o", "jurisdiction": "t", "facility_id": "FAC", "latitude": None, "longitude": None, "spud_date": None, "completion_date": None, "status": "producing", "well_type": "producer", "lift_type": None, "role": "t"})
    prod = store.derive_production(pd.DataFrame(rows), cal)
    ints = pd.DataFrame([{"intervention_id": "I1", "well_id": "W00", "date": months[30], "t": 30, "type": "cleanout", "cost": 1000.0, "duration_months": 0.5, "source": "t", "confidence": "CONFIRMED", "kind": "intervention"}])
    return store.Dataset(name="toy", meta={"dataset_version": "toy"}, wells=pd.DataFrame(wells), production=prod, interventions=ints, facilities=pd.DataFrame(), calendar=cal)


def test_causal_recovers_known_effect_and_beats_naive():
    ds = _toy_dataset(effect=0.3)
    s = config.load_settings()
    s["causal"]["bootstrap_samples"] = 20
    s["causal"]["placebo_wells"] = 6
    idx = {"W00": [(29, 42)]}
    res = causal.run_causal(ds, "W00", 29, 30, settings=s, event_index=idx)
    truth = float(np.mean(ds.panel("oil_bpd")["W00"].to_numpy()[30:42] * (0.3 / 1.3)))
    assert res.status == "COMPLETE" and res.model in ("synthetic_control", "matched_wells")
    assert abs(res.mean_effect_bpd - truth) < 0.25 * truth
    assert res.effect_lo_bpd <= truth <= res.effect_hi_bpd


def test_placebo_no_effect_and_donor_exclusion():
    ds = _toy_dataset(effect=0.0)
    s = config.load_settings()
    s["causal"]["bootstrap_samples"] = 20
    s["causal"]["placebo_wells"] = 6
    idx = {"W00": [(29, 42)]}
    res = causal.run_causal(ds, "W00", 29, 30, settings=s, event_index=idx)
    level = float(np.mean(ds.panel("oil_bpd")["W00"].to_numpy()[18:30]))
    assert abs(res.mean_effect_bpd) < 0.08 * level  # nothing happened → ~no effect
    donors = [d["well_id"] for d in res.donors]
    res2 = causal.run_causal(ds, "W00", 29, 30, settings=s, event_index=idx, exclusions={donors[0], donors[1]})
    used = {d["well_id"] for d in res2.donors if not d.get("excluded")}
    assert donors[0] not in used and donors[1] not in used
    assert any(d.get("excluded") for d in res2.donors)


# ----------------------------------------------------------------------------- API (requires initialised demo data)
@pytest.fixture(scope="module")
def client():
    if not (config.PROCESSED_DIR / "synthetic" / "meta.json").exists():
        pytest.skip("demo data not initialised")
    from fastapi.testclient import TestClient
    from backend.api.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("route", ["/api/meta", "/api/overview", "/api/wells", "/api/interventions", "/api/idle", "/api/ghost", "/api/water", "/api/portfolio/candidates", "/api/validation/planted-truth", "/api/validation/blind-test", "/api/validation/model-cards", "/api/quality", "/api/archive/documents", "/api/network", "/api/data/connectors", "/api/decisions", "/api/settings", "/api/search?q=SYN", "/api/demo/script"])
def test_api_get(client, route):
    r = client.get(route)
    assert r.status_code == 200, r.text[:200]


def test_api_budget_recalculates(client):
    a = client.post("/api/portfolio/optimise", json={"budget": 150000}).json()
    b = client.post("/api/portfolio/optimise", json={"budget": 900000}).json()
    assert a["kpi"]["investment"] <= 150000 and b["kpi"]["selected"] >= a["kpi"]["selected"]


def test_api_reject_requires_reason(client):
    r = client.post("/api/decisions", json={"recommendation_id": "X", "well_id": "SYN-001", "action": "restart", "decision": "REJECT"})
    assert r.status_code == 400


def test_api_no_traceback_on_unknown_well(client):
    r = client.get("/api/wells/DOES-NOT-EXIST")
    assert r.status_code == 404 and "Traceback" not in r.text
