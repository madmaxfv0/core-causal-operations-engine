"""One engine, one evidence base. Builds the shared context and caches every causal run."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import CACHE_DIR, MODEL_VERSION, load_settings
from ..data.store import Dataset, load_dataset
from . import causal, matching, quality, restart
from .causal import clean_json


class Context:
    def __init__(self, ds: Dataset, settings: dict):
        self.ds = ds
        self.settings = settings
        oil = ds.panel("oil_bpd")
        self.restart_events = restart.all_events(oil, settings["restart"])
        self.status = restart.status_table(oil, settings["restart"]).set_index("well_id")
        self.shutin_starts = {w: int(r.last_production_t) + 1 for w, r in self.status.iterrows() if r.status in ("idle", "recently_stopped") and r.last_production_t is not None}
        self.event_index = matching.build_event_index(ds, self.restart_events, self.shutin_starts)
        self.quality = quality.quality_table(ds).set_index("well_id")

    def well_status(self, wid: str) -> str:
        return str(self.status.loc[wid, "status"]) if wid in self.status.index else "unknown"


@lru_cache(maxsize=2)
def _ctx(dataset_version: str, settings_hash: str) -> Context:  # cache key only
    return Context(load_dataset(), load_settings())


def get_context() -> Context:
    ds = load_dataset()
    s = load_settings()
    h = hashlib.sha1(json.dumps({"restart": s["restart"], "causal": s["causal"]}, sort_keys=True).encode()).hexdigest()[:8]
    return _ctx(ds.meta.get("dataset_version", "x"), h)


def clear_context():
    _ctx.cache_clear()


# ----------------------------------------------------------------------------- cache
def _key(**kw) -> str:
    return hashlib.sha1(json.dumps(kw, sort_keys=True, default=str).encode()).hexdigest()[:16]


def cache_get(key: str):
    f = CACHE_DIR / f"{key}.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            return None
    return None


def cache_put(key: str, obj: dict):
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(clean_json(obj)))


def cache_clear():
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()


def list_runs(dataset: str | None = None) -> list[dict]:
    """Cached causal runs belonging to the active data set only.

    The run cache is shared on disk, so without this filter a run computed on the
    synthetic demo appears in REAL mode (and vice versa). Runs written before this
    carried no data-set tag, so membership is also checked against the active data
    set's own well ids — that keeps legacy runs from leaking across data modes.
    """
    try:
        ds = get_context().ds
        active = dataset or ds.name
        known = set(ds.wells.well_id.astype(str))
    except Exception:
        active, known = dataset, None
    out = []
    for f in sorted(CACHE_DIR.glob("run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        tagged = d.get("dataset")
        if tagged and active and tagged != active:
            continue
        well = str(d.get("well_id"))
        if not tagged and known is not None and well not in known:
            continue
        out.append({"analysis_id": d.get("analysis_id"), "well_id": d.get("well_id"), "model": d.get("model"), "confidence": d.get("confidence"), "kind": d.get("meta", {}).get("kind"),
                    "mean_effect_bpd": d.get("mean_effect_bpd"), "donor_count": d.get("diagnostics", {}).get("donor_count"), "created_at": d.get("created_at"), "event_label": d.get("event_label")})
    return out[:300]


def analysis(ctx: Context, well_id: str, pre_end: int, post_start: int, *, model: str | None = None, pre_window: int | None = None, post_window: int | None = None,
             exclusions: list[str] | None = None, forced: list[str] | None = None, kind: str = "intervention", force: bool = False, progress=None,
             bootstrap: int | None = None, placebo_wells: int | None = None, event_label: str = "") -> dict:
    s = ctx.settings
    model = model or s["causal"]["default_model"]
    pre_window = pre_window or s["causal"]["pre_window"]
    post_window = post_window or s["causal"]["post_window"]
    key = "run_" + _key(ds=ctx.ds.meta.get("dataset_version"), w=well_id, pe=pre_end, ps=post_start, m=model, pw=pre_window, po=post_window, ex=sorted(exclusions or []), fo=sorted(forced or []),
                        c=s["causal"], conf=s["confidence"], mv=MODEL_VERSION, b=bootstrap, p=placebo_wells)
    if not force:
        hit = cache_get(key)
        if hit:
            return hit
    truth = None
    if ctx.ds.truth_events is not None:
        te = ctx.ds.truth_events
        m = te[(te.well_id == well_id) & (te.event_t == post_start)]
        if len(m):
            truth = clean_json(m.iloc[0].to_dict())
    res = causal.run_causal(ctx.ds, well_id, pre_end, post_start, model=model, pre_window=pre_window, post_window=post_window, settings=s, event_index=ctx.event_index,
                            exclusions=set(exclusions or []), forced_donors=forced, kind=kind, progress=progress, truth=truth, bootstrap=bootstrap, placebo_wells=placebo_wells)
    d = clean_json(res.to_dict())
    d["analysis_id"] = key
    d["event_label"] = event_label
    d["dataset"] = ctx.ds.name          # so a run can never surface under another data mode
    d["created_at"] = datetime.now(timezone.utc).isoformat()
    d["months"] = [ctx.ds.months[i] for i in d["pre_idx"] + d["post_idx"]]
    d["rel_months"] = [i - post_start for i in d["pre_idx"] + d["post_idx"]]
    d["days"] = [float(ctx.ds.days[i]) for i in d["pre_idx"] + d["post_idx"]]
    cache_put(key, d)
    return d


def events_for_well(ctx: Context, well_id: str) -> list[dict]:
    """All analysable events for a well: explicit interventions + observed restarts."""
    out = []
    ints = ctx.ds.interventions[ctx.ds.interventions.well_id == well_id]
    rs = ctx.restart_events[ctx.restart_events.well_id == well_id]
    restart_ts = set(rs.restart_t.tolist())
    for _, r in ints.iterrows():
        t = int(r.t)
        if t in restart_ts:
            rr = rs[rs.restart_t == t].iloc[0]
            out.append({"kind": "restart", "label": f"{r.type} (restart, recorded)", "pre_end": int(rr.shutin_t) - 1, "post_start": t, "intervention_id": r.intervention_id, "type": r.type, "cost": float(r.cost), "month": ctx.ds.months[t], "recorded": True})
        else:
            out.append({"kind": "intervention", "label": r.type, "pre_end": t - 1, "post_start": t, "intervention_id": r.intervention_id, "type": r.type, "cost": float(r.cost), "month": ctx.ds.months[t], "recorded": True})
    recorded_ts = {e["post_start"] for e in out}
    for _, rr in rs.iterrows():
        if int(rr.restart_t) not in recorded_ts:
            out.append({"kind": "restart", "label": "Observed restart event", "pre_end": int(rr.shutin_t) - 1, "post_start": int(rr.restart_t), "intervention_id": None, "type": "observed_restart", "cost": None, "month": ctx.ds.months[int(rr.restart_t)], "recorded": False})
    out.sort(key=lambda e: e["post_start"])
    return out


def all_events(ctx: Context) -> list[dict]:
    out = []
    for wid in ctx.ds.wells.well_id:
        for e in events_for_well(ctx, wid):
            out.append({"well_id": wid, **e})
    return out


def dataset_version(ctx: Context) -> str:
    return ctx.ds.meta.get("dataset_version", "?")
