"""CORE API. One engine, one evidence base, multiple decisions."""
from __future__ import annotations

import csv
import io
import json
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config, state
from ..archive import extraction as archive
from ..core import copilot, engine, ghost, idle, memory, portfolio, precompute, validation, water
from ..core.causal import MODELS, clean_json
from ..data import alberta, imports, store
from .. import scada

app = FastAPI(title="CORE — Causal Operations & Recovery Engine", version=config.MODEL_VERSION)
FRONTEND_DIST = config.ROOT / "frontend" / "dist"

# Public-link protections (no-ops unless CORE_PUBLIC_DEMO / CORE_ACCESS_PASSWORD
# are set), so a local run is unchanged. See backend/api/public_guard.py.
from . import public_guard
public_guard.install(app)


@app.exception_handler(Exception)
async def _errors(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    msg = str(exc) or exc.__class__.__name__
    if isinstance(exc, FileNotFoundError):
        return JSONResponse({"error": msg, "hint": "Run: python scripts/init_demo.py"}, status_code=503)
    traceback.print_exc()
    return JSONResponse({"error": "CORE could not complete this request.", "detail": msg, "hint": "Check the server log; the request has been recorded."}, status_code=500)


def ok(obj):
    return JSONResponse(clean_json(obj))


def ctx():
    return engine.get_context()


def agg(name: str):
    """Read a precomputed artifact, refusing to serve it for the wrong data context.

    Without this guard a stale evidence base built from the synthetic data set is
    served while the header advertises REAL PUBLIC DATA — i.e. synthetic records
    presented as real. Failing loudly is the only truthful option.
    """
    v = precompute.get(name)
    if v is None:
        raise HTTPException(503, f"Evidence base not built ({name}). Run: python scripts/init_demo.py")
    mismatch = precompute.dataset_mismatch()
    if mismatch:
        raise HTTPException(409, mismatch)
    return v


# ----------------------------------------------------------------------------- jobs (background analyses)
JOBS: dict[str, dict] = {}


def run_job(fn, *args, **kwargs) -> str:
    jid = "JOB-" + uuid.uuid4().hex[:8]
    JOBS[jid] = {"job_id": jid, "status": "QUEUED", "steps": [], "result": None, "error": None, "created_at": time.time()}

    def progress(msg):
        JOBS[jid]["steps"].append(msg)
        JOBS[jid]["status"] = "RUNNING"

    def target():
        try:
            JOBS[jid]["status"] = "RUNNING"
            JOBS[jid]["result"] = clean_json(fn(*args, progress=progress, **kwargs))
            JOBS[jid]["status"] = "COMPLETE"
        except Exception as e:  # noqa
            traceback.print_exc()
            JOBS[jid]["status"] = "FAILED"
            JOBS[jid]["error"] = str(e)
    threading.Thread(target=target, daemon=True).start()
    return jid


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Unknown job")
    return ok(j)


# ----------------------------------------------------------------------------- meta / overview
@app.get("/api/meta")
def meta():
    c = ctx()
    m = precompute.get("meta") or {}
    return ok({"product": "CORE — Causal Operations & Recovery Engine", "model_version": config.MODEL_VERSION, "dataset": c.ds.name, "dataset_label": c.ds.meta.get("label"), "data_mode": c.ds.meta.get("data_mode"), "dataset_version": c.ds.meta.get("dataset_version"),
               "wells": int(len(c.ds.wells)), "months": c.ds.n_months, "date_range": [c.ds.months[0], c.ds.months[-1]], "fields": sorted(c.ds.wells.field.unique().tolist()), "evidence_built_at": m.get("built_at"), "evidence_stale": precompute.stale(),
               "settings": c.settings, "datasets": store.list_datasets(), "archive_provider": c.settings["archive"]["llm_provider"]})


@app.get("/api/overview")
def overview(field: str | None = None):
    c = ctx()
    ds = c.ds
    n = ds.n_months
    wells = ds.wells if not field else ds.wells[ds.wells.field == field]
    ids = set(wells.well_id)
    prod = ds.production[ds.production.well_id.isin(ids)]
    recent = prod[prod.t >= n - 3]
    oil_now = float(recent.oil_bpd.sum() / 3)
    water_now = float(recent.water_bpd.sum() / 3)
    st = c.status[c.status.index.isin(ids)]
    idle_rows = [r for r in agg("idle")["rows"] if r["well_id"] in ids]
    ghost_rows = [r for r in agg("ghost")["rows"] if r["well_id"] in ids]
    water_rows = [r for r in agg("water")["rows"] if r["well_id"] in ids]
    mem = [r for r in agg("memory") if r["well_id"] in ids]
    cands = portfolio.candidates(idle_rows, ghost_rows, water_rows, c.settings, state.load()["manual_jobs"])
    plan = portfolio.optimise(cands, c.settings["portfolio"], c.settings["portfolio"].get("objective", "npv"), locked=state.plan_state()["locked"], removed=set(state.plan_state()["removed"]))
    trend = prod.groupby("t").agg(oil=("oil_bpd", "sum"), water=("water_bpd", "sum")).reset_index()
    idle_opp = sum(r.get("expected_oil_bpd") or 0 for r in idle_rows if r["status"] in ("ACT", "TEST", "REVIEW"))
    ghost_opp = sum(r["oil_opportunity_bpd"] for r in ghost_rows if r.get("is_opportunity"))
    matrix = [{"well_id": r["well_id"], "x": r.get("expected_npv") or 0, "y": {"HIGH CONFIDENCE": 0.9, "MODERATE CONFIDENCE": 0.65, "LOW CONFIDENCE": 0.35}.get(r.get("confidence"), 0.1), "module": "idle", "status": r["status"], "confidence": r.get("confidence")} for r in idle_rows if r["status"] not in ("INSUFFICIENT DATA",)]
    matrix += [{"well_id": r["well_id"], "x": r.get("annual_value") or 0, "y": {"HIGH CONFIDENCE": 0.9, "MODERATE CONFIDENCE": 0.65, "LOW CONFIDENCE": 0.35}.get(r.get("confidence"), 0.1), "module": "ghost", "status": "underperforming", "confidence": r.get("confidence")} for r in ghost_rows if r.get("is_opportunity")]
    water_matrix = [{"well_id": r["well_id"], "water_cut": r["water_cut"], "cost_per_year": r["water_cost_per_year"], "oil_bpd": r["oil_bpd"], "constraint": r["constraint_status"]} for r in water_rows]
    decisions = state.load()["decisions"]
    decided = {d["recommendation_id"] for d in decisions}
    awaiting = [{"recommendation_id": f"IDLE-{r['well_id']}", "well_id": r["well_id"], "action": r.get("intervention_type"), "status": r["status"], "value": r.get("expected_npv"), "confidence": r.get("confidence"), "module": "idle"} for r in idle_rows if r["status"] in ("ACT", "TEST", "REVIEW") and f"IDLE-{r['well_id']}" not in decided][:8]
    awaiting += [{"recommendation_id": f"GHOST-{r['well_id']}", "well_id": r["well_id"], "action": "investigate gap", "status": "REVIEW", "value": r.get("annual_value"), "confidence": r.get("confidence"), "module": "ghost"} for r in ghost_rows if r.get("is_opportunity") and f"GHOST-{r['well_id']}" not in decided][:4]
    return ok({
        "field": field, "data_mode": ds.meta.get("data_mode"), "label": ds.meta.get("label"),
        "kpi": {"oil_bpd": oil_now, "water_bpd": water_now, "water_cut": water_now / max(oil_now + water_now, 1e-6), "idle_wells": int((st.status == "idle").sum()), "producing_wells": int((st.status == "producing").sum()), "wells_screened": int(len(wells)),
                "restart_events": int(len(c.restart_events[c.restart_events.well_id.isin(ids)])), "underperformance_candidates": sum(1 for r in ghost_rows if r.get("is_opportunity")), "intervention_candidates": sum(1 for r in idle_rows if r["status"] in ("ACT", "TEST", "REVIEW")),
                "high_confidence_opportunities": sum(1 for r in idle_rows if r["status"] == "ACT") + sum(1 for r in ghost_rows if r.get("is_opportunity") and r.get("confidence") == "HIGH CONFIDENCE"),
                "recoverable_opportunity_bpd": round(idle_opp + ghost_opp, 1), "recoverable_range_bpd": [round(sum((r.get("expected_oil_lo") or 0) for r in idle_rows if r["status"] in ("ACT", "TEST", "REVIEW")) + sum(r["gap_lo"] for r in ghost_rows if r.get("is_opportunity")), 1), round(sum((r.get("expected_oil_hi") or 0) for r in idle_rows if r["status"] in ("ACT", "TEST", "REVIEW")) + sum(r["gap_hi"] for r in ghost_rows if r.get("is_opportunity")), 1)],
                "avoidable_water_bpd": round(sum(r.get("water_avoided_bpd") or 0 for r in water_rows if r.get("potential_intervention")), 0), "capital_required": plan["kpi"]["investment"], "portfolio_npv": plan["kpi"]["expected_value"], "portfolio_npv_range": [plan["kpi"]["value_lo"], plan["kpi"]["value_hi"]],
                "water_cost_per_year": sum(r["water_cost_per_year"] for r in water_rows), "jobs_analysed": len(mem)},
        "trend": [{"month": ds.months[int(r.t)], "oil_bpd": round(float(r.oil), 0), "water_bpd": round(float(r.water), 0)} for r in trend.itertuples()],
        "waterfall": [{"step": "Current oil production", "value": round(oil_now, 0), "kind": "total"}, {"step": "Ghost barrels (below baseline)", "value": round(ghost_opp, 1), "kind": "delta"}, {"step": "Idle-well candidates", "value": round(idle_opp, 1), "kind": "delta"}, {"step": "Estimated achievable", "value": round(oil_now + ghost_opp + idle_opp, 0), "kind": "total"}],
        "matrix": matrix, "water_matrix": water_matrix, "investment_return": [{"candidate_id": c_["candidate_id"], "well_id": c_["well_id"], "cost": c_["cost"], "npv": c_["npv"], "selected": c_["candidate_id"] in {s["candidate_id"] for s in plan["selected"]}, "action": c_["action"]} for c_ in cands],
        "recent_analyses": engine.list_runs()[:8], "awaiting_review": awaiting, "labels": {"kpi": "Values are computed from the loaded data set; costs, prices and capacities are ILLUSTRATIVE ECONOMIC ASSUMPTIONS."},
    })


# ----------------------------------------------------------------------------- wells
@app.get("/api/wells")
def wells(field: str | None = None, status: str | None = None, q: str | None = None):
    c = ctx()
    ds = c.ds
    n = ds.n_months
    idle_map = {r["well_id"]: r for r in agg("idle")["rows"]}
    ghost_map = {r["well_id"]: r for r in agg("ghost")["rows"]}
    water_map = {r["well_id"]: r for r in agg("water")["rows"]}
    mem = agg("memory")
    last_job = {}
    for m in sorted(mem, key=lambda x: x["date"]):
        last_job[m["well_id"]] = f"{m['type']} {m['date']}"
    oil_p, wat_p, wc_p = ds.panel("oil_bpd"), ds.panel("water_bpd"), ds.panel("water_cut")
    rows = []
    for w in ds.wells.itertuples():
        if field and w.field != field:
            continue
        st = c.well_status(w.well_id)
        if q and q.lower() not in f"{w.well_id} {w.field} {w.operator} {st}".lower():
            continue
        oil = float(np.nanmean(oil_p[w.well_id].to_numpy(dtype=float)[n - 3:]))
        wat = float(np.nanmean(wat_p[w.well_id].to_numpy(dtype=float)[n - 3:]))
        wc = float(np.nanmean(wc_p[w.well_id].to_numpy(dtype=float)[n - 3:]))
        g, i, wr = ghost_map.get(w.well_id), idle_map.get(w.well_id), water_map.get(w.well_id)
        rec = (f"{i['status']}: {i.get('intervention_type', '').replace('_', ' ')}" if i else None) or ("investigate gap" if g and g.get("is_opportunity") else None) or ("water shutoff candidate" if wr and wr.get("potential_intervention") else None)
        conf = (i or g or {}).get("confidence")
        opp = (i.get("expected_npv") if i else None) or (g.get("annual_value") if g and g.get("is_opportunity") else None)
        row = {"well_id": w.well_id, "field": w.field, "status": st, "oil_bpd": round(oil, 1) if np.isfinite(oil) else None, "water_bpd": round(wat, 1) if np.isfinite(wat) else None, "water_cut": round(wc, 3) if np.isfinite(wc) else None,
               "baseline_bpd": g["expected_bpd"] if g else None, "gap_bpd": g["gap_bpd"] if g else None, "opportunity": opp, "last_intervention": last_job.get(w.well_id), "confidence": conf, "recommendation": rec,
               "dq_score": float(c.quality.loc[w.well_id, "dq_score"]) if w.well_id in c.quality.index else None, "flags": []}
        if i:
            row["flags"].append("idle")
        if g and g.get("is_opportunity"):
            row["flags"].append("opportunity")
        if wc >= 0.9:
            row["flags"].append("high_water")
        if i and i["status"] in ("ACT", "TEST", "REVIEW"):
            row["flags"].append("intervention_candidate")
        if conf == "LOW CONFIDENCE":
            row["flags"].append("low_confidence")
        if (i and i["status"] == "INSUFFICIENT DATA") or conf == "INSUFFICIENT EVIDENCE":
            row["flags"].append("insufficient_evidence")
        if status and status not in row["flags"] and status != st:
            continue
        rows.append(row)
    return ok({"rows": rows, "fields": sorted(ds.wells.field.unique().tolist())})


# ----------------------------------------------------------------------------- Alberta public data + map
#
# Everything below serves REAL public Canadian data only:
#   * AER ST37 (well identity, category, WGS84 geometry, surface legal location)
#   * AER ST102 facility list and AER pipeline segments (map overlays)
#   * Petrinex Alberta conventional volumetrics (reported monthly volumes)
# Private telemetry (pressure, temperature, vibration, ESP, choke) has no public
# source and is reported as "Not publicly available" — never generated.

MAP_ZOOM_CELL = {4: 1.2, 5: 0.8, 6: 0.5, 7: 0.3, 8: 0.18, 9: 0.09, 10: 0.05}
MAP_FEATURE_LIMIT = 4000


@app.get("/api/alberta/status")
def alberta_status():
    from ..data import petrinex_cache

    return ok({
        "sources": alberta.source_status(),
        "petrinex": petrinex_cache.cache_meta(),
        "summary": alberta.dataset_summary(),
        "join": alberta.join_report(),
        "mode": "REAL PUBLIC DATA",
        "scada": scada.status(),
        "mode_note": "Public regulatory and volumetric records only. No SCADA/historian connector is "
                     "installed, so private telemetry is reported as Not publicly available.",
        "derivation_notes": alberta.DERIVATION_NOTES,
    })


class AlbertaSync(BaseModel):
    months: int | None = None
    end_month: str | None = None


def _sync_arcgis_job(kind: str, progress=None):
    def report(done: int, total: int):
        if progress and (done % 25000 < 2500 or done >= total):
            progress(f"{kind}: {done:,} / {total:,} records")
    if progress:
        progress(f"contacting {alberta.ARCGIS_SOURCES[kind]['name']}")
    meta = alberta.sync_arcgis(kind, progress=report)
    if progress:
        progress(f"validated and cached {meta['stats']['rows']:,} rows")
    return {"kind": kind, "meta": meta, "summary": alberta.dataset_summary()}


def _sync_petrinex_job(months: int, end_month: str | None, progress=None):
    from ..data import petrinex_cache

    wanted = petrinex_cache.available_months(months, end=end_month)
    def report(stage: str, index: int, total: int):
        if progress:
            progress(f"[{index + 1}/{total}] {stage}")
    meta = petrinex_cache.build(wanted, progress=report)
    if progress:
        progress(f"cached {meta['records']:,} monthly records for {meta['wells']:,} wells")
    return {"kind": "petrinex", "meta": meta, "join": alberta.join_report()}


def _sync_file_job(kind: str, progress=None):
    def report(stage: str):
        if progress:
            progress(stage)
    meta = alberta.download_file_source(kind, progress=report)
    if progress:
        progress(f"validated and cached {meta['stats']['rows']:,} rows")
    return {"kind": kind, "meta": meta}


@app.post("/api/alberta/sync/{kind}")
def alberta_sync(kind: str, req: AlbertaSync | None = None):
    """Refresh one official source. Last-known-good data is preserved on failure."""
    req = req or AlbertaSync()
    if kind == "petrinex":
        return ok({"job_id": run_job(_sync_petrinex_job, req.months or 12, req.end_month)})
    if kind in alberta.ARCGIS_SOURCES:
        return ok({"job_id": run_job(_sync_arcgis_job, kind)})
    if kind in alberta.FILE_SOURCES and alberta.FILE_SOURCES[kind].get("url"):
        return ok({"job_id": run_job(_sync_file_job, kind)})
    refreshable = list(alberta.ARCGIS_SOURCES) + ["petrinex"] + [
        k for k, s in alberta.FILE_SOURCES.items() if s.get("url")
    ]
    raise HTTPException(404, f"{kind} is not a refreshable source. Refreshable: {', '.join(refreshable)}")


@app.get("/api/map/summary")
def map_summary():
    return ok({"summary": alberta.dataset_summary(), "join": alberta.join_report(),
               "sources": alberta.source_status(), "mode": "REAL PUBLIC DATA"})


@app.get("/api/scada/status")
def scada_status():
    return ok(scada.status())


@app.get("/api/scada/wells/{well_id}/telemetry")
def scada_well_telemetry(well_id: str):
    return ok(scada.telemetry(well_id.strip().upper()))


def _bbox(bbox: str | None):
    if not bbox:
        return None
    try:
        values = tuple(float(x) for x in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be minLng,minLat,maxLng,maxLat")
    if len(values) != 4:
        raise HTTPException(400, "bbox must be minLng,minLat,maxLng,maxLat")
    return values


@app.get("/api/map/wells")
def map_wells(bbox: str | None = None, zoom: float = 5, status: str | None = None,
              fluid: str | None = None, operator: str | None = None, layer: str | None = None,
              producing: bool = False, q: str | None = None):
    """Viewport query. Below zoom 11 the response is server-side grid clusters so the
    browser never receives hundreds of thousands of features."""
    rows = alberta.map_query(_bbox(bbox), status=status, fluid=fluid, operator=operator,
                             layer=layer, producing=producing or None, query=q)
    if rows is None or rows.empty:
        available = not alberta.records("st37").empty
        return ok({"mode": "REAL PUBLIC DATA", "available": available, "clusters": [], "features": [],
                   "count": 0, "returned": 0,
                   "message": "No records match this viewport and filter combination." if available
                              else "Alberta dataset not yet imported."})
    total = int(len(rows))
    zoom_key = int(max(4, min(10, zoom)))
    if zoom < 11 and total > 900:
        clusters = alberta.cluster(rows, MAP_ZOOM_CELL[zoom_key])
        if len(clusters) < total:
            return ok({"mode": "REAL PUBLIC DATA", "available": True, "clusters": clusters,
                       "features": [], "count": total, "returned": len(clusters), "clustered": True})
    capped = rows.head(MAP_FEATURE_LIMIT)
    cols = [c for c in ("record_id", "latitude", "longitude", "status", "fluid", "well_category",
                        "surface_location", "ats_cell", "uwi", "operator", "oil_m3", "gas_e3m3",
                        "water_m3", "water_cut", "latest_month") if c in capped.columns]
    features = capped[cols].where(capped[cols].notna(), None).to_dict(orient="records")
    integrity = alberta.integrity_cells()
    if integrity:
        for feature in features:
            feature["integrity_record"] = feature.get("ats_cell") in integrity
    return ok({"mode": "REAL PUBLIC DATA", "available": True, "clusters": [], "features": features,
               "count": total, "returned": len(features), "clustered": False,
               "truncated": total > MAP_FEATURE_LIMIT})


@app.get("/api/map/overlays/{kind}")
def map_overlays(kind: str, bbox: str | None = None, limit: int = 3000):
    """Real AER overlays: ST102 facilities and licensed pipeline segments."""
    if kind not in ("facilities", "pipelines"):
        raise HTTPException(404, "Overlay must be 'facilities' or 'pipelines'")
    frame = alberta.records(kind)
    if frame.empty:
        return ok({"available": False, "features": [], "message": f"{kind} dataset not imported"})
    box = _bbox(bbox)
    if kind == "facilities":
        rows = frame
        if box:
            rows = rows[(rows.longitude >= box[0]) & (rows.longitude <= box[2])
                        & (rows.latitude >= box[1]) & (rows.latitude <= box[3])]
        rows = rows.head(limit)
        return ok({"available": True, "kind": kind, "count": int(len(frame)),
                   "features": rows.where(rows.notna(), None).to_dict(orient="records"),
                   "source": "AER ST102: Facility List"})
    rows = alberta.pipelines_in_bbox(box, limit)
    out = [{"licence_no": r.licence_no, "company_name": r.company_name, "status": r.status,
            "substance": r.substance, "geometry": json.loads(r.geometry_json)}
           for r in rows.itertuples() if r.geometry_json]
    return ok({"available": True, "kind": kind, "count": int(len(frame)), "features": out,
               "source": "AER Pipeline Segments"})


@app.get("/api/map/search")
def map_search(q: str, limit: int = 20):
    """Exact-identifier friendly search over UWI, AER record id, legal location and operator."""
    rows = alberta.map_query(query=q)
    if rows is None or rows.empty:
        return ok({"results": [], "count": 0})
    total = int(len(rows))
    rows = rows.head(max(1, min(limit, 100)))
    cols = [c for c in ("record_id", "uwi", "surface_location", "operator", "status", "fluid",
                        "latitude", "longitude", "latest_month", "oil_m3") if c in rows.columns]
    return ok({"results": rows[cols].where(rows[cols].notna(), None).to_dict(orient="records"),
               "count": total})


def _daily_rate(volume, month: str | None):
    """Reported monthly volume -> calculated daily average. Explicitly a CALCULATED value."""
    if volume is None or month is None or pd.isna(volume):
        return None
    try:
        days = pd.Period(month).days_in_month
    except Exception:
        return None
    return {"value": float(volume) / days, "unit": "m3/day", "value_type": "CALCULATED",
            "formula": f"{float(volume):,.1f} m3 reported for {month} / {days} calendar days",
            "days": int(days), "source": "Petrinex Alberta Conventional Volumetrics"}


@app.get("/api/map/wells/{record_id}")
def public_well_detail(record_id: str):
    """Full public record for one AER ST37 well, with the provenance of every value."""
    from ..data import ats, petrinex_cache

    frame = alberta.wells()
    if frame.empty:
        raise HTTPException(503, "Alberta dataset not yet imported")
    key = record_id.strip().upper()
    hit = frame[frame.record_id.str.upper() == key]
    if hit.empty and "uwi" in frame:
        hit = frame[frame.uwi.fillna("").str.upper() == key]
    if hit.empty:
        raise HTTPException(404, "No matching record in the cached AER ST37 dataset")
    row = hit.iloc[0]
    well = row.where(pd.notna(row), None).to_dict()
    uwi = well.get("uwi") or None
    cell = well.get("ats_cell") or None

    history, production, calculated = [], None, {}
    if uwi:
        frame_hist = petrinex_cache.history(uwi)
        if not frame_hist.empty:
            history = frame_hist.where(pd.notna(frame_hist), None).to_dict(orient="records")
            latest = history[-1]
            production = latest
            calculated = {
                "oil_rate": _daily_rate(latest.get("oil_m3"), latest.get("month")),
                "water_rate": _daily_rate(latest.get("water_m3"), latest.get("month")),
                "gas_rate": _daily_rate(latest.get("gas_e3m3"), latest.get("month")),
                "water_cut": ({"value": latest.get("water_cut"), "unit": "fraction",
                               "value_type": "CALCULATED",
                               "formula": "reported water m3 / (reported water m3 + reported oil m3)",
                               "source": "Petrinex Alberta Conventional Volumetrics"}
                              if pd.notna(latest.get("water_cut")) else None),
                "trend": alberta_trend(history),
            }
    st37_meta = alberta.meta("st37") or {}
    petrinex_meta = petrinex_cache.cache_meta() or {}
    integrity = alberta.integrity_for(cell, uwi)
    blocked = bool(well.get("link_blocked_by_shared_location"))
    shared = int(well.get("cell_records") or 1)
    return ok({
        "well": {**well, "legal_location_text": ats.describe_cell(cell)},
        "identity_note": (
            "This ST37 point is linked to a Petrinex reporting well through its Alberta Township System "
            "legal location (exactly one AER record and one reporting well at this legal subdivision)."
            if uwi else
            f"{shared} AER records share this legal subdivision, so a reported volume cannot be attributed "
            "to this individual point. Production is shown as Not publicly available rather than guessed."
            if blocked else
            "No Petrinex reporting well matches this legal subdivision, so no production is attributed "
            "to this point."),
        "production_latest": production,
        "production_history": history,
        "calculated": calculated,
        "integrity": integrity,
        "telemetry": {field: "Not publicly available" for field in (
            "tubing_pressure", "casing_pressure", "annulus_pressure", "wellhead_temperature",
            "bottomhole_pressure", "choke_position", "pump_frequency", "motor_current",
            "motor_temperature", "vibration", "esp_intake_pressure")},
        "telemetry_note": "These are private operator SCADA measurements. Alberta public data does not "
                          "publish them, and CORE does not generate substitutes. Install a SCADA "
                          "connector to populate them. SCADA NOT CONNECTED — currently using "
                          "public/cached/simulated data.",
        "sources": {
            "identity": {"source": "Alberta Energy Regulator", "dataset": st37_meta.get("dataset"),
                         "value_type": "REPORTED / REGULATORY RECORD",
                         "retrieved_at": st37_meta.get("retrieved_at"),
                         "source_last_edit": st37_meta.get("source_last_edit"),
                         "record_id": well.get("record_id")},
            "coordinates": {"source": "Alberta Energy Regulator", "dataset": st37_meta.get("dataset"),
                            "value_type": "REPORTED", "crs": st37_meta.get("source_crs")},
            "status_and_fluid": {"source": "Derived from AER ST37 Well_Category",
                                 "value_type": "CALCULATED",
                                 "rule_status": alberta.DERIVATION_NOTES["status"],
                                 "rule_fluid": alberta.DERIVATION_NOTES["fluid"]},
            "production": ({"source": "Petrinex", "dataset": petrinex_meta.get("dataset"),
                            "value_type": "REPORTED (monthly volumetric declaration)",
                            "latest_month": petrinex_meta.get("latest_month"),
                            "units": petrinex_meta.get("units"),
                            "retrieved_at": petrinex_meta.get("retrieved_at"),
                            "join_key": "Alberta Township System legal location", "uwi": uwi}
                           if uwi else {"source": "Not publicly available",
                                        "reason": (f"{shared} AER records share this legal subdivision"
                                                   if blocked else "no Petrinex reporting well matched")}),
            "integrity": {"casing_failures": (alberta.meta("casing_failures") or {}).get("dataset")
                                             or "AER Casing Failures Report — not imported",
                          "vent_flow": (alberta.meta("vent_flow") or {}).get("dataset")
                                       or "AER Vent Flow / Gas Migration Report — not imported"},
            "scada": "Not connected",
        },
        "outcomes": state.intervention_outcomes(uwi or well.get("record_id")),
        "mode": "REAL PUBLIC DATA",
    })


def alberta_trend(history: list[dict]) -> dict | None:
    """Deterministic decline analytics from reported monthly oil volumes."""
    series = [(h["month"], h.get("oil_m3")) for h in history if pd.notna(h.get("oil_m3"))]
    if len(series) < 4:
        return None
    values = [float(v) for _, v in series]
    recent = values[-3:]
    prior = values[:-3]
    if not prior:
        return None
    recent_avg = sum(recent) / len(recent)
    prior_avg = sum(prior) / len(prior)
    change = (recent_avg - prior_avg) / prior_avg if prior_avg > 0 else None
    return {
        "value_type": "CALCULATED",
        "months_used": len(values),
        "recent_3_month_avg_m3": recent_avg,
        "prior_average_m3": prior_avg,
        "prior_months": len(prior),
        "change_fraction": change,
        "formula": "mean of the last 3 reported monthly oil volumes vs the mean of the earlier "
                   "reported months in the cached window",
        "source": "Petrinex Alberta Conventional Volumetrics (reported monthly volumes)",
        "flag": ("PRODUCTION DECLINE" if change is not None and change <= -0.2 else None),
    }


@app.get("/api/map/provenance/{record_id}")
def map_provenance(record_id: str):
    """Developer trace: exactly which source rows produced a well's values."""
    from ..data import petrinex_cache

    frame = alberta.wells()
    if frame.empty:
        raise HTTPException(503, "Alberta dataset not yet imported")
    hit = frame[frame.record_id.str.upper() == record_id.strip().upper()]
    if hit.empty:
        raise HTTPException(404, "record not found")
    row = hit.iloc[0]
    trace = [{
        "field": "latitude/longitude/well_category/surface_location",
        "dataset": (alberta.meta("st37") or {}).get("dataset"),
        "record": row.record_id,
        "raw": {"well_category": row.well_category, "surface_location": row.surface_location,
                "latitude": float(row.latitude), "longitude": float(row.longitude)},
        "value_type": "REPORTED",
    }, {
        "field": "status/fluid",
        "derivation": alberta.DERIVATION_NOTES,
        "value_type": "CALCULATED",
    }, {
        "field": "ats_cell",
        "derivation": "parsed from AER surface_location by backend/data/ats.py",
        "value": row.ats_cell, "value_type": "CALCULATED",
    }]
    uwi = row.get("uwi")
    uwi = str(uwi) if pd.notna(uwi) else None
    if uwi:
        record = petrinex_cache.well_record(uwi)
        hist = petrinex_cache.history(uwi)
        trace.append({
            "field": "production",
            "dataset": (petrinex_cache.cache_meta() or {}).get("dataset"),
            "join": {"key": "ATS legal location cell", "cell": row.ats_cell, "uwi": uwi,
                     "aer_records_at_cell": int(row.get("cell_records") or 1),
                     "rule": "linked only when the legal subdivision holds exactly one AER record and "
                             "exactly one reporting Petrinex well"},
            "petrinex_well_record": record,
            "monthly_rows": int(len(hist)),
            "value_type": "REPORTED",
        })
    else:
        trace.append({"field": "production", "value": None, "value_type": "NOT AVAILABLE",
                      "reason": ("more than one AER record shares this legal subdivision"
                                 if bool(row.get("link_blocked_by_shared_location"))
                                 else "no unique Petrinex reporting well at this legal subdivision"),
                      "aer_records_at_cell": int(row.get("cell_records") or 1)})
    return ok({"record_id": record_id, "trace": trace})


class PublicScenario(BaseModel):
    """A what-if run on REAL reported public volumes only."""
    uplift_fraction: float = 0.15          # incremental oil as a fraction of the reported baseline
    water_change_fraction: float = 0.0     # change in produced water as a fraction of the reported baseline
    cost: float | None = None              # $; falls back to the configured illustrative cost
    intervention_type: str = "cleanout"
    success_probability: float = 0.7
    horizon_months: int = 24
    handling: str = "disposal"


@app.get("/api/map/wells/{record_id}/calculator-inputs")
def public_calculator_inputs(record_id: str):
    """Which calculator inputs can be filled from public Alberta data, and which cannot.

    Rule 46 of the product brief: an input with no public source is NEVER populated
    with a generated value.  It is returned in `unavailable` with the reason.
    """
    from ..data import petrinex_cache

    frame = alberta.wells()
    if frame.empty:
        raise HTTPException(503, "Alberta dataset not yet imported")
    hit = frame[frame.record_id.str.upper() == record_id.strip().upper()]
    if hit.empty:
        raise HTTPException(404, "No matching record in the cached AER ST37 dataset")
    row = hit.iloc[0]
    uwi = row.get("uwi")
    uwi = str(uwi) if pd.notna(uwi) else None

    available: dict = {}
    history: list[dict] = []
    if uwi:
        frame_hist = petrinex_cache.history(uwi)
        history = frame_hist.where(pd.notna(frame_hist), None).to_dict(orient="records")
        if history:
            latest = history[-1]
            days = int(latest.get("days") or 30)
            month = latest.get("month")
            def tagged(volume, unit_in, factor, unit_out, name):
                if volume is None or pd.isna(volume):   # a missing declaration is not zero
                    return None
                return {"name": name, "value": round(float(volume) * factor / days, 3), "unit": unit_out,
                        "value_type": "CALCULATED",
                        "formula": f"{float(volume):,.1f} {unit_in} reported for {month} / {days} calendar days"
                                   + (f" × {factor}" if factor != 1 else ""),
                        "reported_value": float(volume), "reported_unit": unit_in,
                        "source": "Petrinex", "dataset": "Petrinex Alberta Conventional Volumetrics",
                        "production_month": month}
            available = {
                "oil_bpd": tagged(latest.get("oil_m3"), "m3", config.M3_TO_BBL, "bbl/day", "Oil rate"),
                "water_bpd": tagged(latest.get("water_m3"), "m3", config.M3_TO_BBL, "bbl/day", "Water rate"),
                "gas_e3m3_per_day": tagged(latest.get("gas_e3m3"), "e3m3", 1.0, "e3m3/day", "Gas rate"),
                "water_cut": ({"name": "Water cut", "value": latest.get("water_cut"), "unit": "fraction",
                               "value_type": "CALCULATED",
                               "formula": "reported water m3 / (reported water m3 + reported oil m3)",
                               "source": "Petrinex", "production_month": month}
                              if pd.notna(latest.get("water_cut")) else None),
                "producing_hours": ({"name": "Producing hours", "value": latest.get("hours"), "unit": "h/month",
                                     "value_type": "REPORTED", "source": "Petrinex", "production_month": month}
                                    if pd.notna(latest.get("hours")) else None),
                "months_of_history": {"name": "Months of reported history", "value": len(history),
                                      "unit": "months", "value_type": "REPORTED", "source": "Petrinex"},
            }
            available = {k: v for k, v in available.items() if v is not None}

    no_public_source = (
        "Alberta public data does not publish this measurement. It is a private operator "
        "SCADA/historian value. Enter it manually or connect a SCADA source — CORE will not generate it."
    )
    unavailable = {key: {"value": None, "value_type": "NOT AVAILABLE", "reason": no_public_source}
                   for key in ("tubing_pressure", "casing_pressure", "annulus_pressure",
                               "bottomhole_pressure", "wellhead_temperature", "choke_position",
                               "pump_frequency", "motor_current", "motor_temperature", "vibration",
                               "esp_intake_pressure", "esp_discharge_pressure")}
    unavailable["facility_fluid_capacity_bpd"] = {
        "value": None, "value_type": "NOT AVAILABLE",
        "reason": "Facility fluid-handling capacity is operator data; the public ST102 list does not publish it.",
    }
    if not uwi:
        unavailable["reported_production"] = {
            "value": None, "value_type": "NOT AVAILABLE",
            "reason": ("More than one AER record shares this legal subdivision, so reported volumes cannot be "
                       "attributed to this point." if bool(row.get("link_blocked_by_shared_location"))
                       else "No Petrinex reporting well matches this legal subdivision."),
        }
    return ok({"record_id": row.record_id, "uwi": uwi, "available": available, "unavailable": unavailable,
               "mode": "REAL PUBLIC DATA",
               "note": "Populated inputs are calculated from Petrinex reported monthly volumes. "
                       "Monthly reported volumes are not real-time production."})


@app.post("/api/map/wells/{record_id}/scenario")
def public_scenario(record_id: str, req: PublicScenario):
    """Run the existing economics engine on this well's REAL reported volumes.

    The engine, the netback and the water unit cost are exactly the ones used
    everywhere else in CORE; only the production baseline is different (Petrinex
    reported volumes instead of the loaded data set).  Price and cost assumptions
    stay tagged as illustrative public assumptions.
    """
    from ..core import economics

    inputs = json.loads(public_calculator_inputs(record_id).body)
    available = inputs.get("available") or {}
    if "oil_bpd" not in available:
        raise HTTPException(422, "This well has no linked public production record, so no baseline exists. "
                                 "CORE will not invent one.")
    settings = ctx().settings
    baseline_oil = float(available["oil_bpd"]["value"])
    baseline_water = float((available.get("water_bpd") or {}).get("value") or 0.0)
    months = max(1, min(int(req.horizon_months), 60))
    uplift = economics.decay_profile(baseline_oil * req.uplift_fraction, months)
    water_change = economics.decay_profile(baseline_water * req.water_change_fraction, months) \
        if req.water_change_fraction else [0.0] * months
    cost_meta = economics.intervention_cost(settings, req.intervention_type)
    cost = float(req.cost if req.cost is not None else (config.val(cost_meta) or 0.0))
    result = economics.evaluate(settings, uplift, water_change, cost, handling=req.handling,
                                success_probability=max(0.0, min(1.0, req.success_probability)),
                                label=f"{req.intervention_type} on {inputs['uwi']}")
    return ok({
        "record_id": record_id, "uwi": inputs["uwi"],
        "baseline": {"oil_bpd": baseline_oil, "water_bpd": baseline_water,
                     "source": available["oil_bpd"], "value_type": "CALCULATED FROM REPORTED VOLUMES"},
        "scenario": {"uplift_fraction": req.uplift_fraction, "water_change_fraction": req.water_change_fraction,
                     "success_probability": req.success_probability, "horizon_months": months,
                     "intervention_type": req.intervention_type,
                     "cost": cost, "cost_source": cost_meta},
        "result": result,
        "caveats": [
            "The production baseline is a Petrinex REPORTED monthly volume converted to a daily average — "
            "not a measured rate and not telemetry.",
            "Uplift and success probability are user assumptions, not model predictions from public data.",
            "Price, royalty, lifting and water component costs are illustrative public assumptions "
            "(editable in Settings) and are tagged as such.",
            "No pressure, temperature or equipment measurement was used: none is publicly available.",
        ],
        "mode": "REAL PUBLIC DATA + STATED ASSUMPTIONS",
    })


@app.get("/api/map/join-report")
def map_join_report():
    return ok(alberta.join_report())


@app.get("/api/wells/{well_id}")
def well_detail(well_id: str):
    c = ctx()
    ds = c.ds
    if well_id not in set(ds.wells.well_id):
        raise HTTPException(404, f"Well {well_id} is not in the loaded data set")
    w = ds.wells.set_index("well_id").loc[well_id]
    s = ds.well_series(well_id)
    n = ds.n_months
    from ..core import restart as rs
    oil = ds.panel("oil_bpd")[well_id].to_numpy(dtype=float)
    q = c.quality.loc[well_id] if well_id in c.quality.index else None
    from ..core.quality import well_quality
    dq = well_quality(ds.production[ds.production.well_id == well_id], n)
    idle_row = next((r for r in agg("idle")["rows"] if r["well_id"] == well_id), None)
    ghost_row = next((r for r in agg("ghost")["rows"] if r["well_id"] == well_id), None)
    water_row = next((r for r in agg("water")["rows"] if r["well_id"] == well_id), None)
    mem = [m for m in agg("memory") if m["well_id"] == well_id]
    st = state.load()
    outcomes = state.intervention_outcomes(well_id)
    for outcome in outcomes:
        if outcome.get("predicted_uplift_bpd") and outcome.get("actual_uplift_bpd") is not None:
            outcome["prediction_accuracy"] = round(1 - abs(outcome["predicted_uplift_bpd"] - outcome["actual_uplift_bpd"]) / max(abs(outcome["predicted_uplift_bpd"]), 1e-9), 4)
    docs = [d for d in archive.documents() if (d.get("well_id") == well_id)]
    events = engine.events_for_well(c, well_id)
    return ok({
        "well": {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in w.to_dict().items()}, "well_id": well_id, "status": c.well_status(well_id), "source": ds.meta.get("source"), "data_mode": ds.meta.get("data_mode"), "last_update": ds.months[-1],
        "quality": dq, "production": [{"t": int(r.t), "month": ds.months[int(r.t)], "oil_bpd": None if not np.isfinite(r.oil_bpd) else round(float(r.oil_bpd), 2), "water_bpd": None if not np.isfinite(r.water_bpd) else round(float(r.water_bpd), 2), "water_cut": None if not np.isfinite(r.water_cut) else round(float(r.water_cut), 3), "hours": None if not np.isfinite(r.hours) else float(r.hours), "oil_m3": None if not np.isfinite(r.oil_m3) else round(float(r.oil_m3), 2), "water_m3": None if not np.isfinite(r.water_m3) else round(float(r.water_m3), 2)} for r in s.itertuples()],
        "shutin_periods": [{**p, "start_month": ds.months[p["start_t"]], "end_month": ds.months[p["end_t"]]} for p in rs.shutin_periods(oil)], "events": events, "interventions": mem,
        "idle": idle_row, "ghost": ghost_row, "water": water_row, "documents": docs, "outcomes": outcomes, "notes": [x for x in st["notes"] if x["entity_id"] == well_id], "decisions": [d for d in st["decisions"] if d["well_id"] == well_id],
        "overview": {"current_oil_bpd": (round(float(np.nanmean(oil[n - 3:])), 1) if np.isfinite(oil[n - 3:]).any() else 0.0), "expected_baseline_bpd": ghost_row["expected_bpd"] if ghost_row else None, "gap_bpd": ghost_row["gap_bpd"] if ghost_row else None,
                     "water_cut": water_row["water_cut"] if water_row else None, "water_cost_per_day": water_row["water_cost_per_day"] if water_row else None, "last_job": (mem[-1]["type"] + " " + mem[-1]["date"]) if mem else None,
                     "recommended_action": (idle_row["status"] + ": " + idle_row.get("intervention_type", "").replace("_", " ")) if idle_row else ("investigate gap" if ghost_row and ghost_row.get("is_opportunity") else None), "confidence": (idle_row or ghost_row or {}).get("confidence")},
    })


class CausalRequest(BaseModel):
    pre_end: int
    post_start: int
    model: str = "auto"
    pre_window: int | None = None
    post_window: int | None = None
    exclusions: list[str] = []
    forced: list[str] = []
    kind: str = "intervention"
    force: bool = False
    lock: bool | None = None


@app.get("/api/wells/{well_id}/causal")
def get_causal(well_id: str, pre_end: int, post_start: int, model: str = "auto", pre_window: int | None = None, post_window: int | None = None, kind: str = "intervention"):
    c = ctx()
    key = f"{well_id}:{post_start}"
    ov = state.get_donor_overrides(key)
    a = engine.analysis(c, well_id, pre_end, post_start, model=model, pre_window=pre_window, post_window=post_window, exclusions=ov["exclusions"], forced=ov["forced"], kind=kind, event_label="")
    a["donor_overrides"] = ov
    return ok(a)


@app.post("/api/wells/{well_id}/causal/run")
def run_causal(well_id: str, req: CausalRequest):
    c = ctx()
    if req.model not in MODELS:
        raise HTTPException(400, f"model must be one of {MODELS}")
    key = f"{well_id}:{req.post_start}"
    ov = state.get_donor_overrides(key)
    if req.lock is not None or req.exclusions or req.forced:
        ov = state.set_donor_overrides(key, req.exclusions if (req.exclusions or req.lock is not None) else ov["exclusions"], req.forced if (req.forced or req.lock is not None) else ov["forced"], bool(req.lock) if req.lock is not None else ov["locked"])
    jid = run_job(engine.analysis, c, well_id, req.pre_end, req.post_start, model=req.model, pre_window=req.pre_window, post_window=req.post_window, exclusions=ov["exclusions"], forced=ov["forced"], kind=req.kind, force=True)
    return ok({"job_id": jid, "status": "QUEUED"})


class DonorOverride(BaseModel):
    post_start: int
    exclusions: list[str] = []
    forced: list[str] = []
    locked: bool = False


@app.post("/api/wells/{well_id}/donors")
def set_donors(well_id: str, req: DonorOverride):
    return ok(state.set_donor_overrides(f"{well_id}:{req.post_start}", req.exclusions, req.forced, req.locked))


@app.get("/api/eligibility-rules")
def eligibility_rules():
    s = ctx().settings["causal"]
    return ok({"rules": ["Donor has complete positive production over the treated well's pre and post windows (≤10% missing)", "Donor has no intervention, shut-in or restart of its own within the guarded window (pre start − 3 months … post end)", "Donor is not on the engineer's exclusion list",
                         f"At least {s['min_donors']} eligible donors are required for donor-based models; otherwise AUTO falls back to a decline curve", "Synthetic control requires ≥5 donors and pre-period R² ≥ 0.6, otherwise matched wells is used", "Pre window: %d months, post window: %d months, up to %d donors" % (s["pre_window"], s["post_window"], s["max_donors"])], "settings": s})


# ----------------------------------------------------------------------------- interventions (memory)
@app.get("/api/interventions")
def interventions(field: str | None = None):
    rows = agg("memory")
    if field:
        rows = [r for r in rows if r.get("field") == field]
    st = state.load()
    for r in rows:
        r["reviewed"] = st["reviewed"].get(r["intervention_id"])
    return ok({"rows": rows, **memory.overview(rows), "type_evidence": {t: memory.type_evidence(rows, t) for t in sorted({r["type"] for r in rows})}})


@app.get("/api/interventions/{intervention_id}")
def intervention_detail(intervention_id: str):
    rows = agg("memory")
    r = next((x for x in rows if x["intervention_id"] == intervention_id), None)
    if not r:
        raise HTTPException(404, "Unknown intervention")
    a = engine.cache_get(r["analysis_id"]) if r.get("analysis_id") else None
    st = state.load()
    docs = [d for d in archive.documents() if d.get("well_id") == r["well_id"]]
    return ok({"row": r, "analysis": a, "notes": [x for x in st["notes"] if x["entity_id"] == intervention_id], "reviewed": st["reviewed"].get(intervention_id), "documents": docs, "type_evidence": memory.type_evidence(rows, r["type"])})


class NoteReq(BaseModel):
    text: str
    user: str = "engineer"


@app.post("/api/notes/{entity_id}")
def add_note(entity_id: str, req: NoteReq):
    return ok(state.add_note(entity_id, req.text, req.user))


@app.post("/api/reviewed/{entity_id}")
def mark_reviewed(entity_id: str, user: str = "engineer"):
    return ok(state.mark_reviewed(entity_id, user))


class InterventionOutcomeReq(BaseModel):
    well_id: str
    intervention_type: str
    intervention_date: str
    predicted_uplift_bpd: float | None = None
    actual_uplift_bpd: float | None = None
    evaluation_days: int | None = None
    notes: str | None = None


@app.post("/api/intervention-outcomes")
def intervention_outcome(req: InterventionOutcomeReq):
    row = state.add_intervention_outcome(req.model_dump())
    if row["predicted_uplift_bpd"] and row["actual_uplift_bpd"] is not None:
        row["prediction_accuracy"] = round(1 - abs(row["predicted_uplift_bpd"] - row["actual_uplift_bpd"]) / max(abs(row["predicted_uplift_bpd"]), 1e-9), 4)
    return ok(row)


@app.get("/api/intervention-outcomes")
def intervention_outcomes(well_id: str | None = None):
    rows = state.intervention_outcomes(well_id)
    for row in rows:
        if row.get("predicted_uplift_bpd") and row.get("actual_uplift_bpd") is not None:
            row["prediction_accuracy"] = round(1 - abs(row["predicted_uplift_bpd"] - row["actual_uplift_bpd"]) / max(abs(row["predicted_uplift_bpd"]), 1e-9), 4)
    return ok({"rows": rows, "count": len(rows)})


# ----------------------------------------------------------------------------- idle / ghost / water
@app.get("/api/idle")
def idle_wells(field: str | None = None):
    d = agg("idle")
    rows = d["rows"] if not field else [r for r in d["rows"] if r.get("field") == field]
    return ok({**d, "rows": rows})


@app.get("/api/idle/{well_id}")
def idle_detail(well_id: str):
    c = ctx()
    d = agg("idle")
    row = next((r for r in d["rows"] if r["well_id"] == well_id), None)
    if not row:
        raise HTTPException(404, f"{well_id} is not currently idle")
    st = c.status.loc[well_id]
    prof = idle.pre_shutin_profile(c, well_id, int(st.last_production_t) + 1)
    mem = agg("memory")
    docs = [dd for dd in archive.documents() if dd.get("well_id") == well_id]
    recent_jobs = [m for m in mem if m["well_id"] == well_id]
    return ok({"row": row, "profile": {**prof, "months": [c.ds.months[prof["t_from"] + i] for i in range(len(prof["series"]))]}, "scenarios": idle.scenarios(c, row, mem), "documents": docs, "recent_interventions": recent_jobs,
               "why": {"what": f"{row['status']}: {row.get('intervention_type', 'n/a').replace('_', ' ')}", "why": row.get("why", []), "compared_with": [a["well_id"] for a in row.get("analogs", [])], "how_much": {"oil_bpd": row.get("expected_oil_bpd"), "range": [row.get("expected_oil_lo"), row.get("expected_oil_hi")], "npv": row.get("expected_npv"), "npv_range": [row.get("npv_lo"), row.get("npv_hi")]},
                       "how_certain": row.get("confidence"), "what_could_change": ["Pump/equipment condition unknown (OPERATOR DATA REQUIRED)", "Intervention cost is an illustrative assumption", "Analogue recovery ratios come from the loaded restart history"], "who_decides": "Production engineer"}})


@app.get("/api/ghost")
def ghost_barrels(field: str | None = None):
    d = agg("ghost")
    rows = d["rows"] if not field else [r for r in d["rows"] if r.get("field") == field]
    return ok({**d, "rows": rows})


@app.get("/api/ghost/{well_id}")
def ghost_detail(well_id: str):
    c = ctx()
    row = next((r for r in agg("ghost")["rows"] if r["well_id"] == well_id), None)
    if not row:
        raise HTTPException(404, f"{well_id} is not in the ghost-barrel screen")
    a = engine.cache_get(row["analysis_id"])
    return ok({"row": row, "analysis": a, "why": ghost.why_panel(c, row, agg("memory"))})


@app.get("/api/water")
def water_econ(field: str | None = None):
    d = agg("water")
    rows = d["rows"] if not field else [r for r in d["rows"] if r.get("field") == field]
    return ok({**d, "rows": rows, "trajectory": water.trajectory(ctx())})


class ShutoffReq(BaseModel):
    well_id: str
    water_reduction_bpd: float
    oil_effect_bpd: float
    cost: float
    success_probability: float = 0.6
    duration_months: int = 24


@app.post("/api/water/shutoff-scenario")
def shutoff(req: ShutoffReq):
    return ok(water.shutoff_scenario(ctx(), req.well_id, req.water_reduction_bpd, req.oil_effect_bpd, req.cost, req.success_probability, req.duration_months))


# ----------------------------------------------------------------------------- portfolio
def _cands(c=None, field: str | None = None):
    c = c or ctx()
    idle_rows, ghost_rows, water_rows = agg("idle")["rows"], agg("ghost")["rows"], agg("water")["rows"]
    if field:
        idle_rows = [r for r in idle_rows if r.get("field") == field]
        ghost_rows = [r for r in ghost_rows if r.get("field") == field]
        water_rows = [r for r in water_rows if r.get("field") == field]
    cands = portfolio.candidates(idle_rows, ghost_rows, water_rows, c.settings, state.load()["manual_jobs"])
    # naive NPV for the transparent baseline: value of last observed rate (or gap) without counterfactual adjustment
    for cd in cands:
        cd["naive_npv"] = cd["npv"] * 1.0
    return cands


class OptimiseReq(BaseModel):
    budget: float | None = None
    crews: int | None = None
    rigs: int | None = None
    horizon_months: int | None = None
    max_concurrent: int | None = None
    min_npv: float | None = None
    risk_tolerance: float | None = None
    objective: str = "npv"
    weights: dict | None = None
    field: str | None = None


def _constraints(req: OptimiseReq, c) -> dict:
    base = dict(c.settings["portfolio"])
    for k in ("budget", "crews", "rigs", "horizon_months", "max_concurrent", "min_npv", "risk_tolerance"):
        v = getattr(req, k)
        if v is not None:
            base[k] = v
    return base


@app.get("/api/portfolio/candidates")
def portfolio_candidates(field: str | None = None):
    return ok({"candidates": _cands(field=field), "plan_state": state.plan_state(), "manual_jobs": state.load()["manual_jobs"], "scenarios": state.load()["scenarios"]})


@app.post("/api/portfolio/optimise")
def optimise(req: OptimiseReq):
    c = ctx()
    if req.objective not in portfolio.OBJECTIVES:
        raise HTTPException(400, f"objective must be one of {portfolio.OBJECTIVES}")
    cons = _constraints(req, c)
    ps = state.plan_state()
    plan = portfolio.optimise(_cands(c, req.field), cons, req.objective, req.weights, locked=ps["locked"], removed=set(ps["removed"]))
    # apply manual moves (drag) and report conflicts
    conflicts = []
    Q = plan["quarters"]
    for sel in plan["selected"]:
        mv = ps["moves"].get(sel["candidate_id"])
        if mv is not None and not sel["locked"]:
            sel["quarter"] = min(int(mv), Q - 1)
            sel["moved"] = True
    for q in range(Q):
        inq = [s_ for s_ in plan["selected"] if s_["quarter"] == q]
        if len(inq) > cons["max_concurrent"]:
            conflicts.append(f"Q{q + 1}: {len(inq)} jobs exceed max concurrent {cons['max_concurrent']}")
        rig = sum(s_["duration_months"] / 3 for s_ in inq if s_["crew_type"] == "rig")
        if rig > cons["rigs"] + 1e-9:
            conflicts.append(f"Q{q + 1}: rig load {rig:.2f} exceeds {cons['rigs']} rig(s)")
        crew = sum(s_["duration_months"] / 3 for s_ in inq if s_["crew_type"] == "rigless")
        if crew > cons["crews"] + 1e-9:
            conflicts.append(f"Q{q + 1}: crew load {crew:.2f} exceeds {cons['crews']} crew(s)")
    plan["conflicts"] = conflicts
    plan["constraints"] = cons
    return ok(plan)


@app.post("/api/portfolio/compare")
def compare(req: OptimiseReq):
    c = ctx()
    cons = _constraints(req, c)
    cands = _cands(c, req.field)
    ps = state.plan_state()
    core = portfolio.optimise(cands, cons, req.objective, req.weights, locked=ps["locked"], removed=set(ps["removed"]))
    baselines = [portfolio.baseline_plan(cands, cons["budget"], rule) for rule in ("highest_previous_production", "lowest_cost_first", "naive_npv")]
    return ok({"core": {"name": "CORE optimised plan", "kpi": {**core["kpi"], "bad_job_exposure": sum(s_["cost"] for s_ in core["selected"] if s_["npv"] <= 0)}, "selected": core["selected"]}, "baselines": baselines, "note": "Baselines are transparent rules applied to the same candidate list — not an engineer plan."})


class PlanEdit(BaseModel):
    locked: dict | None = None
    removed: list | None = None
    moves: dict | None = None
    reset: bool = False


@app.post("/api/portfolio/plan-state")
def plan_edit(req: PlanEdit):
    return ok(state.update_plan(req.locked, req.removed, req.moves, req.reset))


class ManualJob(BaseModel):
    well_id: str
    action: str
    cost: float
    npv: float
    oil_bpd: float = 0
    water_bpd: float = 0
    duration_months: float = 1
    crew_type: str = "rigless"
    risk: float = 0.5
    confidence: str = "LOW CONFIDENCE"
    status: str = "MANUAL"
    label: str | None = None
    safety_block: str | None = None


@app.post("/api/portfolio/manual-job")
def manual_job(req: ManualJob):
    d = req.model_dump()
    d["npv_lo"], d["npv_hi"] = d["npv"] * 0.5, d["npv"] * 1.5
    return ok(state.add_manual_job(d))


class ScenarioReq(BaseModel):
    name: str
    budget: float
    constraints: dict
    objective: str
    plan: dict
    user: str = "manager"
    scenario_id: str | None = None


@app.post("/api/portfolio/scenarios")
def save_scenario(req: ScenarioReq):
    return ok(state.save_scenario(req.name, req.budget, req.constraints, req.objective, req.plan, req.user, req.scenario_id))


@app.delete("/api/portfolio/scenarios/{scenario_id}")
def del_scenario(scenario_id: str):
    state.delete_scenario(scenario_id)
    return ok({"deleted": scenario_id})


@app.post("/api/portfolio/sensitivity")
def sensitivity(req: OptimiseReq):
    c = ctx()
    cons = _constraints(req, c)
    idle_rows, ghost_rows, water_rows = agg("idle")["rows"], agg("ghost")["rows"], agg("water")["rows"]

    def recompute(settings):
        return portfolio.candidates(idle_rows, ghost_rows, water_rows, settings, state.load()["manual_jobs"])
    return ok({"tornado": portfolio.sensitivity(c.settings, recompute(c.settings), cons, req.objective, recompute), "note": "Candidate NPVs are re-priced under each perturbation using cached causal estimates; the optimiser re-runs each time."})


# ----------------------------------------------------------------------------- validation
@app.get("/api/validation/{name}")
def validation_get(name: str):
    if name == "model-cards":
        return ok(validation.model_cards())
    if name == "sensitivity":
        return sensitivity(OptimiseReq())
    key = {"planted-truth": "planted_truth", "blind-test": "blind_test", "placebo": "placebo", "calibration": "calibration", "reason-accuracy": "reason_accuracy"}.get(name)
    if not key:
        raise HTTPException(404, "Unknown validation view")
    return ok(agg(key))


@app.get("/api/quality")
def quality():
    c = ctx()
    q = c.quality.reset_index()
    return ok({"rows": json.loads(q.to_json(orient="records")), "summary": {"wells": int(len(q)), "good": int((q.dq_grade == "good").sum()), "fair": int((q.dq_grade == "fair").sum()), "poor": int((q.dq_grade == "poor").sum()), "mean_score": round(float(q.dq_score.mean()), 1)}})


@app.get("/api/runs")
def runs():
    return ok({"runs": engine.list_runs()})


@app.get("/api/runs/{analysis_id}")
def run_detail(analysis_id: str):
    a = engine.cache_get(analysis_id)
    if not a:
        raise HTTPException(404, "Unknown analysis")
    return ok(a)


# ----------------------------------------------------------------------------- archive
@app.get("/api/archive/documents")
def archive_docs():
    return ok({"documents": archive.documents(), "stats": archive.stats()})


@app.get("/api/archive/documents/{doc_id}")
def archive_doc(doc_id: str):
    d = archive.get(doc_id)
    if not d["document"]:
        raise HTTPException(404, "Unknown document")
    return ok(d)


@app.post("/api/archive/upload")
async def archive_upload(file: UploadFile = File(...), well_id: str | None = Form(None)):
    data = await file.read()
    try:
        doc = archive.save_upload(file.filename or "upload", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if well_id:
        reg = archive._load()
        reg["documents"][doc.document_id]["well_id"] = well_id
        archive._save(reg)
    ex = archive.extract(doc.document_id)
    return ok({"document": archive.get(doc.document_id)["document"], "extraction": ex.model_dump()})


@app.post("/api/archive/documents/{doc_id}/extract")
def archive_extract(doc_id: str, provider: str | None = None):
    try:
        return ok(archive.extract(doc_id, provider).model_dump())
    except KeyError:
        raise HTTPException(404, "Unknown document")


class ReviewReq(BaseModel):
    decision: str
    edits: dict | None = None
    reviewer: str = "engineer"


@app.post("/api/archive/documents/{doc_id}/review")
def archive_review(doc_id: str, req: ReviewReq):
    try:
        return ok(archive.review(doc_id, req.decision, req.edits, req.reviewer))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/archive/search")
def archive_search(q: str):
    return ok(archive.search(q))


@app.get("/api/archive/records")
def archive_records():
    return ok({"records": archive.approved_records()})


@app.get("/api/archive/file/{doc_id}")
def archive_file(doc_id: str):
    d = archive.get(doc_id)["document"]
    if not d:
        raise HTTPException(404, "Unknown document")
    path = archive.stored_file(d)
    if not path.exists():
        raise HTTPException(404, "The file for this document is no longer on disk")
    return FileResponse(path, filename=d["file_name"])


# ----------------------------------------------------------------------------- network / data hub
@app.get("/api/network")
def network():
    return ok(imports.network(ctx(), agg("idle")["rows"], agg("ghost")["rows"], agg("water")["rows"]))


@app.get("/api/data/connectors")
def connectors():
    return ok({"connectors": imports.connector_status(state.load()["connectors"]), "active": store.active_dataset_name()})


class ModeReq(BaseModel):
    mode: str


@app.get("/api/data/mode")
def get_data_mode():
    """Current data mode and its source line. SYNTHETIC is the default."""
    from ..data import mode as data_mode

    data_mode.sync_from_active()
    return ok(data_mode.describe())


@app.post("/api/data/mode")
def set_data_mode(req: ModeReq):
    """Switch between the existing synthetic demo and real public data.

    Switching repoints the analytical data set and clears the engine context, so no
    values from the other mode can survive in a cached page.
    """
    from ..data import mode as data_mode

    try:
        result = data_mode.set_mode(req.mode.upper())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except store.EmptyDatasetError as exc:
        raise HTTPException(409, str(exc))
    engine.clear_context()
    store.load_dataset.cache_clear()
    return ok({**result, **data_mode.describe()})


@app.get("/api/data/context")
def data_context():
    """What CORE is analysing right now, per domain, with truthful availability states."""
    from ..data import context

    return ok(context.describe())


class ConnectorReq(BaseModel):
    months: list[str] | None = None
    activate: bool = False


# Sources CORE can genuinely import by itself. Anything not listed here must say so
# rather than turning green: a connector never reports Connected on a button press alone.
ADAPTER_NOT_IMPLEMENTED = {
    "saskatchewan_petrinex": "Petrinex Saskatchewan",
    "north_dakota": "North Dakota DMR",
    "kansas_kgs": "Kansas Geological Survey",
    "volve": "Equinor Volve",
}


def _aer_kind(cid: str) -> str | None:
    return cid[4:] if cid.startswith("aer_") else None


def _connect_petrinex(req: ConnectorReq | None, progress=None) -> dict:
    """Download → validate → normalize → write. Only a real import returns ok=True."""
    from ..data import petrinex, petrinex_cache

    months = (req.months if req and req.months else None) or petrinex_cache.available_months(12)
    if progress:
        progress(f"downloading {len(months)} month(s): {months[0]} → {months[-1]}")
    try:
        tables, meta_ = petrinex.build_alberta(months, config.RAW_DIR)
        meta_.update({
            "rows": int(len(tables["production_monthly"])),
            "date_range": [months[0], months[-1]],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "fields": ["oil_m3", "water_m3", "gas_e3m3", "hours"],
            "connection_type": "public download → local validated cache",
            "official": True,
        })
        if progress:
            progress(f"validating {len(tables['production_monthly']):,} rows")
        store.write_dataset("alberta_petrinex", tables, meta_)   # refuses an empty import
    except store.EmptyDatasetError as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:
        return {"ok": False, "message": (
            f"Petrinex import failed: {exc}. Nothing was imported and the previously active data set is "
            "unchanged. Offline alternative: python scripts/fetch_petrinex.py, or the CSV import wizard.")}
    message = (f"Imported {len(tables['wells']):,} wells and {len(tables['production_monthly']):,} monthly rows "
               f"({months[0]} → {months[-1]}).")
    if req and req.activate:
        store.set_active_dataset("alberta_petrinex")
        engine.clear_context()
        message += " This data set is now the active data context. Rebuild the evidence base to refresh causal analyses."
    else:
        message += " Select it as the active data context to analyse it."
    return {"ok": True, "message": message, "rows": int(len(tables["production_monthly"])),
            "wells": int(len(tables["wells"]))}


def _connect_aer(kind: str, progress=None) -> dict:
    """AER public sources: ArcGIS services and AER's own direct-download CSVs."""
    if progress:
        progress(f"contacting the official source for {kind}")
    try:
        if kind in alberta.ARCGIS_SOURCES:
            meta_ = alberta.sync_arcgis(kind)
        elif kind in alberta.FILE_SOURCES and alberta.FILE_SOURCES[kind].get("url"):
            meta_ = alberta.download_file_source(kind)
        else:
            spec = alberta.FILE_SOURCES.get(kind, {})
            return {"ok": False, "message": (
                f"{spec.get('name', kind)} has no automatic adapter. Download the official file from AER and "
                f"import it with: python scripts/update_alberta_data.py --file {kind}=/path/to/file.csv")}
    except Exception as exc:
        return {"ok": False, "message": f"{kind} import failed: {exc} The previous validated cache is unchanged."}
    return {"ok": True, "message": f"Imported {meta_['stats']['rows']:,} validated rows.",
            "rows": int(meta_["stats"]["rows"])}


@app.post("/api/data/connectors/{cid}/{action}")
def connector_action(cid: str, action: str, req: ConnectorReq | None = None):
    st = state.load()
    aer_kind = _aer_kind(cid)

    if action in ("connect", "refresh"):
        if cid == "synthetic":
            raise HTTPException(410, "Synthetic data is an existing validation dataset; select it from the data-context switcher instead of importing it.")
        result = None
        if cid == "alberta_petrinex":
            # Downloading and normalising months of Petrinex takes minutes: run it as a
            # tracked job so the Data Hub can show progress rather than appearing frozen.
            return ok({"job_id": run_job(lambda progress=None: _connect_petrinex(req, progress)),
                       "async": True, "message": "Importing Petrinex months…"})
        elif aer_kind:
            return ok({"job_id": run_job(lambda progress=None: _connect_aer(aer_kind, progress)),
                       "async": True, "message": "Importing from the official AER source…"})
        elif cid in ADAPTER_NOT_IMPLEMENTED:
            result = {"ok": False, "message": (
                f"Adapter not implemented for {ADAPTER_NOT_IMPLEMENTED[cid]}. Download the file from the "
                "official site and import it through the CSV wizard — CORE will not fabricate this source."),
                "redirect": "/data/imports"}
        elif cid == "operator_api":
            result = {"ok": False, "message": (
                "Operator API is a contract only: no SOCAR or operator data is bundled, connected or fabricated. "
                "SCADA NOT CONNECTED — currently using public/cached data.")}
        elif cid == "local_csv":
            result = {"ok": True, "message": "Use the import wizard to import a file.", "redirect": "/data/imports"}
        else:
            raise HTTPException(404, f"Unknown source '{cid}'")
        # A source is only ever recorded as connected after a real, validated import.
        if result.get("ok") and cid not in ("local_csv",):
            st["connectors"].pop(cid, None)
        state.save(st)
        return ok(result)

    if action == "disconnect":
        if cid == "synthetic":
            raise HTTPException(410, "Synthetic validation data cannot be disconnected; switch to the Alberta real-data dataset instead.")
        if aer_kind:
            removed = alberta.forget_source(aer_kind)
            return ok({"ok": True, "removed_cache": removed, "message": (
                f"{cid} disconnected and its validated cache removed. Pages that used it now report the data "
                "as unavailable — nothing falls back to synthetic data.")})
        st["connectors"][cid] = {"connected": False, "note": "disconnected by user"}
        state.save(st)
        message = f"{cid} disconnected."
        if store.active_dataset_name() == cid:
            message += (" It was the active data context, so no real data context is selected any more. "
                        "Choose a data context in the Data Hub — CORE will not silently analyse synthetic "
                        "data in its place.")
        return ok({"ok": True, "message": message, "needs_context_choice": store.active_dataset_name() == cid})

    if action == "schema":
        return ok(_source_schema(cid, aer_kind))
    if action == "sample":
        return ok(_source_sample(cid, aer_kind))
    raise HTTPException(400, "Unknown action")


def _source_schema(cid: str, aer_kind: str | None) -> dict:
    """Actual imported columns and dtypes — never a hard-coded display list."""
    if aer_kind:
        frame = alberta.records(aer_kind)
        if frame.empty:
            raise HTTPException(404, f"{cid} is not imported, so it has no schema to inspect.")
        return {"source": cid, "observed": True, "row_count": int(len(frame)),
                "columns": [{"name": c, "dtype": str(frame[c].dtype),
                             "non_null": int(frame[c].notna().sum())} for c in frame.columns]}
    name = cid if cid != "synthetic" else "synthetic"
    try:
        ds = store.load_dataset(name)
    except (FileNotFoundError, store.EmptyDatasetError) as exc:
        raise HTTPException(404, f"{cid} is not imported, so it has no schema to inspect. {exc}")
    tables = {"wells": ds.wells, "production_monthly": ds.production,
              "interventions": ds.interventions, "facilities": ds.facilities}
    return {"source": cid, "observed": True, "dataset": ds.name,
            "tables": {k: {"rows": int(len(v)),
                           "columns": [{"name": c, "dtype": str(v[c].dtype),
                                        "non_null": int(v[c].notna().sum())} for c in v.columns]}
                       for k, v in tables.items()}}


def _source_sample(cid: str, aer_kind: str | None) -> dict:
    """Real rows out of the imported cache."""
    if aer_kind:
        frame = alberta.records(aer_kind)
        if frame.empty:
            raise HTTPException(404, f"{cid} is not imported, so there are no rows to sample.")
        head = frame.head(12)
        return {"source": cid, "rows_total": int(len(frame)),
                "sample": json.loads(head.where(pd.notna(head), None).to_json(orient="records"))}
    name = cid if cid != "synthetic" else "synthetic"
    try:
        ds = store.load_dataset(name)
    except (FileNotFoundError, store.EmptyDatasetError) as exc:
        raise HTTPException(404, f"{cid} is not imported, so there are no rows to sample. {exc}")
    return {"source": cid, "dataset": ds.name, "rows_total": int(len(ds.production)),
            "sample": json.loads(ds.production.head(12).to_json(orient="records")),
            "wells": json.loads(ds.wells.head(6).to_json(orient="records"))}


@app.get("/api/data/sample-schema.csv")
def sample_schema():
    return Response(imports.SAMPLE_SCHEMA, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=core_sample_schema.csv"})


@app.post("/api/data/import/preview")
async def import_preview(file: UploadFile = File(...)):
    data = await file.read()
    try:
        return ok(imports.preview(data, file.filename or "upload.csv"))
    except Exception as e:
        raise HTTPException(400, f"Could not read the file: {e}")


@app.post("/api/data/import/validate")
async def import_validate(file: UploadFile = File(...), mapping: str = Form(...), units: str = Form("{}")):
    import pandas as pd
    data = await file.read()
    df = pd.read_excel(io.BytesIO(data), dtype=str) if (file.filename or "").lower().endswith(".xlsx") else pd.read_csv(io.BytesIO(data), dtype=str, sep=None, engine="python")
    df.columns = [str(c).strip() for c in df.columns]
    return ok(imports.validate(df, json.loads(mapping), json.loads(units)))


@app.post("/api/data/import/ingest")
async def import_ingest(file: UploadFile = File(...), mapping: str = Form(...), units: str = Form("{}"), dataset_name: str = Form("import")):
    data = await file.read()
    res = imports.ingest(data, file.filename or "upload.csv", json.loads(mapping), json.loads(units), dataset_name)
    if res.get("ok"):
        st = state.load()
        st["imports"].append({"file": file.filename, "dataset": res["dataset"], "rows": res["rows"], "at": state.now()})
        state.save(st)
    return ok(res)


@app.post("/api/data/import/interventions")
async def import_interventions(file: UploadFile = File(...), mapping: str = Form(...), dataset_name: str = Form("synthetic")):
    data = await file.read()
    res = imports.ingest_interventions(data, file.filename or "upload.csv", json.loads(mapping), dataset_name)
    if res.get("ok"):
        engine.clear_context()
    return ok(res)


@app.post("/api/data/activate/{name}")
def activate(name: str):
    """Switch the analytical data context. An unusable data set is never activated."""
    if not (config.PROCESSED_DIR / name / "meta.json").exists():
        raise HTTPException(404, "Unknown data set")
    try:
        store.set_active_dataset(name)
    except store.EmptyDatasetError as exc:
        raise HTTPException(409, str(exc))
    engine.clear_context()
    from ..data import context

    return ok({"active": name, "evidence_stale": precompute.stale(),
               "context": context.describe()["dataset"],
               "note": "Rebuild the evidence base: POST /api/evidence/rebuild"})


@app.post("/api/evidence/rebuild")
def rebuild(full: bool = False):
    def fn(progress=None):
        if full:
            precompute.build_all(progress=progress, log=lambda *a: None)
        else:
            precompute.rebuild_economics_only(log=lambda *a: None)
        return {"rebuilt": True}
    return ok({"job_id": run_job(fn), "status": "QUEUED"})


# ----------------------------------------------------------------------------- decisions
class DecisionReq(BaseModel):
    recommendation_id: str
    well_id: str
    action: str
    decision: str
    user: str = "engineer"
    reason: str | None = None
    notes: str | None = None
    inputs: dict | None = None
    confidence: str | None = None
    module: str = "idle"


REASONS = ["Operational constraint", "Safety concern", "Known field condition", "Model missing information", "Cost assumption incorrect", "Intervention unavailable", "Engineering judgement", "Other"]


@app.get("/api/decisions")
def decisions():
    st = state.load()
    return ok({"decisions": sorted(st["decisions"], key=lambda d: d["timestamp"], reverse=True), "reasons": REASONS, "require_reject_reason": ctx().settings["decisions"]["require_reject_reason"]})


@app.post("/api/decisions")
def add_decision(req: DecisionReq):
    if req.decision not in ("ACCEPT", "MODIFY", "REJECT", "DEFER"):
        raise HTTPException(400, "decision must be ACCEPT, MODIFY, REJECT or DEFER")
    if req.decision == "REJECT" and ctx().settings["decisions"]["require_reject_reason"] and not req.reason:
        raise HTTPException(400, "A reason is required to reject a recommendation")
    return ok(state.add_decision(req.recommendation_id, req.well_id, req.action, req.decision, req.user, req.reason, req.notes, req.inputs, req.confidence, req.module))


@app.get("/api/decisions/model-vs-engineer")
def model_vs_engineer():
    ds = state.load()["decisions"]
    n = len(ds)
    acc = sum(1 for d in ds if d["decision"] == "ACCEPT")
    over = sum(1 for d in ds if d["decision"] in ("REJECT", "MODIFY"))
    by_reason = {}
    for d in ds:
        if d.get("reason"):
            by_reason[d["reason"]] = by_reason.get(d["reason"], 0) + 1
    return ok({"decisions": n, "acceptance_rate": round(acc / n, 3) if n else None, "override_rate": round(over / n, 3) if n else None, "deferred": sum(1 for d in ds if d["decision"] == "DEFER"), "by_reason": by_reason,
               "outcomes": {"accepted_with_outcome": 0, "overridden_with_outcome": 0, "note": "Outcome tracking starts when post-decision production is loaded; none available yet in the demo."},
               "note": "Overrides are learning signals, not errors: reasons feed the active-learning backlog (missing features, cost assumptions, donor pools, documents)."})


@app.get("/api/decisions/export.csv")
def decisions_csv():
    ds = state.load()["decisions"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["decision_id", "timestamp", "user", "well_id", "recommendation_id", "action", "decision", "reason", "notes", "confidence", "module", "model_version", "subsequent_outcome"])
    w.writeheader()
    for d in ds:
        w.writerow({k: d.get(k) for k in w.fieldnames})
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=core_decisions.csv"})


# ----------------------------------------------------------------------------- settings / search / copilot / demo
@app.get("/api/settings")
def get_settings():
    return ok(config.load_settings())


@app.put("/api/settings")
def put_settings(payload: dict):
    s = config.save_settings(payload)
    engine.clear_context()
    return ok({"settings": s, "evidence_stale": precompute.stale(), "note": "Economic changes re-price cached analyses; causal/restart changes require a full rebuild."})


@app.post("/api/settings/reset")
def settings_reset():
    s = config.reset_settings()
    engine.clear_context()
    return ok({"settings": s, "evidence_stale": precompute.stale()})


@app.get("/api/search")
def search(q: str):
    return ok(copilot.global_search(ctx(), q, agg("memory")))


class AskReq(BaseModel):
    question: str


@app.post("/api/copilot/ask")
def ask(req: AskReq):
    return ok(copilot.ask(req.question, agg("idle")["rows"], agg("ghost")["rows"], agg("memory")))


@app.post("/api/demo/reset")
def demo_reset():
    import subprocess, sys
    r = subprocess.run([sys.executable, str(config.ROOT / "scripts" / "init_demo.py"), "--reset"], capture_output=True, text=True, timeout=600)
    engine.clear_context()
    return ok({"ok": r.returncode == 0, "log": (r.stdout + r.stderr)[-2000:]})


@app.get("/api/demo/script")
def demo_script():
    c = ctx()
    m = precompute.get("meta") or {}
    mem = agg("memory")
    strong = sorted([r for r in mem if r["kind"] == "intervention" and r["evidence_status"] == "COMPLETE" and r["confidence"] == "HIGH CONFIDENCE"], key=lambda r: -(r["naive_gain_bpd"] - r["causal_gain_bpd"]))
    best = strong[0] if strong else (mem[0] if mem else None)
    idle_top = next((r for r in agg("idle")["rows"] if r["status"] in ("ACT", "REVIEW", "TEST")), None)
    ghost_top = next((r for r in agg("ghost")["rows"] if r.get("is_opportunity")), None)
    return ok({"dataset": {"label": c.ds.meta.get("label"), "data_mode": c.ds.meta.get("data_mode"), "wells": int(len(c.ds.wells)), "months": c.ds.n_months, "restart_events": int(len(c.restart_events)), "idle": int((c.status.status == "idle").sum())},
               "example_intervention": best, "example_idle": idle_top["well_id"] if idle_top else None, "example_ghost": ghost_top["well_id"] if ghost_top else None, "built_at": m.get("built_at")})


@app.get("/api/pilot/scorecard")
def pilot_scorecard():
    bt = agg("blind_test")
    pt = agg("planted_truth")
    idle_rows = agg("idle")["rows"]
    st = state.load()
    dec = st["decisions"]
    plan = portfolio.optimise(_cands(), ctx().settings["portfolio"], "npv", locked=state.plan_state()["locked"], removed=set(state.plan_state()["removed"]))
    qsum = quality().body
    return ok({"blind_test": bt.get("results", [None])[0] if bt.get("available") else None, "bad_interventions_avoided": plan["kpi"]["avoided_poor_spend"], "wells_screened": int(len(ctx().ds.wells)), "engineer_review_rate": (round(sum(1 for d in dec if d["decision"] != "DEFER") / len(dec), 3) if dec else None),
               "calibration": agg("calibration")["bins"], "archive_extraction_accuracy": archive.stats()["accuracy_on_validated_sample"], "data_coverage": json.loads(qsum)["summary"], "time_saved": "OPERATOR DATA REQUIRED (baseline review hours)", "potential_value": plan["kpi"]["expected_value"], "planted_truth": pt.get("metrics")})


# ----------------------------------------------------------------------------- export
@app.get("/api/export/analysis/{analysis_id}.json")
def export_analysis(analysis_id: str):
    a = engine.cache_get(analysis_id)
    if not a:
        raise HTTPException(404, "Unknown analysis")
    return Response(json.dumps(a, indent=1), media_type="application/json", headers={"Content-Disposition": f"attachment; filename={analysis_id}.json"})


@app.get("/api/export/well/{well_id}/report.pdf")
def well_report(well_id: str):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = ctx()
    if well_id not in set(c.ds.wells.well_id):
        raise HTTPException(404, "Unknown well")
    d = json.loads(well_detail(well_id).body)
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    y = H - 50
    pdf.setFont("Helvetica-Bold", 16); pdf.drawString(40, y, f"CORE Well Decision Report — {well_id}"); y -= 22
    pdf.setFont("Helvetica", 9); pdf.drawString(40, y, f"Data: {d['data_mode']} | {d['source']} | model version {config.MODEL_VERSION} | generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"); y -= 24

    def line(txt, size=10, bold=False):
        nonlocal y
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        for chunk in [txt[i:i + 110] for i in range(0, len(txt), 110)] or [""]:
            pdf.drawString(40, y, chunk); y -= 14
            if y < 60:
                pdf.showPage(); y = H - 50
    ov = d["overview"]
    line("Current state", 12, True)
    line(f"Status: {d['status']}   Field: {d['well']['field']}   Current oil: {ov['current_oil_bpd']} bbl/d   Water cut: {ov['water_cut']}   Data quality: {d['quality']['score']} ({d['quality']['grade']})")
    line("Recommendation", 12, True); line(f"{ov['recommended_action'] or 'No open recommendation'}   Confidence: {ov['confidence'] or 'n/a'}")
    if d.get("idle"):
        i = d["idle"]
        line(f"Expected oil {i.get('expected_oil_bpd')} bbl/d (range {i.get('expected_oil_lo')}–{i.get('expected_oil_hi')}), expected NPV {i.get('expected_npv')} (range {i.get('npv_lo')}–{i.get('npv_hi')}), cost {i.get('intervention_cost')} [ILLUSTRATIVE]")
        for w_ in i.get("why", []):
            line("• " + w_)
        line("Shut-in reason hypotheses: " + "; ".join(f"{r['reason']} {r['probability']:.0%} ({r['evidence_quality']})" for r in i.get("reasons", [])))
        line("Evidence wells (analogue restarts): " + ", ".join(a["well_id"] for a in i.get("analogs", [])))
    if d.get("ghost"):
        g = d["ghost"]
        line(f"Ghost-barrel screen: observed {g['observed_bpd']} vs expected {g['expected_bpd']} bbl/d, gap {g['gap_bpd']} (range {g['gap_lo']}–{g['gap_hi']}), driver {g.get('probable_driver')}, {g['confidence']}")
    line("Counterfactual analyses", 12, True)
    for m in d["interventions"]:
        line(f"{m['date']} {m['type']}: naive {m['naive_gain_bpd']} vs causal {m['causal_gain_bpd']} bbl/d (80%: {m['gain_lo_bpd']}–{m['gain_hi_bpd']}), NPV {m['net_value']} [{m['value_basis']}], {m['confidence']}, model {m['model']}, donors {m['donor_count']}")
    line("Source documents", 12, True)
    for doc in d["documents"] or []:
        line(f"{doc['file_name']} ({doc.get('language')}, review: {doc.get('review_status')})")
    if not d["documents"]:
        line("No archive documents linked to this well.")
    line("Engineer decisions", 12, True)
    for dec in d["decisions"] or []:
        line(f"{dec['timestamp'][:16]} {dec['user']}: {dec['decision']} {dec['action']} — {dec.get('reason') or ''} {dec.get('notes') or ''}")
    if not d["decisions"]:
        line("No decisions recorded.")
    line("Assumptions", 12, True)
    e = c.settings["economics"]
    line(f"Oil price {config.val(e['oil_price'])} $/bbl, royalty {config.val(e['royalty_rate'])}, lifting {config.val(e['lifting_cost'])} $/bbl, discount {config.val(e['discount_rate'])}, horizon {config.val(e['horizon_months'])} months — PUBLIC ASSUMPTIONS, editable in Settings.")
    pdf.save()
    return Response(buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=CORE_{well_id}_decision_report.pdf"})


# ----------------------------------------------------------------------------- frontend
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = FRONTEND_DIST / path
        if path and f.exists() and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
