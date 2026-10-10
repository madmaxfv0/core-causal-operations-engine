"""Observed restart-event detection from production history.

A restart is *observed*, not a workover: it is only called an intervention when an explicit record exists.
N (min inactive months) and M (min producing months) are configuration, never hard-coded in analysis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def inactive_mask(oil_bpd: np.ndarray, zero_threshold_bpd: float = 0.5) -> np.ndarray:
    return ~(np.nan_to_num(oil_bpd, nan=0.0) > zero_threshold_bpd)


def detect_restarts(oil_bpd: np.ndarray, min_inactive: int = 3, min_producing: int = 3, zero_threshold_bpd: float = 0.5) -> list[dict]:
    """Return observed restart events: inactive run of >= N months followed by >= M producing months."""
    inactive = inactive_mask(oil_bpd, zero_threshold_bpd)
    n = len(inactive)
    events = []
    t = 0
    # skip leading inactivity (never produced yet)
    while t < n and inactive[t]:
        t += 1
    while t < n:
        if inactive[t]:
            s = t
            while t < n and inactive[t]:
                t += 1
            run = t - s
            if run >= min_inactive and t < n:
                r = t
                m = 0
                while t < n and not inactive[t]:
                    t += 1
                    m += 1
                if m >= min_producing:
                    events.append({"shutin_t": s, "restart_t": r, "inactive_months": run, "producing_after": m, "sustained": bool(t >= n or m >= 6)})
            # else: too-short gap or trailing inactivity: continue
        else:
            t += 1
    return events


def shutin_periods(oil_bpd: np.ndarray, zero_threshold_bpd: float = 0.5) -> list[dict]:
    inactive = inactive_mask(oil_bpd, zero_threshold_bpd)
    out, t, n = [], 0, len(inactive)
    while t < n and inactive[t]:
        t += 1
    while t < n:
        if inactive[t]:
            s = t
            while t < n and inactive[t]:
                t += 1
            out.append({"start_t": s, "end_t": t - 1, "months": t - s, "ongoing": t >= n})
        else:
            t += 1
    return out


def current_status(oil_bpd: np.ndarray, min_inactive: int = 3, zero_threshold_bpd: float = 0.5) -> dict:
    inactive = inactive_mask(oil_bpd, zero_threshold_bpd)
    n = len(inactive)
    trailing = 0
    for v in inactive[::-1]:
        if v:
            trailing += 1
        else:
            break
    ever = (~inactive).any()
    last_prod_t = int(np.where(~inactive)[0].max()) if ever else None
    if not ever:
        return {"status": "never_produced", "idle_months": n, "last_production_t": None}
    if trailing >= min_inactive:
        return {"status": "idle", "idle_months": trailing, "last_production_t": last_prod_t}
    if trailing > 0:
        return {"status": "recently_stopped", "idle_months": trailing, "last_production_t": last_prod_t}
    return {"status": "producing", "idle_months": 0, "last_production_t": last_prod_t}


def all_events(panel_oil_bpd: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = []
    for wid in panel_oil_bpd.columns:
        arr = panel_oil_bpd[wid].to_numpy(dtype=float)
        for e in detect_restarts(arr, cfg["min_inactive_months"], cfg["min_producing_months"], cfg["zero_threshold_bpd"]):
            rows.append({"well_id": wid, **e})
    cols = ["well_id", "shutin_t", "restart_t", "inactive_months", "producing_after", "sustained"]
    return pd.DataFrame(rows, columns=cols)


def status_table(panel_oil_bpd: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = []
    for wid in panel_oil_bpd.columns:
        arr = panel_oil_bpd[wid].to_numpy(dtype=float)
        rows.append({"well_id": wid, **current_status(arr, cfg["min_inactive_months"], cfg["zero_threshold_bpd"])})
    return pd.DataFrame(rows)
