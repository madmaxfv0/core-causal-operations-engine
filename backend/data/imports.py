"""Data Hub: connector registry, CSV import wizard, intervention import, abstract network view."""
from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..config import M3_TO_BBL, PROCESSED_DIR, RAW_DIR
from . import alberta, store

CONNECTORS = [
    {"id": "alberta_petrinex", "name": "Petrinex — Alberta Public Data", "source": "Petrinex Alberta Public Data", "jurisdiction": "Alberta, Canada", "url": "https://www.petrinex.ca/public-data/apd/", "grain": "well × month", "oil": True, "water": True, "gas": True,
     "well_status": "derived from volumes/hours", "interventions": False, "license": "Public data, Petrinex terms of use", "kind": "download", "note": "Current + previous 4 production years. Fetch: python scripts/fetch_petrinex.py --months 2023-01 2025-12"},
    {"id": "saskatchewan_petrinex", "name": "Petrinex — Saskatchewan Public Data", "source": "Petrinex Saskatchewan Public Data", "jurisdiction": "Saskatchewan, Canada", "url": "https://petrinex.ca/public-data/spd/", "grain": "well × month", "oil": True, "water": True, "gas": True,
     "well_status": "derived", "interventions": False, "license": "Public data, Petrinex terms of use", "kind": "download", "note": "Adapter not yet implemented; use the CSV wizard on the downloaded file."},
    {"id": "north_dakota", "name": "North Dakota Department of Mineral Resources", "source": "ND DMR monthly production reports", "jurisdiction": "North Dakota, USA", "url": "https://www.dmr.nd.gov/oilgas/mprindex.asp", "grain": "well × month", "oil": True, "water": True, "gas": True,
     "well_status": "reported", "interventions": False, "license": "Public records", "kind": "download", "note": "Adapter not yet implemented; monthly xlsx files import through the CSV wizard."},
    {"id": "kansas_kgs", "name": "Kansas Geological Survey", "source": "KGS oil & gas database", "jurisdiction": "Kansas, USA", "url": "https://www.kgs.ku.edu/PRS/petroDB.html", "grain": "lease × month (well-level varies)", "oil": True, "water": False, "gas": True,
     "well_status": "reported", "interventions": False, "license": "Public records", "kind": "download", "note": "Water volumes are not consistently reported; water economics limited."},
    {"id": "volve", "name": "Equinor Volve Open Data", "source": "Equinor Volve data sharing", "jurisdiction": "Norway (North Sea)", "url": "https://www.equinor.com/energy/volve-data-sharing", "grain": "well × day/month", "oil": True, "water": True, "gas": True,
     "well_status": "reported", "interventions": "partial (daily drilling/well reports)", "license": "Equinor open data licence (registration required)", "kind": "download", "note": "Requires manual download under licence; production xlsx imports through the CSV wizard."},
    {"id": "synthetic", "name": "Synthetic validation field", "source": "CORE generator (planted truth)", "jurisdiction": "SYNTHETIC", "grain": "well × month", "oil": True, "water": True, "gas": True, "well_status": "derived", "interventions": True, "license": "n/a", "kind": "local", "note": "SYNTHETIC — FOR METHOD VALIDATION"},
    {"id": "local_csv", "name": "Local CSV / operator export", "source": "Import wizard", "jurisdiction": "any", "grain": "well × month", "oil": True, "water": "if mapped", "gas": "if mapped", "well_status": "derived", "interventions": "via intervention import", "license": "operator", "kind": "local", "note": ""},
    {"id": "operator_api", "name": "Operator API (SOCAR pilot)", "source": "Operator integration layer", "jurisdiction": "operator", "grain": "well × month", "oil": True, "water": True, "gas": True, "well_status": "reported", "interventions": True, "license": "operator", "kind": "api",
     "note": "Contract only: no operator data is bundled. Endpoints: /wells, /production_monthly, /interventions, /costs, /facilities, /documents."},
]


def connector_status(state_connectors: dict) -> list[dict]:
    datasets = {d["name"]: d for d in store.list_datasets()}
    active = store.active_dataset_name()
    out = []
    for c in CONNECTORS:
        if c["id"] == "synthetic":
            continue
        ds = datasets.get(c["id"]) or (datasets.get("alberta") if c["id"] == "alberta_petrinex" else None)
        st = dict(c)
        if ds:
            st.update({"connected": True, "active": (ds["name"] == active), "last_refresh": ds.get("created_at"), "rows": ds.get("rows"), "date_range": ds.get("date_range"), "fields": ds.get("fields"), "quality": ds.get("quality"), "dataset": ds["name"]})
        else:
            st.update({"connected": False, "active": False, "last_refresh": None, "rows": None, "date_range": None, "fields": None, "quality": None, "dataset": None})
        st.update(state_connectors.get(c["id"], {}))
        out.append(st)
    for source in alberta.source_status():
        out.append({
            "id": f"aer_{source['kind']}", "name": source["name"], "source": "Alberta Energy Regulator",
            "jurisdiction": "Alberta, Canada", "url": source["meta"].get("source_url") if source["meta"] else None,
            "grain": "well-level public record", "kind": "download", "connected": source["connected"],
            "active": source["connected"], "last_refresh": source["meta"].get("retrieved_at") if source["meta"] else None,
            "rows": (source["meta"].get("stats") or {}).get("rows") if source["meta"] else None,
            "dataset": source["dataset"], "quality": "validated cache" if source["connected"] else None,
            "note": "Import with scripts/update_alberta_data.py; no synthetic fallback."
        })
    return out


# ----------------------------------------------------------------------------- CSV wizard
SAMPLE_SCHEMA = "well_id,month,oil_m3,water_m3,gas_e3m3,hours,status,field\nWELL-001,2024-01,410.5,1250.0,32.1,720,producing,Field A\nWELL-001,2024-02,398.2,1290.4,31.0,672,producing,Field A\n"
CANON = {"well_id": ["well", "well_id", "wellid", "uwi", "well identifier", "quyu", "скважина"], "month": ["month", "date", "production_month", "period", "ay", "месяц", "дата"], "oil": ["oil", "oil_m3", "oil_bbl", "neft", "нефть"],
         "water": ["water", "water_m3", "water_bbl", "su", "вода"], "gas": ["gas", "gas_e3m3", "gas_mcf", "qaz", "газ"], "hours": ["hours", "hrs", "saat", "часы"], "status": ["status", "state"], "field": ["field", "yataq", "месторождение", "pool"]}


def preview(data: bytes, name: str) -> dict:
    if name.lower().endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(data), dtype=str)
    else:
        df = pd.read_csv(io.BytesIO(data), dtype=str, sep=None, engine="python")
    df.columns = [str(c).strip() for c in df.columns]
    guess = {}
    for canon, aliases in CANON.items():
        for c in df.columns:
            if c.lower().replace(" ", "_") in aliases or any(a == c.lower() for a in aliases):
                guess[canon] = c
                break
    return {"columns": list(df.columns), "rows": len(df), "sample": json.loads(df.head(8).to_json(orient="records")), "suggested_mapping": guess}


def validate(df: pd.DataFrame, mapping: dict, units: dict) -> dict:
    errs, warns = [], []
    for req in ("well_id", "month", "oil"):
        if not mapping.get(req):
            errs.append(f"Required column not mapped: {req}")
    if errs:
        return {"ok": False, "errors": errs, "warnings": warns}
    d = df.rename(columns={v: k for k, v in mapping.items() if v})
    months = pd.to_datetime(d["month"], errors="coerce")
    bad = int(months.isna().sum())
    if bad:
        warns.append(f"{bad} rows have unparseable dates and will be dropped")
    oil = pd.to_numeric(d["oil"], errors="coerce")
    if oil.isna().mean() > 0.5:
        errs.append("More than half of oil values are not numeric")
    if (oil < 0).sum():
        warns.append(f"{int((oil < 0).sum())} negative oil values (flagged, not removed)")
    n_wells = d["well_id"].nunique()
    n_months = months.dt.to_period("M").nunique()
    if n_months < 12:
        warns.append(f"Only {n_months} distinct months: causal analysis needs ≥ 24 months of history for a 12/12 window")
    return {"ok": not errs, "errors": errs, "warnings": warns, "wells": int(n_wells), "months": int(n_months), "units": units}


def ingest(data: bytes, name: str, mapping: dict, units: dict, dataset_name: str) -> dict:
    if name.lower().endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(data), dtype=str)
    else:
        df = pd.read_csv(io.BytesIO(data), dtype=str, sep=None, engine="python")
    df.columns = [str(c).strip() for c in df.columns]
    v = validate(df, mapping, units)
    if not v["ok"]:
        return {"ok": False, **v}
    d = df.rename(columns={val: k for k, val in mapping.items() if val})
    d["month"] = pd.to_datetime(d["month"], errors="coerce").dt.to_period("M").astype(str)
    d = d[d.month != "NaT"]
    f_oil = 1.0 / M3_TO_BBL if units.get("oil") == "bbl" else 1.0
    f_wat = 1.0 / M3_TO_BBL if units.get("water") == "bbl" else 1.0
    prod = pd.DataFrame({"well_id": d.well_id.astype(str), "month": d.month, "oil_m3": pd.to_numeric(d.oil, errors="coerce") * f_oil,
                         "water_m3": pd.to_numeric(d.water, errors="coerce") * f_wat if "water" in d.columns else np.nan,
                         "gas_e3m3": pd.to_numeric(d.gas, errors="coerce") if "gas" in d.columns else np.nan, "hours": pd.to_numeric(d.hours, errors="coerce") if "hours" in d.columns else np.nan,
                         "status": d.status if "status" in d.columns else np.where(pd.to_numeric(d.oil, errors="coerce").fillna(0) > 0, "producing", "idle"), "source": f"import:{name}"})
    prod["source_oil_unit"] = units.get("oil", "m3")
    months = sorted(prod.month.unique())
    cal = pd.DataFrame({"t": range(len(months)), "month": months, "days": [pd.Period(m).days_in_month for m in months]})
    prod = prod.merge(cal[["t", "month"]], on="month")
    wells = pd.DataFrame({"well_id": sorted(prod.well_id.unique())})
    wells["source_id"] = wells.well_id
    wells["field"] = wells.well_id.map(d.groupby("well_id").field.first()).fillna("imported").astype(str) if "field" in d.columns else "imported"
    for c, val in (("pool", None), ("operator", "imported"), ("jurisdiction", "import"), ("facility_id", None), ("latitude", None), ("longitude", None), ("spud_date", None), ("completion_date", None), ("well_type", "producer"), ("lift_type", None), ("role", "import")):
        wells[c] = val
    wells["status"] = wells.well_id.map(prod.sort_values("t").groupby("well_id").status.last())
    tables = {"wells": wells, "production_monthly": prod, "interventions": pd.DataFrame(columns=["intervention_id", "well_id", "date", "t", "type", "cost", "duration_months", "source", "confidence", "kind"]), "facilities": pd.DataFrame(columns=["facility_id", "field", "fluid_capacity_bpd", "water_handling"]), "calendar": cal}
    dataset_name = re.sub(r"[^a-z0-9_]+", "_", dataset_name.lower())[:40] or "import"
    store.write_dataset(dataset_name, tables, {"label": f"Imported: {name}", "source": f"local import {name}", "data_mode": "OPERATOR DATA (imported)", "start": months[0], "n_months": len(months), "rows": len(prod), "date_range": [months[0], months[-1]],
                                              "fields": list(mapping.keys()), "created_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "dataset": dataset_name, "wells": int(len(wells)), "months": len(months), "rows": int(len(prod)), "warnings": v["warnings"]}


def ingest_interventions(data: bytes, name: str, mapping: dict, dataset_name: str) -> dict:
    df = pd.read_csv(io.BytesIO(data), dtype=str, sep=None, engine="python")
    df.columns = [str(c).strip() for c in df.columns]
    for req in ("well_id", "date", "type"):
        if not mapping.get(req):
            return {"ok": False, "errors": [f"Required column not mapped: {req}"]}
    d = df.rename(columns={v: k for k, v in mapping.items() if v})
    ds = store.load_dataset(dataset_name)
    tmap = dict(zip(ds.calendar.month, ds.calendar.t))
    d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.to_period("M").astype(str)
    d = d[d.date.isin(tmap.keys())]
    ints = pd.DataFrame({"intervention_id": [f"IMP-{i + 1:04d}" for i in range(len(d))], "well_id": d.well_id.astype(str).values, "date": d.date.values, "t": d.date.map(tmap).astype(int).values, "type": d.type.str.lower().str.replace(" ", "_").values,
                         "cost": pd.to_numeric(d.cost, errors="coerce").values if "cost" in d.columns else np.nan, "duration_months": pd.to_numeric(d.duration, errors="coerce").values if "duration" in d.columns else 1.0,
                         "source": f"import:{name}", "confidence": "CONFIRMED", "kind": "intervention"})
    existing = ds.interventions
    merged = pd.concat([existing, ints], ignore_index=True) if len(existing) else ints
    merged.to_parquet(PROCESSED_DIR / dataset_name / "interventions.parquet", index=False)
    store.load_dataset.cache_clear()
    return {"ok": True, "imported": int(len(ints)), "skipped": int(len(df) - len(d)), "dataset": dataset_name}


# ----------------------------------------------------------------------------- network
def network(ctx, idle_rows: list[dict], ghost_rows: list[dict], water_rows: list[dict]) -> dict:
    """Abstract network layout — coordinates are NOT geographic (none exist in the data)."""
    wells = ctx.ds.wells
    idle_ids = {r["well_id"]: r for r in idle_rows}
    ghost_ids = {r["well_id"]: r for r in ghost_rows if r.get("is_opportunity")}
    wc_map = {r["well_id"]: r["water_cut"] for r in water_rows}
    fields = sorted(wells.field.unique())
    nodes, edges = [], []
    rng = np.random.default_rng(3)
    per_field = {f: wells[wells.field == f].well_id.tolist() for f in fields}
    for fi, f in enumerate(fields):
        ids = per_field[f]
        cx, cy = 200 + fi * 320, 260
        for k, wid in enumerate(ids):
            ang = 2 * np.pi * k / max(len(ids), 1)
            rad = 90 + 90 * (k % 3) / 2 + rng.uniform(-8, 8)
            st = ctx.well_status(wid)
            tags = [st]
            if wid in idle_ids and idle_ids[wid].get("status") in ("ACT", "TEST", "REVIEW"):
                tags.append("intervention candidate")
            if wid in ghost_ids:
                tags.append("underperforming")
            if (wc_map.get(wid) or 0) >= 0.9:
                tags.append("high-water")
            if wid in idle_ids and idle_ids[wid].get("status") == "INSUFFICIENT DATA":
                tags.append("insufficient data")
            nodes.append({"id": wid, "field": f, "x": round(cx + rad * np.cos(ang), 1), "y": round(cy + rad * np.sin(ang), 1), "status": st, "tags": tags, "water_cut": wc_map.get(wid),
                          "opportunity": (idle_ids.get(wid, {}).get("expected_npv") if wid in idle_ids else ghost_ids.get(wid, {}).get("annual_value")) or 0,
                          "confidence": (idle_ids.get(wid) or ghost_ids.get(wid) or {}).get("confidence"), "intervention_type": idle_ids.get(wid, {}).get("intervention_type")})
    # edges: link each candidate well to its top-3 analogue / donor wells (evidence relationships, not geography)
    for r in idle_rows[:40]:
        for a in (r.get("analogs") or [])[:3]:
            edges.append({"source": r["well_id"], "target": a["well_id"], "kind": "analogue restart"})
    for r in ghost_rows[:40]:
        if r.get("is_opportunity") and r.get("analysis_id"):
            from ..core import engine
            a = engine.cache_get(r["analysis_id"])
            if a:
                for d in sorted(a.get("donors", []), key=lambda x: -(x.get("weight") or 0))[:3]:
                    if d.get("weight"):
                        edges.append({"source": r["well_id"], "target": d["well_id"], "kind": "donor"})
    return {"nodes": nodes, "edges": edges, "fields": fields, "note": "Abstract layout: no coordinates exist in this data set, so positions are grouped by field and are not geographic."}
