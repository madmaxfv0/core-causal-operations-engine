"""Donor pool engine: find comparable untreated wells for a treated/restarted well."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class EventWindow:
    well_id: str
    pre_idx: np.ndarray   # month indices used to fit the counterfactual
    post_idx: np.ndarray  # month indices over which the effect is measured
    kind: str = "intervention"  # intervention | restart | pseudo

    @property
    def guard_idx(self):
        lo = int(self.pre_idx.min()) - 3
        hi = int(self.post_idx.max())
        return lo, hi


def _features(oil: np.ndarray, wc: np.ndarray, hours: np.ndarray) -> np.ndarray:
    x = np.log(np.maximum(oil, 0.05))
    t = np.arange(len(x))
    slope = np.polyfit(t, x, 1)[0] if len(x) > 2 else 0.0
    return np.array([
        x.mean(),
        slope * 12,                          # annual log-decline
        float(np.nanmean(wc)) if np.isfinite(wc).any() else 0.5,
        (np.polyfit(t, np.nan_to_num(wc, nan=np.nanmean(wc) if np.isfinite(wc).any() else 0.5), 1)[0] * 12) if len(x) > 2 else 0.0,
        np.std(x),
        float(np.nanmean(hours)) / 720.0 if np.isfinite(hours).any() else 1.0,
    ])


FEATURE_NAMES = ["log_rate", "annual_decline", "water_cut", "water_cut_trend", "variability", "uptime"]
FEATURE_WEIGHTS = np.array([2.0, 1.5, 1.2, 0.8, 0.6, 0.5])


def eligible_candidates(ds, ev: EventWindow, event_index: dict[str, list[tuple[int, int]]], exclusions: set[str], same_field_only: bool) -> list[str]:
    """Wells with complete, positive production over pre+post and no event of their own inside the guarded window."""
    oil = ds.panel("oil_bpd")
    wells = ds.wells.set_index("well_id")
    tf = wells.loc[ev.well_id, "field"] if ev.well_id in wells.index else None
    lo, hi = ev.guard_idx
    need = np.concatenate([ev.pre_idx, ev.post_idx])
    need = need[(need >= 0) & (need < ds.n_months)]
    out = []
    for wid in oil.columns:
        if wid == ev.well_id or wid in exclusions:
            continue
        if same_field_only and wells.loc[wid, "field"] != tf:
            continue
        arr = oil[wid].to_numpy(dtype=float)[need]
        if np.isnan(arr).mean() > 0.1:
            continue
        if not (np.nan_to_num(arr, nan=0) > 0.5).all():
            continue
        bad = False
        for (a, b) in event_index.get(wid, []):
            if not (b < lo or a > hi):
                bad = True
                break
        if bad:
            continue
        out.append(wid)
    return out


def rank_donors(ds, ev: EventWindow, candidates: list[str], k: int = 25) -> list[dict]:
    oil, wc, hrs = ds.panel("oil_bpd"), ds.panel("water_cut"), ds.panel("hours")
    wells = ds.wells.set_index("well_id")
    tf = wells.loc[ev.well_id, "field"] if ev.well_id in wells.index else None
    pre = ev.pre_idx[(ev.pre_idx >= 0) & (ev.pre_idx < ds.n_months)]
    y = oil[ev.well_id].to_numpy(dtype=float)[pre]
    y = np.where(np.isfinite(y), y, np.nanmean(y))
    ft = _features(y, wc[ev.well_id].to_numpy(dtype=float)[pre], hrs[ev.well_id].to_numpy(dtype=float)[pre])
    rows = []
    feats = []
    for wid in candidates:
        d = oil[wid].to_numpy(dtype=float)[pre]
        d = np.where(np.isfinite(d), d, np.nanmean(d))
        feats.append(_features(d, wc[wid].to_numpy(dtype=float)[pre], hrs[wid].to_numpy(dtype=float)[pre]))
    if not feats:
        return []
    F = np.array(feats)
    scale = F.std(axis=0) + 1e-6
    Z = (F - ft) / scale
    dist = np.sqrt(((Z ** 2) * FEATURE_WEIGHTS).sum(axis=1))
    for wid, f, dd, z in zip(candidates, F, dist, Z):
        field_match = wells.loc[wid, "field"] == tf if wid in wells.index else False
        dd_adj = dd + (0.0 if field_match else 0.8)
        reasons = []
        reasons.append("same field" if field_match else "different field")
        if abs(z[0]) < 0.7:
            reasons.append(f"pre-period rate within {abs(np.exp(f[0] - ft[0]) - 1) * 100:.0f}%")
        if abs(z[1]) < 0.8:
            reasons.append("similar decline")
        if abs(z[2]) < 0.8:
            reasons.append("similar water cut")
        reasons.append("no intervention or shut-in in window")
        rows.append({"well_id": wid, "distance": float(dd_adj), "similarity": float(1 / (1 + dd_adj)), "pre_rate_bpd": float(np.exp(f[0])),
                     "water_cut": float(f[2]), "trend_pct_per_year": float((np.exp(f[1]) - 1) * 100), "field_match": bool(field_match), "reasons": reasons})
    rows.sort(key=lambda r: r["distance"])
    return rows[:k]


def build_event_index(ds, restart_events: pd.DataFrame, shutin_starts: dict[str, int]) -> dict[str, list[tuple[int, int]]]:
    """Map well -> list of (start_t, end_t) periods where the well is 'treated' (intervention, shut-in, restart)."""
    idx: dict[str, list[tuple[int, int]]] = {}
    for _, r in ds.interventions.iterrows():
        idx.setdefault(r.well_id, []).append((int(r.t) - 1, int(r.t) + 12))
    for _, r in restart_events.iterrows():
        idx.setdefault(r.well_id, []).append((int(r.shutin_t) - 1, int(r.restart_t) + 12))
    for wid, s in shutin_starts.items():
        idx.setdefault(wid, []).append((int(s) - 1, 10_000))
    return idx
