"""Real Alberta public-data ingestion, normalization and map query helpers.

Source hierarchy (documented in docs/alberta-map.md):

    Official AER dataset  ->  Official Petrinex dataset  ->  Not publicly available

There is deliberately **no fallback generator**.  A dataset becomes usable only
after its required fields validate and the normalized cache is written
atomically.  If a refresh fails for any reason the previously validated cache is
kept and the UI says the refresh failed - it never silently substitutes a
generated number.

Two families of sources are supported:

``ARCGIS_SOURCES``
    AER's own public ArcGIS Feature Services (ST37 list of wells, ST102 facility
    list, pipeline segments).  These can be refreshed directly from the app or
    the CLI because AER publishes them as open services.

``FILE_SOURCES``
    Datasets AER distributes as downloadable files (casing failures, vent flow /
    gas migration, abandoned-well spatial data, well licence list).  These are
    imported from a file the operator has downloaded from the AER catalogue.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config
from . import arcgis, ats

AER_ARCGIS = "https://services2.arcgis.com/jQV6VMr2Loovu7GU/arcgis/rest/services"

ARCGIS_SOURCES: dict[str, dict] = {
    "st37": {
        "name": "AER ST37 — List of Wells in Alberta",
        "dataset": "AER ST37: List of Wells in Alberta",
        "publisher": "Alberta Energy Regulator / Alberta Geological Survey",
        "licence": "Open Government Licence — Alberta",
        "service": f"{AER_ARCGIS}/AB_Well_Licence_WebM/FeatureServer",
        "layer": 0,
        "geometry": "point",
        "required": ["Well_Category", "Surface_Location"],
        "landing": "https://www.aer.ca/data-and-performance-reports/statistical-reports/st37",
        "provides": "Well locations (WGS84), AER well category, surface legal location",
        "primary": True,
    },
    "facilities": {
        "name": "AER ST102 — Facility List",
        "dataset": "AER ST102: Facility List",
        "publisher": "Alberta Energy Regulator",
        "licence": "Open Government Licence — Alberta",
        "service": f"{AER_ARCGIS}/Facilities/FeatureServer",
        "layer": 0,
        "geometry": "point",
        "required": ["FAC_ID", "FAC_NAME", "OPERATOR"],
        "landing": "https://www.aer.ca/data-and-performance-reports/statistical-reports/st102",
        "provides": "Batteries, gas plants, injection and disposal facilities with operator and status",
        "primary": False,
    },
    "pipelines": {
        "name": "AER Pipeline Segments",
        "dataset": "AER Pipeline Segments",
        "publisher": "Alberta Energy Regulator",
        "licence": "Open Government Licence — Alberta",
        "service": f"{AER_ARCGIS}/AB_Pipeline_Segment_WebM/FeatureServer",
        "layer": 0,
        "geometry": "line",
        "required": ["licence_no", "company_name", "substance"],
        "landing": "https://www.aer.ca/data-and-performance-reports/activity-and-data/spatial-data",
        "provides": "Licensed pipeline segments with substance and status",
        "primary": False,
    },
}

# Direct download URLs AER itself publishes on its "General Well Data" page
# (https://www.aer.ca/data-and-performance-reports/activity-and-data/lists-and-activities/general-well-data).
# These are dated, machine-fetchable CSVs updated daily by AER — not a catalogue page a
# person has to search. They are blocked by AER's edge WAF from this development
# sandbox's network (confirmed: identical 403 from curl, a real browser, and Anthropic's
# fetch infrastructure, regardless of headers) — a network-reputation block, not an
# authentication wall. The same URL works from an ordinary residential/office connection.
# Overridable via environment variable if AER changes the path.
FILE_SOURCES: dict[str, dict] = {
    "licences": {
        "name": "AER Well Licence List",
        "dataset": "AER Well Licence List",
        "publisher": "Alberta Energy Regulator",
        "url": os.environ.get("AER_WELL_LICENCE_URL", ""),
        "required": ["well_id"],
        "landing": "https://www.aer.ca/data-and-performance-reports/activity-and-data/lists-and-activities/general-well-data",
        "provides": "Licence number, licensee, well name",
        "note": "AER's General Well Data page does not currently list a standalone direct-download "
                "licence file; ST37 already carries operator and lifecycle status per well.",
    },
    "casing_failures": {
        "name": "AER Well Casing Failures Report",
        "dataset": "AER Casing Failures Report",
        "publisher": "Alberta Energy Regulator",
        "url": os.environ.get(
            "AER_CASING_FAILURES_URL",
            "https://www2.aer.ca/t/Production/views/COM-WellCasingFailureReport/WellCasingFailureReport.csv",
        ),
        "required": ["well_id"],
        "landing": "https://www.aer.ca/data-and-performance-reports/activity-and-data/lists-and-activities/general-well-data",
        "provides": "Reported casing failures, updated daily by AER",
    },
    "vent_flow": {
        "name": "AER Vent Flow / Gas Migration Report",
        "dataset": "AER Vent Flow / Gas Migration Report",
        "publisher": "Alberta Energy Regulator",
        "url": os.environ.get(
            "AER_VENT_FLOW_URL",
            "https://www2.aer.ca/t/Production/views/COM-VentFlowGasMigrationReport/VentFlowGasMigrationReport.csv",
        ),
        "required": ["well_id"],
        "landing": "https://www.aer.ca/data-and-performance-reports/activity-and-data/lists-and-activities/general-well-data",
        "provides": "Surface casing vent flow and gas migration reports, updated daily by AER",
    },
    "abandoned": {
        "name": "AER Abandoned Well Spatial Data",
        "dataset": "AER Abandoned Well Spatial Data",
        "publisher": "Alberta Energy Regulator",
        "url": os.environ.get("AER_ABANDONED_URL", ""),
        "required": ["well_id", "latitude", "longitude"],
        "landing": "https://www.aer.ca/data-and-performance-reports/activity-and-data/spatial-data",
        "provides": "Abandoned well locations",
        "note": "ST37's Well_Category already reports an Abandoned lifecycle state per well "
                "(see the map's Abandoned status filter); this source would add a dedicated "
                "abandonment-event record if AER publishes one as a direct download.",
    },
}

# Retained for callers that treat both families uniformly.
SOURCE_CATALOG: dict[str, dict] = {
    **{k: {**v, "url": v.get("service", "")} for k, v in ARCGIS_SOURCES.items()},
    **FILE_SOURCES,
}

ALIASES = {
    "well_id": ("well_id", "uwi", "well identifier", "licence number", "license number", "licence"),
    "latitude": ("latitude", "lat", "surface latitude", "surface_latitude"),
    "longitude": ("longitude", "lon", "long", "surface longitude", "surface_longitude"),
    "operator": ("operator", "licensee", "licencee", "operator name"),
    "status": ("status", "well status", "lifecycle status"),
    "well_type": ("well type", "type", "fluid"),
    "field": ("field", "field name"),
    "pool": ("pool", "pool name"),
    "surface_location": ("surface location", "surface_location", "legal location", "location"),
}

# ---------------------------------------------------------------------------
# ST37 Well_Category -> derived status / fluid.
# These are DERIVED fields.  The rule is fully documented so nothing is opaque:
# the AER category string is split into a lifecycle word and a fluid word; if a
# word is absent the derived field is reported as "Not reported".
# ---------------------------------------------------------------------------
STATUS_RULES: list[tuple[str, str]] = [
    ("abandoned", "Abandoned"),
    ("suspended", "Suspended"),
    ("drilled and cased", "Drilled and cased"),
    ("surface casing only", "Surface casing only"),
]
FLUID_RULES: list[tuple[str, str]] = [
    ("crude bitumen", "Crude bitumen"),
    ("gas", "Gas"),
    ("oil", "Oil"),
    ("injection", "Injection"),
    ("disposal", "Disposal"),
    ("observation", "Observation"),
]


def derive_status(category: object) -> str:
    text = str(category or "").strip().lower()
    if not text or text == "undefined":
        return "Not reported"
    for needle, label in STATUS_RULES:
        if needle in text:
            return label
    return "Active"


def derive_fluid(category: object) -> str:
    text = str(category or "").strip().lower()
    for needle, label in FLUID_RULES:
        if needle in text:
            return label
    return "Not reported"


DERIVATION_NOTES = {
    "status": "Derived from the AER ST37 Well_Category string: 'Abandoned'/'Suspended'/"
              "'Drilled and Cased'/'Surface Casing Only' map to that lifecycle state; every "
              "other reported category is shown as Active. 'Undefined' is shown as Not reported.",
    "fluid": "Derived from the AER ST37 Well_Category string: the fluid word "
             "(Oil / Gas / Crude bitumen / Injection / Disposal / Observation) is read from the "
             "category. Categories with no fluid word are shown as Not reported.",
}


def _key(value: object) -> str:
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum())


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {_key(c): c for c in df.columns}
    rename = {}
    for target, aliases in ALIASES.items():
        for alias in aliases:
            if _key(alias) in lookup:
                rename[lookup[_key(alias)]] = target
                break
    out = df.rename(columns=rename).copy()
    if "well_id" in out:
        out["well_id"] = out["well_id"].astype(str).str.strip().str.upper()
    for col in ("latitude", "longitude"):
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def transform_to_wgs84(df: pd.DataFrame, source_crs: str | None) -> pd.DataFrame:
    """Transform declared source coordinates; never guess a CRS."""
    if not source_crs or source_crs.upper() in {"EPSG:4326", "CRS84", "WGS84"}:
        return df
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise ValueError(f"Source CRS {source_crs} requires pyproj; install backend requirements before importing") from exc
    transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
    valid = df.latitude.notna() & df.longitude.notna()
    lng, lat = transformer.transform(df.loc[valid, "longitude"].to_numpy(), df.loc[valid, "latitude"].to_numpy())
    out = df.copy()
    out.loc[valid, "longitude"] = lng
    out.loc[valid, "latitude"] = lat
    return out


def validate_wells(df: pd.DataFrame, required=("well_id", "latitude", "longitude")) -> dict:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"AER schema changed: required field(s) missing: {', '.join(missing)}")
    bad_coords = int((df.latitude.notna() & ((df.latitude < 48) | (df.latitude > 61))).sum()) if "latitude" in df else 0
    bad_coords += int((df.longitude.notna() & ((df.longitude < -125) | (df.longitude > -109))).sum()) if "longitude" in df else 0
    valid = df["well_id"].notna() & df["well_id"].ne("") & df["well_id"].ne("NAN")
    return {"rows": int(len(df)), "valid_identifiers": int(valid.sum()),
            "duplicate_identifiers": int(df.loc[valid, "well_id"].duplicated().sum()),
            "invalid_coordinates": bad_coords}


def _read_source(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith((".csv", ".txt"))]
            if not names:
                raise ValueError(f"{path.name} contains no CSV/TXT source file")
            frames = [pd.read_csv(archive.open(name), dtype=str, low_memory=False) for name in names]
        return pd.concat(frames, ignore_index=True)
    return pd.read_csv(path, dtype=str, low_memory=False)


def download_file_source(kind: str, progress=None) -> dict:
    """Download a FILE_SOURCES CSV directly from AER and import it.

    Used for sources AER publishes as a plain dated file rather than a queryable
    service (casing failures, vent flow / gas migration). Retried with backoff;
    the download is written to a temp file and only handed to `import_file` (which
    is itself atomic) once it has fully arrived, so a failed or partial download
    can never replace a validated cache.
    """
    import httpx

    spec = FILE_SOURCES.get(kind)
    if not spec or not spec.get("url"):
        raise ValueError(f"{kind} has no configured direct-download URL")
    url = spec["url"]
    raw_dir = config.ALBERTA_RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(f"downloading {spec['name']}")
    last: Exception | None = None
    for attempt in range(4):
        staging = None
        try:
            with httpx.Client(
                timeout=httpx.Timeout(30, read=180), follow_redirects=True,
                headers={"User-Agent": "CORE Alberta public-data importer", "Accept": "text/csv,*/*"},
            ) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with tempfile.NamedTemporaryFile(dir=raw_dir, suffix=".csv.part", delete=False) as tmp:
                        staging = Path(tmp.name)
                        for chunk in response.iter_bytes(1 << 20):
                            tmp.write(chunk)
            if staging.stat().st_size < 50:
                raise ValueError(f"response too small ({staging.stat().st_size} bytes) — likely blocked or empty")
            if progress:
                progress(f"validating {spec['name']}")
            meta = import_file(staging, kind)
            staging.unlink(missing_ok=True)
            return meta
        except Exception as exc:
            last = exc
            if staging is not None:
                staging.unlink(missing_ok=True)
            time.sleep(min(20, 2 ** attempt))
    raise RuntimeError(
        f"{spec['name']} could not be downloaded from {url}: {last}. "
        "Previous valid cache (if any) was preserved. If this network blocks the AER host, "
        "download the CSV in a browser and run: python scripts/update_alberta_data.py "
        f"--file {kind}=/path/to/file.csv"
    )


def import_file(path: Path, kind: str, retrieved_at: str | None = None, source_crs: str | None = None) -> dict:
    """Import an official file the operator downloaded from the AER catalogue."""
    spec = SOURCE_CATALOG.get(kind)
    if not spec:
        raise ValueError(f"Unknown Alberta source: {kind}")
    declared_crs = (source_crs or os.environ.get("AER_ST37_CRS")) if kind in {"st37", "abandoned"} else source_crs
    normalized = transform_to_wgs84(normalize_columns(_read_source(path)), declared_crs)
    stats = validate_wells(normalized, tuple(spec["required"]))
    out_dir = config.ALBERTA_CACHE_DIR / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"{kind}-", dir=config.ALBERTA_CACHE_DIR))
    try:
        normalized.to_parquet(tmp / "records.parquet", index=False)
        meta = {
            "source": spec.get("publisher", "Alberta Energy Regulator"),
            "dataset": spec["dataset"],
            "source_url": spec.get("url") or spec.get("service") or None,
            "source_file": path.name,
            "ingest": "file",
            "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_crs": declared_crs or "EPSG:4326",
            "stats": stats,
        }
        (tmp / "meta.json").write_text(json.dumps(meta, indent=2))
        backup = out_dir.with_name(out_dir.name + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        if out_dir.exists():
            out_dir.rename(backup)
        tmp.rename(out_dir)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    _CACHE.clear()
    return meta


# ---------------------------------------------------------------------------
# ArcGIS refresh
# ---------------------------------------------------------------------------

def normalize_st37(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    out = pd.DataFrame(index=frame.index)
    out["record_id"] = "ST37-" + frame["OBJECTID"].astype(str)
    out["well_category"] = frame.get("Well_Category").astype(str).str.strip() if "Well_Category" in frame else ""
    out["surface_location"] = frame.get("Surface_Location").astype(str).str.strip() if "Surface_Location" in frame else None
    out["latitude"] = pd.to_numeric(frame.get("latitude"), errors="coerce")
    out["longitude"] = pd.to_numeric(frame.get("longitude"), errors="coerce")
    out["status"] = out.well_category.map(derive_status)
    out["fluid"] = out.well_category.map(derive_fluid)
    out["ats_cell"] = out.surface_location.map(ats.cell_from_location)
    in_alberta = out.latitude.between(48, 61) & out.longitude.between(-125, -109)
    stats = {
        "rows": int(len(out)),
        "valid_coordinates": int(in_alberta.sum()),
        "invalid_coordinates": int((~in_alberta).sum()),
        "parsed_legal_locations": int(out.ats_cell.notna().sum()),
        "unparsed_legal_locations": int(out.ats_cell.isna().sum()),
        "distinct_ats_cells": int(out.ats_cell.dropna().nunique()),
        "by_status": out.status.value_counts().to_dict(),
        "by_fluid": out.fluid.value_counts().to_dict(),
    }
    out = out[in_alberta].reset_index(drop=True)
    return out, stats


def normalize_facilities(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    out = pd.DataFrame(index=frame.index)
    out["facility_id"] = frame.get("FAC_ID").astype(str).str.strip().str.upper()
    out["name"] = frame.get("FAC_NAME")
    out["operator"] = frame.get("OPERATOR")
    out["facility_type"] = frame.get("EDCT_DESCR") if "EDCT_DESCR" in frame else frame.get("FAC_SUB_TY")
    out["facility_status"] = frame.get("FAC_STATUS")
    out["surface_location"] = frame.get("ats_label") if "ats_label" in frame else None
    out["latitude"] = pd.to_numeric(frame.get("latitude"), errors="coerce")
    out["longitude"] = pd.to_numeric(frame.get("longitude"), errors="coerce")
    valid = out.latitude.between(48, 61) & out.longitude.between(-125, -109)
    stats = {"rows": int(len(out)), "valid_coordinates": int(valid.sum()),
             "invalid_coordinates": int((~valid).sum()),
             "distinct_facilities": int(out.facility_id.nunique())}
    return out[valid].reset_index(drop=True), stats


def normalize_pipelines(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    out = pd.DataFrame(index=frame.index)
    out["licence_no"] = frame.get("licence_no").astype(str)
    out["company_name"] = frame.get("company_name")
    out["status"] = frame.get("status")
    out["substance"] = frame.get("substance")
    out["geometry_json"] = frame.get("geometry_json")
    out = out[out.geometry_json.notna()].reset_index(drop=True)
    out = _add_segment_bounds(out)
    stats = {"rows": int(len(out)), "distinct_licences": int(out.licence_no.nunique()),
             "by_substance": out.substance.value_counts().head(20).to_dict()}
    return out, stats


def _segment_bounds(geometry_json: str) -> tuple[float, float, float, float] | None:
    try:
        coords = json.loads(geometry_json)
    except Exception:
        return None
    parts = coords if coords and isinstance(coords[0][0], list) else [coords]
    xs = [pt[0] for part in parts for pt in part]
    ys = [pt[1] for part in parts for pt in part]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _add_segment_bounds(frame: pd.DataFrame) -> pd.DataFrame:
    """Precompute a per-segment bounding box so viewport filtering is vectorised."""
    bounds = [_segment_bounds(g) for g in frame.geometry_json]
    frame = frame.copy()
    frame["min_lng"] = [b[0] if b else np.nan for b in bounds]
    frame["min_lat"] = [b[1] if b else np.nan for b in bounds]
    frame["max_lng"] = [b[2] if b else np.nan for b in bounds]
    frame["max_lat"] = [b[3] if b else np.nan for b in bounds]
    return frame


def pipelines_in_bbox(bbox, limit: int = 1200) -> pd.DataFrame:
    """Bounding-box intersection using precomputed segment extents."""
    frame = records("pipelines")
    if frame.empty:
        return frame
    if "min_lng" not in frame.columns:                 # cache written before bounds existed
        stamp = _cache_path("pipelines").stat().st_mtime
        hit = _CACHE.get("pipeline_bounds")
        if hit and hit[0] == stamp:
            frame = hit[1]
        else:
            frame = _add_segment_bounds(frame)
            _CACHE["pipeline_bounds"] = (stamp, frame)
    if not bbox:
        return frame.head(limit)
    min_lng, min_lat, max_lng, max_lat = bbox
    hit = (frame.min_lng <= max_lng) & (frame.max_lng >= min_lng) & \
          (frame.min_lat <= max_lat) & (frame.max_lat >= min_lat)
    return frame[hit].head(limit)


NORMALIZERS = {"st37": normalize_st37, "facilities": normalize_facilities, "pipelines": normalize_pipelines}


def sync_arcgis(kind: str, progress=None, max_records: int | None = None) -> dict:
    """Refresh one AER ArcGIS source. Preserves last-known-good on any failure."""
    spec = ARCGIS_SOURCES.get(kind)
    if not spec:
        raise ValueError(f"{kind} is not an AER ArcGIS source")
    frame, provenance = arcgis.fetch_layer(
        spec["service"], spec["layer"], geometry=spec["geometry"],
        required_fields=spec["required"], progress=progress, max_records=max_records,
    )
    normalized, stats = NORMALIZERS[kind](frame)
    if normalized.empty:
        raise arcgis.SourceUnavailable(f"{kind}: no valid rows after validation; cache preserved")
    meta = {
        "source": spec["publisher"],
        "dataset": spec["dataset"],
        "licence": spec["licence"],
        "landing_page": spec["landing"],
        "ingest": "arcgis-feature-service",
        "source_url": spec["service"],
        "value_type": "REPORTED / REGULATORY RECORD",
        "stats": stats,
        **provenance,
    }
    arcgis.write_cache(normalized, meta, config.ALBERTA_CACHE_DIR / kind)
    _CACHE.clear()
    return meta


# ---------------------------------------------------------------------------
# Cache access with an in-process memo keyed on file mtime.
# ---------------------------------------------------------------------------
_CACHE: dict[str, tuple[float, object]] = {}


def _cache_path(kind: str) -> Path:
    return config.ALBERTA_CACHE_DIR / kind / "records.parquet"


def records(kind: str) -> pd.DataFrame:
    path = _cache_path(kind)
    if not path.exists():
        return pd.DataFrame()
    stamp = path.stat().st_mtime
    hit = _CACHE.get(f"rec:{kind}")
    if hit and hit[0] == stamp:
        return hit[1]
    frame = pd.read_parquet(path)
    _CACHE[f"rec:{kind}"] = (stamp, frame)
    return frame


def forget_source(kind: str) -> bool:
    """Remove a validated cache so the source genuinely becomes 'not connected'.

    Downstream views then report the data as unavailable. Nothing falls back to a
    generated substitute. Returns True when a cache was actually removed.
    """
    if kind not in SOURCE_CATALOG:
        raise ValueError(f"Unknown Alberta source: {kind}")
    out_dir = config.ALBERTA_CACHE_DIR / kind
    existed = out_dir.exists()
    if existed:
        shutil.rmtree(out_dir, ignore_errors=True)
    _CACHE.clear()
    return existed


def meta(kind: str) -> dict | None:
    path = config.ALBERTA_CACHE_DIR / kind / "meta.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def source_status() -> list[dict]:
    out = []
    for kind, spec in SOURCE_CATALOG.items():
        m = meta(kind)
        rows = 0
        if m:
            rows = int(m.get("stats", {}).get("rows", 0))
        out.append({
            "kind": kind,
            "name": spec["name"],
            "dataset": spec["dataset"],
            "publisher": spec.get("publisher"),
            "provides": spec.get("provides"),
            "landing_page": spec.get("landing"),
            "note": spec.get("note"),
            "refreshable": kind in ARCGIS_SOURCES or (kind in FILE_SOURCES and bool(spec.get("url"))),
            "connected": bool(m),
            "rows": rows,
            "url_configured": bool(spec.get("url") or spec.get("service")),
            "meta": m,
        })
    return out


# ---------------------------------------------------------------------------
# Map queries
# ---------------------------------------------------------------------------
ALBERTA_BOUNDS = (-120.1, 48.9, -109.9, 60.1)


def wells() -> pd.DataFrame:
    """ST37 wells enriched with the Petrinex production join (cached)."""
    base = records("st37")
    if base.empty:
        return base
    from . import petrinex_cache

    stamp = (_cache_path("st37").stat().st_mtime, petrinex_cache.cache_stamp())
    hit = _CACHE.get("wells")
    if hit and hit[0] == stamp:
        return hit[1]
    out = base.copy()
    # How many AER records share this legal subdivision? Needed for the uniqueness rule below.
    out["cell_records"] = out.groupby("ats_cell").record_id.transform("size").where(out.ats_cell.notna())
    link = petrinex_cache.cell_link()
    if link is not None and not link.empty:
        merged = out.merge(link, on="ats_cell", how="left")
        # The production link must be unique in BOTH directions.  Petrinex already
        # excluded legal subdivisions holding more than one reporting well; here we
        # also drop cells holding more than one AER record, because one reported
        # volume must never be attributed to several map points.
        ambiguous = merged.cell_records.fillna(0) > 1
        for col in ("uwi", "operator", "facility_id", "facility_name", "latest_month", "oil_m3",
                    "gas_e3m3", "water_m3", "water_cut", "oil_m3_per_day", "months_reported", "candidates"):
            if col in merged:
                merged.loc[ambiguous, col] = None
        merged["link_blocked_by_shared_location"] = ambiguous & merged.ats_cell.notna()
    else:
        merged = out
        for col in ("uwi", "operator", "facility_id", "facility_name", "candidates", "latest_month",
                    "oil_m3", "gas_e3m3", "water_m3", "water_cut", "oil_m3_per_day", "months_reported"):
            merged[col] = None
        merged["link_blocked_by_shared_location"] = False
    merged["has_production"] = merged.uwi.notna() if "uwi" in merged else False
    _CACHE["wells"] = (stamp, merged)
    return merged


def _apply_filters(rows: pd.DataFrame, *, status=None, fluid=None, operator=None,
                   layer=None, producing=None, query=None) -> pd.DataFrame:
    out = rows
    if status:
        out = out[out.status.str.lower() == str(status).lower()]
    if fluid:
        out = out[out.fluid.str.lower() == str(fluid).lower()]
    if operator:
        needle = str(operator).lower()
        out = out[out.operator.fillna("").astype(str).str.lower().str.contains(needle, regex=False)]
    if producing:
        out = out[pd.to_numeric(out.get("oil_m3"), errors="coerce").fillna(0) > 0]
    if layer == "integrity":
        ids = integrity_cells()
        out = out[out.ats_cell.isin(ids)] if ids else out.iloc[0:0]
    elif layer == "production":
        out = out[out.get("has_production").fillna(False)]
    elif layer == "water":
        out = out[pd.to_numeric(out.get("water_cut"), errors="coerce").fillna(-1) >= 0.5]
    elif layer == "abandoned":
        out = out[out.status == "Abandoned"]
    elif layer == "injection":
        out = out[out.fluid.isin(["Injection", "Disposal"])]
    if query:
        needle = str(query).strip().lower()
        cols = [c for c in ("record_id", "uwi", "surface_location", "operator", "well_category", "facility_id") if c in out.columns]
        mask = np.zeros(len(out), dtype=bool)
        for col in cols:
            mask |= out[col].fillna("").astype(str).str.lower().str.contains(needle, regex=False).to_numpy()
        out = out[mask]
    return out


def map_query(bbox=None, *, status=None, fluid=None, operator=None, layer=None,
              producing=None, query=None) -> pd.DataFrame:
    rows = wells()
    if rows.empty:
        return rows
    if bbox:
        min_lng, min_lat, max_lng, max_lat = bbox
        lat = rows.latitude.to_numpy()
        lng = rows.longitude.to_numpy()
        rows = rows[(lng >= min_lng) & (lng <= max_lng) & (lat >= min_lat) & (lat <= max_lat)]
    return _apply_filters(rows, status=status, fluid=fluid, operator=operator,
                          layer=layer, producing=producing, query=query)


def cluster(rows: pd.DataFrame, cell: float) -> list[dict]:
    """Grid clustering: bounded response size regardless of dataset size."""
    if rows.empty:
        return []
    gx = np.floor(rows.longitude.to_numpy() / cell).astype(np.int64)
    gy = np.floor(rows.latitude.to_numpy() / cell).astype(np.int64)
    frame = pd.DataFrame({
        "gx": gx, "gy": gy,
        "lng": rows.longitude.to_numpy(), "lat": rows.latitude.to_numpy(),
        "abandoned": (rows.status == "Abandoned").to_numpy(),
        "active": (rows.status == "Active").to_numpy(),
        "producing": pd.to_numeric(rows.get("oil_m3"), errors="coerce").fillna(0).to_numpy() > 0,
    })
    grouped = frame.groupby(["gx", "gy"], sort=False)
    out = grouped.agg(count=("lng", "size"), longitude=("lng", "mean"), latitude=("lat", "mean"),
                      abandoned=("abandoned", "sum"), active=("active", "sum"),
                      producing=("producing", "sum")).reset_index()
    return [{
        "id": f"c{int(r.gx)}_{int(r.gy)}",
        "count": int(r.count), "longitude": float(r.longitude), "latitude": float(r.latitude),
        "abandoned": int(r.abandoned), "active": int(r.active), "producing": int(r.producing),
    } for r in out.itertuples()]


def integrity_cells() -> set[str]:
    """ATS cells with a matching AER casing-failure or vent-flow record."""
    cells: set[str] = set()
    for kind in ("casing_failures", "vent_flow"):
        frame = records(kind)
        if frame.empty:
            continue
        if "surface_location" in frame:
            cells.update(frame.surface_location.map(ats.cell_from_location).dropna())
        if "well_id" in frame:
            cells.update(frame.well_id.map(ats.cell_from_uwi).dropna())
    return cells


def integrity_for(cell: str | None, uwi: str | None = None) -> dict:
    """Matching public integrity records, keyed by ATS cell (and UWI when known)."""
    result: dict[str, list] = {}
    for kind, label in (("casing_failures", "casing_failure"), ("vent_flow", "vent_flow"), ("abandoned", "abandoned")):
        frame = records(kind)
        if frame.empty:
            result[label] = []
            continue
        mask = pd.Series(False, index=frame.index)
        if cell:
            if "surface_location" in frame:
                mask |= frame.surface_location.map(ats.cell_from_location).eq(cell).fillna(False)
            if "well_id" in frame:
                mask |= frame.well_id.map(ats.cell_from_uwi).eq(cell).fillna(False)
        if uwi and "well_id" in frame:
            mask |= frame.well_id.astype(str).str.replace(r"[^0-9A-Z]", "", regex=True).eq(uwi)
        hits = frame[mask]
        result[label] = hits.where(pd.notna(hits), None).to_dict(orient="records")
    return result


def dataset_summary() -> dict:
    """Every headline number on the map page is computed here, from imported rows."""
    frame = wells()
    if frame.empty:
        return {"available": False}
    oil = pd.to_numeric(frame.get("oil_m3"), errors="coerce")
    facilities = records("facilities")
    pipelines = records("pipelines")
    st37_meta = meta("st37") or {}
    from . import petrinex_cache

    pmeta = petrinex_cache.cache_meta() or {}
    return {
        "available": True,
        "wells_loaded": int(len(frame)),
        "with_valid_coordinates": int(len(frame)),
        "active": int((frame.status == "Active").sum()),
        "suspended": int((frame.status == "Suspended").sum()),
        "abandoned": int((frame.status == "Abandoned").sum()),
        "oil": int((frame.fluid == "Oil").sum()),
        "gas": int((frame.fluid == "Gas").sum()),
        "bitumen": int((frame.fluid == "Crude bitumen").sum()),
        "injection": int(frame.fluid.isin(["Injection", "Disposal"]).sum()),
        "observation": int((frame.fluid == "Observation").sum()),
        "matched_to_production": int(frame.get("uwi").notna().sum()) if "uwi" in frame else 0,
        "reported_producing": int((oil.fillna(0) > 0).sum()) if oil is not None else 0,
        "operators": int(frame.get("operator").nunique()) if "operator" in frame else 0,
        "integrity_records": len(integrity_cells()),
        "facilities": int(len(facilities)),
        "pipeline_segments": int(len(pipelines)),
        "st37_release": st37_meta.get("source_last_edit") or st37_meta.get("retrieved_at"),
        "st37_retrieved": st37_meta.get("retrieved_at"),
        "production_period": pmeta.get("latest_month"),
        "production_months": pmeta.get("months"),
        "production_retrieved": pmeta.get("retrieved_at"),
    }


def join_report() -> dict:
    """Honest ST37 <-> Petrinex join statistics; failed joins are never hidden."""
    from . import petrinex_cache

    st37 = records("st37")
    if st37.empty:
        return {"available": False, "reason": "AER ST37 not imported"}
    link = petrinex_cache.cell_link()
    pstats = petrinex_cache.cache_meta() or {}
    report = {
        "available": True,
        "st37_wells_imported": int(len(st37)),
        "st37_with_parsed_legal_location": int(st37.ats_cell.notna().sum()),
        "st37_distinct_legal_cells": int(st37.ats_cell.nunique()),
        "petrinex_reporting_wells": int(pstats.get("wells", 0)),
        "petrinex_production_records": int(pstats.get("records", 0)),
        "petrinex_months": pstats.get("months"),
    }
    if link is None or link.empty:
        report.update({"matched_wells": 0, "unmatched_petrinex_cells": pstats.get("wells", 0),
                       "note": "Petrinex volumetric data not imported"})
        return report
    frame = wells()
    matched = frame.uwi.notna()
    report.update({
        "unambiguous_link_cells": int(len(link)),
        "st37_wells_linked": int(matched.sum()),
        "st37_wells_unlinked": int((~matched).sum()),
        "st37_links_blocked_by_shared_location": int(frame.link_blocked_by_shared_location.fillna(False).sum()),
        "ambiguous_cells_excluded": int(pstats.get("ambiguous_cells", 0)),
        "petrinex_cells_without_st37_match": int(len(set(link.ats_cell) - set(st37.ats_cell.dropna()))),
        "join_key": "Alberta Township System cell (LSD-Sec-Twp-Rge-Meridian) parsed from the AER surface "
                    "location and from the Petrinex UWI. Structural identifier join — no fuzzy name matching.",
        "ambiguity_rule": "The link must be unique in both directions. A legal subdivision holding more than "
                          "one reporting Petrinex well, or more than one AER ST37 record, is excluded from the "
                          "production link: the reported volume cannot be attributed to a single map point "
                          "without the operator's own well list.",
    })
    return report
