"""M0 — Causal core.

Observed production after an event MINUS estimated production had the event never happened
= estimated causal effect. Before/after is computed only as the "naive" comparison.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from ..config import MODEL_VERSION
from . import decline as dc
from .matching import EventWindow, build_event_index, eligible_candidates, rank_donors

MODELS = ["auto", "synthetic_control", "matched_wells", "did", "decline_curve"]
MODEL_LABELS = {"synthetic_control": "Synthetic control", "matched_wells": "Matched wells", "did": "Difference-in-differences (log)", "decline_curve": "Decline curve (Arps)"}


# ----------------------------------------------------------------------------- estimators
def sc_weights(y_pre: np.ndarray, Y_pre: np.ndarray) -> np.ndarray:
    J = Y_pre.shape[1]
    if J == 1:
        return np.array([1.0])
    s = max(float(np.mean(y_pre)), 1e-6)
    yp, Yp = y_pre / s, Y_pre / s
    w0 = np.ones(J) / J

    def obj(w):
        r = yp - Yp @ w
        return float(r @ r)

    res = minimize(obj, w0, method="SLSQP", bounds=[(0.0, 1.0)] * J, constraints=({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},), options={"maxiter": 400, "ftol": 1e-12})
    w = np.clip(res.x, 0, None)
    return w / max(w.sum(), 1e-12)


def fit_counterfactual(model: str, y_pre: np.ndarray, Y_pre: np.ndarray, Y_post: np.ndarray, sims: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, dict]:
    """Return (cf_pre_fitted, cf_post, info)."""
    if model == "synthetic_control":
        w = sc_weights(y_pre, Y_pre)
        return Y_pre @ w, Y_post @ w, {"weights": w}
    if model == "matched_wells":
        k = min(5, Y_pre.shape[1])
        order = np.argsort(-sims)[:k] if sims is not None else np.arange(k)
        scale = np.mean(y_pre) / np.maximum(Y_pre[:, order].mean(axis=0), 1e-6)
        w = np.zeros(Y_pre.shape[1])
        w[order] = scale / k
        return Y_pre @ w, Y_post @ w, {"weights": w, "matched": order.tolist()}
    if model == "did":
        dm_pre = Y_pre.mean(axis=1)
        dm_post = Y_post.mean(axis=1)
        base = float(np.mean(y_pre))
        ratio_pre = dm_pre / max(float(dm_pre.mean()), 1e-6)
        ratio_post = dm_post / max(float(dm_pre.mean()), 1e-6)
        w = np.ones(Y_pre.shape[1]) / Y_pre.shape[1]
        return base * ratio_pre, base * ratio_post, {"weights": w}
    raise ValueError(model)


def r2(y, yhat) -> float:
    sse = float(np.sum((y - yhat) ** 2))
    sst = float(np.sum((y - np.mean(y)) ** 2)) + 1e-9
    return float(1 - sse / sst)


# ----------------------------------------------------------------------------- result
@dataclass
class CausalResult:
    well_id: str
    model: str
    model_label: str
    status: str
    confidence: str
    pre_idx: list
    post_idx: list
    actual: list
    counterfactual: list
    cf_lo: list
    cf_hi: list
    cf_pre_fit: list
    effect_bpd: list
    cumulative_bbl: list
    mean_effect_bpd: float
    effect_lo_bpd: float
    effect_hi_bpd: float
    cumulative_effect_bbl: float
    cumulative_lo_bbl: float
    cumulative_hi_bbl: float
    naive_effect_bpd: float
    naive_cumulative_bbl: float
    naive_pre_level: float
    naive_post_level: float
    diagnostics: dict
    donors: list
    donor_paths: dict
    placebo: dict
    messages: list
    meta: dict
    truth: dict | None = None

    def to_dict(self):
        return self.__dict__


def confidence_label(diag: dict, thresholds: dict, min_donors: int) -> tuple[str, float]:
    if diag.get("insufficient"):
        return "INSUFFICIENT EVIDENCE", 0.0
    pts = []
    r = diag.get("pre_r2") or 0.0
    nr = diag.get("pre_nrmse")
    fit_pts = 1.0 if r >= 0.8 else 0.6 if r >= 0.6 else 0.3 if r >= thresholds.get("min_pre_r2", 0.4) else 0.0
    if nr is not None:
        fit_pts = max(fit_pts, 1.0 if nr <= 0.08 else 0.6 if nr <= 0.15 else 0.3 if nr <= 0.25 else 0.0)
    pts.append(fit_pts)
    d = diag.get("donor_count", 0)
    pts.append(1.0 if d >= 10 else 0.6 if d >= 6 else 0.3 if d >= min_donors else 0.0)
    p = diag.get("placebo_wells_p")
    pts.append(0.5 if p is None else 1.0 if p <= 0.15 else 0.6 if p <= 0.35 else 0.2)
    pt = diag.get("placebo_time_score")
    pts.append(0.5 if pt is None else 1.0 if pt >= 0.7 else 0.6 if pt >= 0.4 else 0.3)
    m = diag.get("missing_pct", 0)
    pts.append(1.0 if m <= 0.02 else 0.6 if m <= 0.1 else 0.2)
    score = float(np.mean(pts))
    if diag.get("model") == "decline_curve":
        score = min(score, 0.7)
    label = "HIGH CONFIDENCE" if score >= thresholds.get("high", 0.8) else "MODERATE CONFIDENCE" if score >= thresholds.get("moderate", 0.55) else "LOW CONFIDENCE"
    if fit_pts < 0.6 and label == "HIGH CONFIDENCE":
        label = "MODERATE CONFIDENCE"
    if fit_pts < 0.3:
        label = "LOW CONFIDENCE"
    return label, score


# ----------------------------------------------------------------------------- main entry
def run_causal(ds, well_id: str, pre_end: int, post_start: int, *, model: str = "auto", pre_window: int = 12, post_window: int = 12,
               settings: dict, event_index: dict, exclusions: set[str] | None = None, forced_donors: list[str] | None = None,
               kind: str = "intervention", bootstrap: int | None = None, placebo_wells: int | None = None, progress=None,
               truth: dict | None = None) -> CausalResult:
    t0 = time.time()
    cfg = settings["causal"]
    exclusions = set(exclusions or [])
    bootstrap = cfg["bootstrap_samples"] if bootstrap is None else bootstrap
    placebo_n = cfg["placebo_wells"] if placebo_wells is None else placebo_wells
    rng = np.random.default_rng(cfg.get("seed", 7))
    oil = ds.panel("oil_bpd")
    days = ds.days
    n = ds.n_months
    pre_idx = np.arange(max(0, pre_end - pre_window + 1), pre_end + 1)
    post_idx = np.arange(post_start, min(n, post_start + post_window))
    ev = EventWindow(well_id=well_id, pre_idx=pre_idx, post_idx=post_idx, kind=kind)
    messages: list[str] = []

    y_full = oil[well_id].to_numpy(dtype=float)
    y_pre_raw, y_post_raw = y_full[pre_idx], y_full[post_idx]
    missing_pct = float(np.isnan(np.concatenate([y_pre_raw, y_post_raw])).mean())
    y_pre = np.where(np.isfinite(y_pre_raw), y_pre_raw, np.nanmean(y_pre_raw) if np.isfinite(y_pre_raw).any() else 0.0)
    y_post = np.where(np.isfinite(y_post_raw), y_post_raw, 0.0)

    if progress: progress("Finding donors...")
    cands = eligible_candidates(ds, ev, event_index, exclusions, cfg.get("same_field_only", False))
    donors = rank_donors(ds, ev, cands, k=cfg["max_donors"])
    if forced_donors:
        have = {d["well_id"] for d in donors}
        extra = [d for d in rank_donors(ds, ev, [w for w in forced_donors if w not in have and w in cands], k=len(forced_donors))]
        donors = donors + extra
    donor_ids = [d["well_id"] for d in donors]
    sims = np.array([d["similarity"] for d in donors]) if donors else np.array([])
    D = np.array(oil[donor_ids].to_numpy(dtype=float), copy=True) if donor_ids else np.zeros((n, 0))
    if D.size:
        for j in range(D.shape[1]):
            col = D[:, j]
            if np.isnan(col).any():
                idx = np.arange(n)
                col[np.isnan(col)] = np.interp(idx[np.isnan(col)], idx[~np.isnan(col)], col[~np.isnan(col)])
                D[:, j] = col
    Y_pre, Y_post = D[pre_idx], D[post_idx]

    # ---- choose model
    diag: dict = {"donor_count": len(donor_ids), "candidate_count": len(cands), "missing_pct": round(missing_pct, 3), "pre_window": int(len(pre_idx)), "post_window": int(len(post_idx))}
    insufficient = len(pre_idx) < 6 or len(post_idx) < 3
    chosen = model
    if progress: progress("Validating pre-period fit...")
    if model == "auto":
        if len(donor_ids) >= max(cfg["min_donors"], 5):
            cf_pre, _, _ = fit_counterfactual("synthetic_control", y_pre, Y_pre, Y_post, sims)
            if r2(y_pre, cf_pre) >= 0.6:
                chosen = "synthetic_control"
            else:
                chosen = "matched_wells"
                messages.append("Synthetic control pre-period fit was weak; AUTO selected matched wells (level-scaled).")
        elif len(donor_ids) >= cfg["min_donors"]:
            chosen = "matched_wells"
            messages.append(f"Only {len(donor_ids)} eligible comparison wells; AUTO selected matched wells.")
        else:
            chosen = "decline_curve"
            messages.append(f"Only {len(donor_ids)} eligible comparison wells (minimum {cfg['min_donors']}); AUTO fell back to a decline-curve baseline.")
    if chosen != "decline_curve" and len(donor_ids) < cfg["min_donors"]:
        insufficient = True
        messages.append(f"Counterfactual could not be estimated with {MODEL_LABELS.get(chosen, chosen)}: only {len(donor_ids)} eligible comparison wells were available. Minimum configured requirement: {cfg['min_donors']}.")
    diag["model"] = chosen

    # ---- fit
    if progress: progress("Running counterfactual...")
    weights = np.zeros(len(donor_ids))
    paths = []
    fit_info = {}
    if insufficient:
        cf_pre = np.full(len(pre_idx), np.nan)
        cf_post = np.full(len(post_idx), np.nan)
    elif chosen == "decline_curve":
        fit = dc.fit_arps(y_pre)
        if not fit.get("ok"):
            insufficient = True
            messages.append(f"Decline curve could not be fitted: {fit.get('reason')}")
            cf_pre, cf_post = np.full(len(pre_idx), np.nan), np.full(len(post_idx), np.nan)
        else:
            fit_info = {"decline_model": fit["model"], "params": fit["params"], "poor_fit": fit["poor_fit"], "flag": fit["flag"]}
            if fit["flag"]:
                messages.append(f"Decline-curve caveat: {fit['flag']}.")
            tt_pre = np.arange(len(pre_idx), dtype=float)
            tt_post = np.arange(len(pre_idx), len(pre_idx) + len(post_idx), dtype=float) + (post_idx[0] - pre_idx[-1] - 1)
            cf_pre = dc.extrapolate(fit, tt_pre)
            cf_post = dc.extrapolate(fit, tt_post)
            paths = dc.sample_paths(fit, tt_post, n=bootstrap, seed=cfg.get("seed", 7))
    else:
        cf_pre, cf_post, fit_info = fit_counterfactual(chosen, y_pre, Y_pre, Y_post, sims)
        weights = fit_info.get("weights", weights)
        # bootstrap over donors
        if progress: progress("Estimating uncertainty (bootstrap)...")
        J = Y_pre.shape[1]
        for _ in range(bootstrap):
            samp = rng.integers(0, J, size=J)
            try:
                _, cfp, _ = fit_counterfactual(chosen, y_pre, Y_pre[:, samp], Y_post[:, samp], sims[samp])
                paths.append(cfp)
            except Exception:
                continue
    paths = np.array(paths) if len(paths) else np.zeros((0, len(post_idx)))
    if paths.size and not insufficient:
        pre_res_sd = float(np.std(y_pre - cf_pre)) if np.isfinite(cf_pre).all() else 0.0
        ar = np.zeros(paths.shape)
        ar[:, 0] = rng.normal(0, pre_res_sd, size=paths.shape[0])
        for tt in range(1, paths.shape[1]):
            ar[:, tt] = 0.5 * ar[:, tt - 1] + rng.normal(0, pre_res_sd * np.sqrt(1 - 0.25), size=paths.shape[0])
        paths = paths + ar
    if paths.size:
        cf_lo, cf_hi = np.percentile(paths, 10, axis=0), np.percentile(paths, 90, axis=0)
        cum_paths = np.array([np.sum((y_post - p) * days[post_idx]) for p in paths])
        eff_paths = np.array([np.mean(y_post - p) for p in paths])
        cum_lo, cum_hi = float(np.percentile(cum_paths, 10)), float(np.percentile(cum_paths, 90))
        eff_lo, eff_hi = float(np.percentile(eff_paths, 10)), float(np.percentile(eff_paths, 90))
    else:
        cf_lo, cf_hi = cf_post, cf_post
        cum_lo = cum_hi = eff_lo = eff_hi = float("nan")

    effect = y_post - cf_post
    cum = np.cumsum(effect * days[post_idx])
    diag["pre_r2"] = round(r2(y_pre, cf_pre), 3) if not insufficient else None
    diag["pre_rmse_bpd"] = round(float(np.sqrt(np.mean((y_pre - cf_pre) ** 2))), 2) if not insufficient else None
    diag["pre_nrmse"] = round(float(diag["pre_rmse_bpd"] / max(float(np.mean(y_pre)), 1e-6)), 3) if not insufficient else None
    diag["insufficient"] = bool(insufficient)
    diag["donor_pool_quality"] = round(float(np.mean(sims[:10])), 3) if len(sims) else None
    diag["effective_donors"] = round(float(1.0 / np.sum((weights / max(weights.sum(), 1e-9)) ** 2)), 1) if weights.sum() > 0 else 0
    diag["baseline_reliability"] = "high" if (diag["pre_r2"] or 0) >= 0.8 else "moderate" if (diag["pre_r2"] or 0) >= 0.6 else "low"
    diag.update({k: v for k, v in fit_info.items() if k not in ("weights", "matched")})

    # ---- placebo in time
    if progress: progress("Running placebo tests...")
    placebo: dict = {"in_time": None, "wells": None}
    if not insufficient and chosen != "decline_curve" and len(pre_idx) >= 8:
        fake_t0 = int(pre_idx[0]) - 1
        fake_pre = np.arange(fake_t0 - len(pre_idx) + 1, fake_t0 + 1)
        fake_post = pre_idx[: max(3, len(post_idx) // 2)]
        if fake_pre.min() >= 0 and len(fake_pre) >= 6:
            try:
                yp, ypp = y_full[fake_pre], y_full[fake_post]
                okd = [j for j in range(D.shape[1]) if (D[fake_pre, j] > 0.5).all() and (D[fake_post, j] > 0.5).all()]
                if np.isfinite(yp).mean() > 0.8 and (np.nan_to_num(yp) > 0.5).mean() > 0.9 and len(okd) >= 3:
                    yp = np.where(np.isfinite(yp), yp, np.nanmean(yp)); ypp = np.where(np.isfinite(ypp), ypp, np.nanmean(ypp))
                    _, cfpp, _ = fit_counterfactual(chosen, yp, D[fake_pre][:, okd], D[fake_post][:, okd], sims[okd])
                    pl_eff = float(np.mean(ypp - cfpp))
                    act = float(np.mean(effect))
                    ratio = abs(pl_eff) / max(abs(act), 1e-6)
                    placebo["in_time"] = {"fake_t0": fake_t0, "fake_effect_bpd": round(pl_eff, 2), "actual_effect_bpd": round(act, 2), "ratio": round(min(ratio, 5), 3), "score": round(float(max(0.0, 1 - ratio)), 3), "note": "A good model finds ~no effect at a fake earlier treatment date."}
                    diag["placebo_time_score"] = placebo["in_time"]["score"]
            except Exception:
                pass
    if not insufficient and chosen != "decline_curve" and len(donor_ids) >= 4:
        treated_ratio = float(np.sqrt(np.mean(effect ** 2)) / max(diag["pre_rmse_bpd"], 1e-6))
        ratios = []
        top = np.argsort(-sims)[:placebo_n]
        for j in top:
            others = [k for k in range(len(donor_ids)) if k != j]
            if len(others) < 2:
                continue
            try:
                cfp_pre, cfp_post, _ = fit_counterfactual(chosen, Y_pre[:, j], Y_pre[:, others], Y_post[:, others], sims[others])
                pre_rmse = np.sqrt(np.mean((Y_pre[:, j] - cfp_pre) ** 2))
                post_rmse = np.sqrt(np.mean((Y_post[:, j] - cfp_post) ** 2))
                ratios.append({"well_id": donor_ids[j], "rmspe_ratio": float(post_rmse / max(pre_rmse, 1e-6)), "effect_bpd": float(np.mean(Y_post[:, j] - cfp_post))})
            except Exception:
                continue
        if ratios:
            ge = sum(1 for r in ratios if r["rmspe_ratio"] >= treated_ratio)
            p = (1 + ge) / (1 + len(ratios))
            placebo["wells"] = {"treated_rmspe_ratio": round(treated_ratio, 2), "placebos": [{**r, "rmspe_ratio": round(r["rmspe_ratio"], 2), "effect_bpd": round(r["effect_bpd"], 2)} for r in ratios], "p_value": round(float(p), 3), "note": "Share of untreated wells whose fake 'effect' is at least as large as the treated well's."}
            diag["placebo_wells_p"] = placebo["wells"]["p_value"]
            pl_sd = float(np.std([r["effect_bpd"] for r in ratios])) if len(ratios) >= 3 else 0.0
            if np.isfinite(eff_lo) and pl_sd > 0:
                boot_sd = (eff_hi - eff_lo) / 2.56
                tot = float(np.sqrt(boot_sd ** 2 + pl_sd ** 2))
                m = float(np.mean(effect))
                eff_lo, eff_hi = m - 1.28 * tot, m + 1.28 * tot
                cmean = float(np.sum(effect * days[post_idx]))
                cum_lo, cum_hi = cmean - 1.28 * tot * float(days[post_idx].sum()), cmean + 1.28 * tot * float(days[post_idx].sum())
                diag["interval_note"] = "80% interval combines donor-resampling and placebo-well dispersion"

    # ---- naive
    k3 = 3
    naive_pre = float(np.nanmean(y_pre[-k3:]))
    naive_post = float(np.nanmean(y_post[:k3]))
    naive_eff = naive_post - naive_pre
    naive_cum = float(naive_eff * days[post_idx].sum())

    conf, score = confidence_label(diag, settings["confidence"], cfg["min_donors"])
    diag["confidence_score"] = round(score, 3)
    status = "INSUFFICIENT EVIDENCE" if insufficient else "COMPLETE"

    donor_paths = {}
    if not insufficient and len(donor_ids):
        order = np.argsort(-weights)[:5] if weights.sum() > 0 else np.argsort(-sims)[:5]
        for j in order:
            if weights[j] > 0 or chosen == "did":
                idxs = np.concatenate([pre_idx, post_idx])
                donor_paths[donor_ids[j]] = [round(float(v), 2) for v in D[idxs, j]]
    for d, w in zip(donors, weights if len(weights) == len(donors) else np.zeros(len(donors))):
        d["weight"] = round(float(w), 4)
        d["excluded"] = False
    for wid in exclusions:
        donors.append({"well_id": wid, "excluded": True, "weight": 0.0, "similarity": None, "reasons": ["excluded by engineer"]})

    if progress: progress("Calculating economics...")
    res = CausalResult(
        well_id=well_id, model=chosen, model_label=MODEL_LABELS.get(chosen, chosen), status=status, confidence=conf,
        pre_idx=pre_idx.tolist(), post_idx=post_idx.tolist(),
        actual=[None if not np.isfinite(v) else round(float(v), 2) for v in np.concatenate([y_pre_raw, y_post_raw])],
        counterfactual=[None if not np.isfinite(v) else round(float(v), 2) for v in np.concatenate([cf_pre, cf_post])],
        cf_lo=[None if not np.isfinite(v) else round(float(v), 2) for v in np.concatenate([cf_pre, cf_lo])],
        cf_hi=[None if not np.isfinite(v) else round(float(v), 2) for v in np.concatenate([cf_pre, cf_hi])],
        cf_pre_fit=[None if not np.isfinite(v) else round(float(v), 2) for v in cf_pre],
        effect_bpd=[None if not np.isfinite(v) else round(float(v), 2) for v in effect],
        cumulative_bbl=[None if not np.isfinite(v) else round(float(v), 0) for v in cum],
        mean_effect_bpd=round(float(np.nanmean(effect)), 2) if not insufficient else float("nan"),
        effect_lo_bpd=round(eff_lo, 2) if np.isfinite(eff_lo) else float("nan"), effect_hi_bpd=round(eff_hi, 2) if np.isfinite(eff_hi) else float("nan"),
        cumulative_effect_bbl=round(float(cum[-1]), 0) if (len(cum) and np.isfinite(cum[-1])) else float("nan"),
        cumulative_lo_bbl=round(cum_lo, 0) if np.isfinite(cum_lo) else float("nan"), cumulative_hi_bbl=round(cum_hi, 0) if np.isfinite(cum_hi) else float("nan"),
        naive_effect_bpd=round(naive_eff, 2), naive_cumulative_bbl=round(naive_cum, 0), naive_pre_level=round(naive_pre, 2), naive_post_level=round(naive_post, 2),
        diagnostics=diag, donors=donors, donor_paths=donor_paths, placebo=placebo, messages=messages,
        meta={"model_version": MODEL_VERSION, "dataset_version": ds.meta.get("dataset_version"), "seed": cfg.get("seed", 7), "bootstrap_samples": bootstrap,
              "elapsed_s": round(time.time() - t0, 2), "pre_window": pre_window, "post_window": post_window, "kind": kind, "requested_model": model},
        truth=truth,
    )
    return res


def clean_json(obj):
    """Replace NaN/inf with None recursively so responses are valid JSON."""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return clean_json(obj.tolist())
    return obj
