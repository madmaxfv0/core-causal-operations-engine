"""Precomputed evidence base. Computed once (init or after settings change), read by the API."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from ..config import CACHE_DIR, load_settings
from . import engine, ghost, idle, memory, validation, water
from .causal import clean_json

ARTIFACTS = ["memory", "idle", "ghost", "water", "planted_truth", "blind_test", "placebo", "calibration", "reason_accuracy"]


def _dataset_cache_dir(dataset: str | None = None):
    """Evidence artifacts live per data set.

    A single shared cache meant that switching data mode overwrote the other mode's
    precomputed analyses, so returning to SYNTHETIC found an evidence base built for
    real data and refused to serve. Keeping them separate lets both modes stay ready.
    """
    if dataset is None:
        from ..data import store
        dataset = store.active_dataset_name()
    d = CACHE_DIR / dataset
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(name: str, dataset: str | None = None):
    return _dataset_cache_dir(dataset) / f"agg_{name}.json"


def get(name: str):
    p = _path(name)
    if p.exists():
        return json.loads(p.read_text())
    return None


def put(name: str, obj):
    _path(name).write_text(json.dumps(clean_json(obj)))


def stale() -> bool:
    m = get("meta")
    if not m:
        return True
    ctx = engine.get_context()
    s = ctx.settings
    return m.get("dataset_version") != ctx.ds.meta.get("dataset_version") or m.get("settings_sig") != settings_sig(s)


def dataset_mismatch() -> str | None:
    """Reason the cached evidence base does not belong to the active data set, else None.

    This is the guard that stops a page serving records from one data set while the
    header advertises another — the failure mode where synthetic SYN-* rows are shown
    under a REAL PUBLIC DATA badge. Callers must refuse to serve, not silently mix.
    """
    m = get("meta")
    if not m:
        return "The evidence base has not been built yet."
    built_for = m.get("dataset_name")
    try:
        ds = engine.get_context().ds
    except Exception:
        return None
    active = ds.name
    if built_for:
        if built_for != active:
            return (f"The evidence base was built from the '{built_for}' data set, but the active data context "
                    f"is '{active}'. Refusing to show '{built_for}' records as '{active}' data. Rebuild the "
                    "evidence base to analyse the active data set.")
        return None
    # Caches written before data-context tracking: the dataset_version hash still
    # proves which data produced them, so an exact match is accepted.
    if m.get("dataset_version") and m.get("dataset_version") == ds.meta.get("dataset_version"):
        return None
    return (f"The evidence base does not match the active data set '{active}', so its records cannot be "
            "shown as this data set's results. Rebuild the evidence base.")


def settings_sig(s: dict) -> str:
    import hashlib
    return hashlib.sha1(json.dumps({"economics": s["economics"], "causal": s["causal"], "restart": s["restart"], "confidence": s["confidence"], "portfolio": {"min_npv": s["portfolio"]["min_npv"]}}, sort_keys=True).encode()).hexdigest()[:10]


def build_all(progress=None, log=print):
    t0 = time.time()
    engine.clear_context()
    ctx = engine.get_context()
    log(f"Context: {len(ctx.ds.wells)} wells, {ctx.ds.n_months} months, {len(ctx.restart_events)} observed restarts, {int((ctx.status.status == 'idle').sum())} idle")
    rows = memory.analyse_all(ctx, progress=progress)
    put("memory", rows)
    log(f"Intervention memory: {len(rows)} events analysed ({time.time() - t0:.0f}s)")
    idle_res = idle.screen(ctx, rows, progress=progress)
    put("idle", idle_res)
    log(f"Idle wells: funnel {idle_res['funnel']}")
    ghost_res = ghost.screen(ctx, progress=progress)
    put("ghost", ghost_res)
    log(f"Ghost barrels: {ghost_res['kpi']} ({time.time() - t0:.0f}s)")
    water_res = water.table(ctx, rows)
    put("water", water_res)
    log(f"Water: {water_res['kpi']}")
    put("planted_truth", validation.planted_truth(rows))
    put("blind_test", validation.blind_test(ctx, rows))
    put("placebo", validation.placebo_summary(rows))
    put("calibration", validation.calibration(rows, idle_res["rows"]))
    put("reason_accuracy", validation.reason_accuracy(ctx, idle_res["rows"]))
    put("meta", {"dataset_name": ctx.ds.name, "dataset_version": ctx.ds.meta.get("dataset_version"), "settings_sig": settings_sig(ctx.settings), "built_at": datetime.now(timezone.utc).isoformat(), "elapsed_s": round(time.time() - t0, 1)})
    log(f"Precompute complete in {time.time() - t0:.0f}s")


def rebuild_economics_only(log=print):
    """Cheaper refresh when only economic assumptions change: causal runs are reused from cache."""
    engine.clear_context()
    ctx = engine.get_context()
    rows = memory.analyse_all(ctx)  # cached causal runs → fast
    put("memory", rows)
    idle_res = idle.screen(ctx, rows)
    put("idle", idle_res)
    ghost_res = ghost.screen(ctx)
    put("ghost", ghost_res)
    put("water", water.table(ctx, rows))
    put("planted_truth", validation.planted_truth(rows))
    put("blind_test", validation.blind_test(ctx, rows))
    put("placebo", validation.placebo_summary(rows))
    put("calibration", validation.calibration(rows, idle_res["rows"]))
    put("reason_accuracy", validation.reason_accuracy(ctx, idle_res["rows"]))
    put("meta", {"dataset_name": ctx.ds.name, "dataset_version": ctx.ds.meta.get("dataset_version"), "settings_sig": settings_sig(ctx.settings), "built_at": datetime.now(timezone.utc).isoformat()})
