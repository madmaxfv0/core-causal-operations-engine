"""Arps decline curves: the transparent benchmark counterfactual."""
from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit


def arps(t, qi, di, b):
    t = np.asarray(t, dtype=float)
    b = float(b)
    if b < 1e-3:
        return qi * np.exp(-di * t)
    return qi / np.power(np.maximum(1.0 + b * di * t, 1e-9), 1.0 / b)


def fit_arps(rates: np.ndarray, model: str = "auto") -> dict:
    """Fit q(t) on a pre-period. Returns params, r2, flag for unstable/poor fits."""
    y = np.asarray(rates, dtype=float)
    t = np.arange(len(y), dtype=float)
    ok = np.isfinite(y) & (y > 0)
    if ok.sum() < 4:
        return {"ok": False, "reason": "fewer than 4 valid points"}
    tt, yy = t[ok], y[ok]
    best = None
    candidates = {"exponential": (0.0, 0.0), "harmonic": (1.0, 1.0), "hyperbolic": (0.01, 1.5)}
    if model != "auto":
        candidates = {model: candidates[model]}
    for name, (blo, bhi) in candidates.items():
        try:
            if blo == bhi:
                f = lambda t_, qi, di, _b=blo: arps(t_, qi, di, _b)
                p0 = [yy[0], 0.02]
                popt, pcov = curve_fit(f, tt, yy, p0=p0, bounds=([1e-6, 1e-5], [yy.max() * 5, 1.0]), maxfev=4000)
                params = {"qi": popt[0], "di": popt[1], "b": blo}
                pred = arps(tt, *popt, blo)
            else:
                popt, pcov = curve_fit(arps, tt, yy, p0=[yy[0], 0.02, 0.5], bounds=([1e-6, 1e-5, blo], [yy.max() * 5, 1.0, bhi]), maxfev=4000)
                params = {"qi": popt[0], "di": popt[1], "b": popt[2]}
                pred = arps(tt, *popt)
            sse = float(np.sum((yy - pred) ** 2))
            sst = float(np.sum((yy - yy.mean()) ** 2)) + 1e-9
            r2 = 1 - sse / sst
            cand = {"ok": True, "model": name, "params": {k: float(v) for k, v in params.items()}, "r2": float(r2), "rmse": float(np.sqrt(sse / len(yy))), "cov": pcov}
            if best is None or cand["rmse"] < best["rmse"] - 1e-9:
                best = cand
        except Exception:
            continue
    if best is None:
        return {"ok": False, "reason": "curve fit did not converge"}
    trend_up = bool(np.polyfit(tt, np.log(np.maximum(yy, 1e-6)), 1)[0] > 0.02)
    best["poor_fit"] = bool(best["r2"] < 0.3 or trend_up)
    best["flag"] = "unstable or rising pre-period: decline extrapolation not trustworthy" if trend_up else ("poor fit (r2 < 0.3)" if best["r2"] < 0.3 else None)
    return best


def extrapolate(fit: dict, t_index: np.ndarray) -> np.ndarray:
    p = fit["params"]
    return arps(t_index, p["qi"], p["di"], p["b"])


def sample_paths(fit: dict, t_index: np.ndarray, n: int = 60, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    p = fit["params"]
    cov = fit.get("cov")
    names = ["qi", "di"] + (["b"] if fit["model"] == "hyperbolic" else [])
    mean = np.array([p[k] for k in names])
    paths = []
    try:
        c = np.asarray(cov, dtype=float)
        c = c[: len(names), : len(names)]
        if not np.all(np.isfinite(c)):
            raise ValueError
        draws = rng.multivariate_normal(mean, c * 0.5, size=n)
    except Exception:
        draws = mean[None, :] * (1 + rng.normal(0, 0.05, size=(n, len(names))))
    for d in draws:
        qi = max(d[0], 1e-6)
        di = min(max(d[1], 1e-5), 1.0)
        b = p["b"] if fit["model"] != "hyperbolic" else min(max(d[2], 0.01), 1.5)
        paths.append(arps(t_index, qi, di, b))
    return np.array(paths)
