"""Alberta Petrinex public conventional volumetric data → CORE canonical tables.

Source: Petrinex Alberta Public Data (https://www.petrinex.ca/public-data/apd/), API pattern documented in the
Petrinex learning aid: https://www.petrinex.gov.ab.ca/publicdata/API/Files/AB/Vol/{YYYY-MM}/CSV (zip of CSV).
Units are kept as reported: liquids m3, gas e3m3, hours. Confidential rows show '***' and are dropped.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

API = "https://www.petrinex.gov.ab.ca/publicdata/API/Files/AB/Vol/{month}/CSV"
REQUIRED = ["ProductionMonth", "ReportingFacilityID", "ActivityID", "ProductID", "FromToID", "Volume"]
OPTIONAL = ["Hours", "FromToIDType", "OperatorName", "OperatorBAID", "ReportingFacilityType", "ReportingFacilityName"]


def _norm_col(c: str) -> str:
    return "".join(ch for ch in str(c) if ch.isalnum())


def validate_schema(df: pd.DataFrame) -> tuple[bool, list[str]]:
    cols = {_norm_col(c) for c in df.columns}
    missing = [c for c in REQUIRED if _norm_col(c) not in cols]
    return (len(missing) == 0), missing


def download_month(month: str, raw_dir: Path, session=None) -> Path:
    import httpx
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"AB_Vol_{month}.zip"
    if target.exists():
        return target
    url = API.format(month=month)
    r = (session or httpx).get(url, timeout=120, follow_redirects=True)
    r.raise_for_status()
    target.write_bytes(r.content)
    return target


def _csv_bytes(path: Path) -> list[bytes]:
    """Petrinex nests a zip inside the downloaded zip; unwrap either shape."""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if names:
            return [z.read(n) for n in names]
        inner = [n for n in z.namelist() if n.lower().endswith(".zip")]
        if not inner:
            raise ValueError(f"{path.name} contains no CSV or nested zip")
        out: list[bytes] = []
        for name in inner:
            with zipfile.ZipFile(io.BytesIO(z.read(name))) as nested:
                out.extend(nested.read(n) for n in nested.namelist() if n.lower().endswith(".csv"))
        if not out:
            raise ValueError(f"{path.name}: nested zip contains no CSV")
        return out


def parse_zip(path: Path) -> pd.DataFrame:
    frames = [pd.read_csv(io.BytesIO(b), dtype=str, low_memory=False) for b in _csv_bytes(path)]
    df = pd.concat(frames, ignore_index=True)
    df.columns = [_norm_col(c) for c in df.columns]
    ok, missing = validate_schema(df)
    if not ok:
        raise ValueError(f"Petrinex file {path.name} is missing expected columns: {missing}. The public file layout may have changed; update backend/data/petrinex.py.")
    return df


def canonicalise(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    d = df.copy()
    d = d[(d.ActivityID.str.upper() == "PROD") & (d.ProductID.str.upper().isin(["OIL", "WATER", "GAS"]))]
    if "FromToIDType" in d.columns:
        d = d[d.FromToIDType.str.upper().isin(["WI", "WELL"]) | d.FromToID.str.upper().str.startswith("ABWI")]
    else:
        d = d[d.FromToID.str.upper().str.startswith("ABWI")]
    d = d[~d.FromToID.astype(str).str.contains(r"\*\*\*", regex=True)]
    d["Volume"] = pd.to_numeric(d.Volume, errors="coerce")
    d["Hours"] = pd.to_numeric(d.get("Hours", np.nan), errors="coerce")
    d["month"] = d.ProductionMonth.str.slice(0, 7)
    piv = d.pivot_table(index=["FromToID", "month", "ReportingFacilityID"], columns=d.ProductID.str.upper(), values="Volume", aggfunc="sum").reset_index()
    hrs = d.groupby(["FromToID", "month"]).Hours.max().reset_index()
    prod = piv.merge(hrs, on=["FromToID", "month"], how="left")
    prod = prod.rename(columns={"FromToID": "well_id", "OIL": "oil_m3", "WATER": "water_m3", "GAS": "gas_e3m3", "ReportingFacilityID": "facility_id"})
    for c in ("oil_m3", "water_m3", "gas_e3m3"):
        if c not in prod.columns:
            prod[c] = np.nan
    prod["hours"] = prod.Hours
    prod["source"] = "Petrinex AB public data"
    prod["status"] = np.where(prod.oil_m3.fillna(0) > 0, "producing", "idle")
    prod = prod[["well_id", "month", "oil_m3", "water_m3", "gas_e3m3", "hours", "status", "facility_id", "source"]]
    months = sorted(prod.month.unique())
    cal = pd.DataFrame({"t": range(len(months)), "month": months})
    cal["days"] = [pd.Period(m).days_in_month for m in months]
    prod = prod.merge(cal[["t", "month"]], on="month")
    ops = d.groupby("FromToID").OperatorName.first() if "OperatorName" in d.columns else None
    fac = d.groupby("FromToID").ReportingFacilityID.first()
    wells = pd.DataFrame({"well_id": sorted(prod.well_id.unique())})
    wells["source_id"] = wells.well_id
    wells["field"] = wells.well_id.map(fac).fillna("unknown").astype(str)   # facility used as grouping proxy; true field codes require the well infrastructure report
    wells["pool"] = None
    wells["operator"] = wells.well_id.map(ops).astype(str) if ops is not None else "unknown"
    wells["jurisdiction"] = "AB"
    wells["facility_id"] = wells.well_id.map(fac).astype(str)
    wells["latitude"] = None
    wells["longitude"] = None
    wells["spud_date"] = None
    wells["completion_date"] = None
    wells["status"] = wells.well_id.map(prod.sort_values("t").groupby("well_id").status.last())
    wells["well_type"] = "producer"
    wells["lift_type"] = None
    wells["role"] = "public"
    facilities = pd.DataFrame({"facility_id": sorted(prod.facility_id.dropna().unique())})
    facilities["field"] = facilities.facility_id
    facilities["fluid_capacity_bpd"] = None      # OPERATOR DATA REQUIRED
    facilities["water_handling"] = "disposal"    # unknown from public data; assumption
    interventions = pd.DataFrame(columns=["intervention_id", "well_id", "date", "t", "type", "cost", "duration_months", "source", "confidence", "kind"])
    return {"wells": wells, "production_monthly": prod.drop(columns=["facility_id"]), "interventions": interventions, "facilities": facilities, "calendar": cal}


def build_alberta(months: list[str], raw_dir: Path, max_wells: int | None = 3000, min_months: int = 24) -> tuple[dict[str, pd.DataFrame], dict]:
    """Build the canonical Alberta dataset from Petrinex months.

    `min_months` is clamped to the requested window: asking for 3 months while
    demanding 24 months of history per well would silently produce an EMPTY
    dataset, which previously imported as a "connected" source with zero rows.
    """
    if not months:
        raise ValueError("No production months requested.")
    min_months = max(1, min(min_months, len(months)))
    frames = []
    for m in months:
        frames.append(parse_zip(download_month(m, raw_dir)))
    df = pd.concat(frames, ignore_index=True)
    tables = canonicalise(df)
    prod = tables["production_monthly"]
    # keep wells with enough history (and optionally cap the number for demo performance)
    counts = prod[prod.oil_m3.fillna(0) > 0].groupby("well_id").size()
    keep = counts[counts >= min_months].index
    if max_wells and len(keep) > max_wells:
        keep = counts.loc[keep].sort_values(ascending=False).index[:max_wells]
    tables["production_monthly"] = prod[prod.well_id.isin(keep)].reset_index(drop=True)
    tables["wells"] = tables["wells"][tables["wells"].well_id.isin(keep)].reset_index(drop=True)
    if tables["wells"].empty or tables["production_monthly"].empty:
        raise ValueError(
            f"Petrinex returned no well that reports oil in at least {min_months} of the "
            f"{len(months)} requested month(s) ({months[0]}…{months[-1]}). Nothing was imported and no "
            "data set was written. Request a wider window of months, or import the file through the CSV wizard."
        )
    meta = {"label": "Petrinex — Alberta Public Data (conventional volumetrics)", "source": "Petrinex Alberta Public Data", "data_mode": "REAL PUBLIC DATA", "months": months, "start": months[0], "n_months": len(months),
            "licence": "Petrinex public data; see https://www.petrinex.ca/terms", "notes": "Field = reporting facility (proxy). No intervention records, coordinates or costs in this source."}
    return tables, meta
