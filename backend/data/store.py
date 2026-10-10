"""Canonical data store.

Tables live as Parquet under data/processed/<dataset>/ and are queried through DuckDB.
Source units are never overwritten: oil_m3/water_m3 stay as reported, oil_bbl/water_bbl are added.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from ..config import M3_TO_BBL, PROCESSED_DIR

CANONICAL_TABLES = ["wells", "production_monthly", "interventions", "facilities", "calendar"]


def dataset_dir(name: str) -> Path:
    d = PROCESSED_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


class EmptyDatasetError(ValueError):
    """A data set with no wells or no production rows is not usable and is never written.

    Guards the failure mode where a source 'connects' successfully, writes an empty
    data set, becomes active, and takes every downstream page down with it.
    """


def validate_tables(name: str, tables: dict[str, pd.DataFrame]) -> dict:
    """Row counts for an import, raising when the result is structurally unusable."""
    wells = tables.get("wells")
    prod = tables.get("production_monthly")
    n_wells = 0 if wells is None else int(len(wells))
    n_prod = 0 if prod is None else int(len(prod))
    if n_wells == 0 or n_prod == 0:
        raise EmptyDatasetError(
            f"'{name}' produced {n_wells} wells and {n_prod} production rows. An empty data set is not "
            "written and not activated — the previous data set stays active. Check the source window, "
            "filters and credentials, then try again."
        )
    if wells is not None and "well_id" not in wells.columns:
        raise EmptyDatasetError(f"'{name}' has no well_id column in its wells table; refusing to import.")
    return {"wells": n_wells, "production_rows": n_prod}


def write_dataset(name: str, tables: dict[str, pd.DataFrame], meta: dict) -> None:
    counts = validate_tables(name, tables)
    d = dataset_dir(name)
    for k, df in tables.items():
        df.to_parquet(d / f"{k}.parquet", index=False)
    meta = dict(meta)
    meta.setdefault("rows", counts["production_rows"])
    meta["n_wells"] = counts["wells"]
    meta["dataset_version"] = hashlib.sha1(json.dumps({k: len(v) for k, v in tables.items()}, sort_keys=True).encode()).hexdigest()[:10]
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    load_dataset.cache_clear()


def list_datasets() -> list[dict]:
    out = []
    for d in sorted(PROCESSED_DIR.iterdir()):
        if (d / "meta.json").exists():
            m = json.loads((d / "meta.json").read_text())
            m["name"] = d.name
            out.append(m)
    return out


def active_dataset_name() -> str:
    f = PROCESSED_DIR / "active.txt"
    if f.exists():
        n = f.read_text().strip()
        if (PROCESSED_DIR / n / "meta.json").exists():
            return n
    return "synthetic"


def dataset_health(name: str) -> dict:
    """Cheap structural check used before a data set is allowed to become active."""
    d = PROCESSED_DIR / name
    if not (d / "meta.json").exists():
        return {"usable": False, "reason": f"Data set '{name}' is not initialised."}
    try:
        wells = pd.read_parquet(d / "wells.parquet")
        prod = pd.read_parquet(d / "production_monthly.parquet")
    except Exception as exc:
        return {"usable": False, "reason": f"Data set '{name}' could not be read: {exc}"}
    if len(wells) == 0 or len(prod) == 0 or "well_id" not in wells.columns:
        return {"usable": False, "wells": int(len(wells)), "production_rows": int(len(prod)),
                "reason": f"Data set '{name}' has {len(wells)} wells and {len(prod)} production rows. "
                          "It cannot be used for analysis."}
    return {"usable": True, "wells": int(len(wells)), "production_rows": int(len(prod))}


def set_active_dataset(name: str) -> None:
    health = dataset_health(name)
    if not health["usable"]:
        raise EmptyDatasetError(health["reason"])
    (PROCESSED_DIR / "active.txt").write_text(name)
    load_dataset.cache_clear()


def derive_production(prod: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    p = prod.copy()
    if "t" not in p.columns:
        tmap = dict(zip(calendar.month, calendar.t))
        p["t"] = p.month.map(tmap)
    p = p.merge(calendar[["t", "days"]], on="t", how="left")
    for c in ("oil_m3", "water_m3", "gas_e3m3", "hours"):
        if c not in p.columns:
            p[c] = np.nan
    p["oil_bbl"] = p.oil_m3 * M3_TO_BBL
    p["water_bbl"] = p.water_m3 * M3_TO_BBL
    p["total_fluid_bbl"] = p.oil_bbl.fillna(0) + p.water_bbl.fillna(0)
    p["oil_bpd"] = p.oil_bbl / p.days
    p["water_bpd"] = p.water_bbl / p.days
    fluid = p.oil_m3.fillna(0) + p.water_m3.fillna(0)
    p["water_cut"] = np.where(fluid > 0, p.water_m3.fillna(0) / fluid, np.nan)
    return p


@dataclass
class Dataset:
    name: str
    meta: dict
    wells: pd.DataFrame
    production: pd.DataFrame
    interventions: pd.DataFrame
    facilities: pd.DataFrame
    calendar: pd.DataFrame
    truth_events: pd.DataFrame | None = None
    truth_monthly: pd.DataFrame | None = None
    _panel: dict = field(default_factory=dict)

    @property
    def n_months(self) -> int:
        return len(self.calendar)

    @property
    def months(self) -> list[str]:
        return self.calendar.month.tolist()

    @property
    def days(self) -> np.ndarray:
        return self.calendar.days.to_numpy(dtype=float)

    def panel(self, col: str = "oil_bpd") -> pd.DataFrame:
        """Wide matrix t × well_id (duplicates aggregated by mean, missing months left NaN)."""
        if col not in self._panel:
            p = self.production.groupby(["t", "well_id"])[col].mean().unstack("well_id")
            p = p.reindex(range(self.n_months))
            self._panel[col] = p
        return self._panel[col]

    def well_series(self, well_id: str) -> pd.DataFrame:
        s = self.production[self.production.well_id == well_id].sort_values("t")
        s = s.drop_duplicates("t", keep="first")
        return s.set_index("t").reindex(range(self.n_months)).reset_index()

    def query(self, sql: str) -> pd.DataFrame:
        con = duckdb.connect()
        for name, df in (("wells", self.wells), ("production_monthly", self.production), ("interventions", self.interventions), ("facilities", self.facilities), ("calendar", self.calendar)):
            con.register(name, df)
        return con.execute(sql).df()


@lru_cache(maxsize=4)
def load_dataset(name: str | None = None) -> Dataset:
    name = name or active_dataset_name()
    d = PROCESSED_DIR / name
    if not (d / "meta.json").exists():
        raise FileNotFoundError(f"Dataset '{name}' is not initialised. Run: python scripts/init_demo.py")
    meta = json.loads((d / "meta.json").read_text())
    wells = pd.read_parquet(d / "wells.parquet")
    if len(wells) == 0 or "well_id" not in wells.columns:
        # Loud and actionable, never a silent swap to synthetic data.
        raise EmptyDatasetError(
            f"The active data set '{name}' contains no usable wells, so no page can be calculated from it. "
            "Select a different data context in the Data Hub, or re-import this source over a wider window."
        )
    calendar = pd.read_parquet(d / "calendar.parquet")
    prod = derive_production(pd.read_parquet(d / "production_monthly.parquet"), calendar)
    interventions = pd.read_parquet(d / "interventions.parquet") if (d / "interventions.parquet").exists() else pd.DataFrame(columns=["intervention_id", "well_id", "date", "t", "type", "cost", "duration_months", "source", "confidence", "kind"])
    facilities = pd.read_parquet(d / "facilities.parquet") if (d / "facilities.parquet").exists() else pd.DataFrame(columns=["facility_id", "field", "fluid_capacity_bpd", "water_handling"])
    te = pd.read_parquet(d / "truth_events.parquet") if (d / "truth_events.parquet").exists() else None
    tm = pd.read_parquet(d / "truth_monthly.parquet") if (d / "truth_monthly.parquet").exists() else None
    return Dataset(name=name, meta=meta, wells=wells, production=prod, interventions=interventions, facilities=facilities, calendar=calendar, truth_events=te, truth_monthly=tm)


def rate_stats(ds: Dataset, well_id: str, t_from: int, t_to: int) -> dict:
    s = ds.well_series(well_id)
    w = s[(s.t >= t_from) & (s.t <= t_to)]
    return {"oil_bpd": float(np.nanmean(w.oil_bpd)) if len(w) else float("nan"), "water_cut": float(np.nanmean(w.water_cut)) if len(w) else float("nan")}
