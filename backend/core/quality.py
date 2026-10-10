"""Data-quality components per well. The score is never shown without its components."""
from __future__ import annotations

import numpy as np
import pandas as pd


def well_quality(prod: pd.DataFrame, n_months: int, pre_window: int = 12, post_window: int = 12) -> dict:
    """prod: raw rows for one well (may include duplicates / missing months)."""
    p = prod.sort_values("t")
    months_present = p.t.nunique()
    missing_months = int(n_months - months_present)
    duplicate_rows = int(len(p) - months_present)
    negatives = int(((p.oil_m3 < 0) | (p.water_m3 < 0)).sum())
    ids = p.source_id.nunique() if "source_id" in p.columns else 1
    identifier_changes = int(max(0, ids - 1))
    oil = p.drop_duplicates("t").set_index("t").oil_m3.reindex(range(n_months))
    nz = oil[oil > 0]
    outliers = 0
    jumps = 0
    if len(nz) >= 6:
        med = np.nanmedian(nz)
        mad = np.nanmedian(np.abs(nz - med)) + 1e-9
        outliers = int((np.abs(nz - med) / (1.4826 * mad) > 5).sum())
        r = nz.to_numpy()
        ratio = r[1:] / np.maximum(r[:-1], 1e-9)
        jumps = int(((ratio > 3.5) | (ratio < 1 / 3.5)).sum())
    status_incons = 0
    if "status" in p.columns:
        s = p.drop_duplicates("t").set_index("t").reindex(range(n_months))
        status_incons = int(((s.status == "idle") & (s.oil_m3 > 0)).sum() + ((s.status == "producing") & (s.oil_m3.fillna(0) == 0) & s.oil_m3.notna()).sum())
    unit_issue = int(bool((p.oil_m3 > 50000).any()))  # a monthly conventional-well volume this large signals a unit problem
    producing_idx = np.where(oil.fillna(0).to_numpy() > 0)[0]
    pre_ok = bool(len(producing_idx) >= pre_window)
    post_ok = bool(len(producing_idx) >= pre_window + post_window)
    completeness = months_present / n_months
    components = {
        "completeness": round(float(completeness), 3),
        "missing_months": missing_months,
        "duplicate_rows": duplicate_rows,
        "negative_volumes": negatives,
        "identifier_changes": identifier_changes,
        "outliers": outliers,
        "status_inconsistencies": status_incons,
        "unusual_jumps": jumps,
        "unit_issues": unit_issue,
        "insufficient_pre_period": not pre_ok,
        "insufficient_post_period": not post_ok,
    }
    penalty = (1 - completeness) * 40 + duplicate_rows * 5 + negatives * 10 + identifier_changes * 10 + outliers * 6 + status_incons * 4 + min(jumps, 5) * 3 + unit_issue * 30 + (0 if pre_ok else 15)
    score = max(0.0, 100.0 - penalty)
    flags = [k for k, v in components.items() if (v is True) or (isinstance(v, (int,)) and not isinstance(v, bool) and v > 0 and k != "missing_months")]
    if missing_months > 0:
        flags.append("missing_months")
    return {"score": round(score, 1), "grade": "good" if score >= 85 else "fair" if score >= 65 else "poor", "components": components, "flags": flags}


def quality_table(ds) -> pd.DataFrame:
    rows = []
    for wid, g in ds.production.groupby("well_id"):
        q = well_quality(g, ds.n_months)
        rows.append({"well_id": wid, "dq_score": q["score"], "dq_grade": q["grade"], "dq_flags": ",".join(q["flags"]), **{f"dq_{k}": v for k, v in q["components"].items()}})
    return pd.DataFrame(rows)
