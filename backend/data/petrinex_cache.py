"""Petrinex Alberta public volumetric data -> normalized monthly well cache.

Source
------
Petrinex Alberta Public Data, conventional volumetrics:
``https://www.petrinex.gov.ab.ca/publicdata/API/Files/AB/Vol/{YYYY-MM}/CSV``

The endpoint returns a zip that contains a zip that contains the month's CSV.
Volumes are **reported monthly totals** in the units Petrinex publishes
(liquids m3, gas e3m3, hours h).  They are not telemetry and are never relabelled
as such anywhere in the product.

Confidential rows are published with ``***`` in place of the identifier and are
dropped (counted in the ingest statistics rather than silently discarded).
"""
from __future__ import annotations

import io
import json
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config
from . import ats

API = "https://www.petrinex.gov.ab.ca/publicdata/API/Files/AB/Vol/{month}/CSV"
USE_COLS = [
    "ProductionMonth", "OperatorName", "OperatorBAID", "ReportingFacilityID",
    "ReportingFacilityName", "ActivityID", "ProductID", "FromToID", "FromToIDType",
    "FromToIDIdentifier", "Volume", "Hours",
]
REQUIRED_COLS = ["ProductionMonth", "ActivityID", "ProductID", "FromToID", "Volume"]
CACHE = lambda: config.ALBERTA_CACHE_DIR / "petrinex"   # noqa: E731


class PetrinexUnavailable(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_month(month: str, raw_dir: Path | None = None, force: bool = False) -> Path:
    """Download one Petrinex month with retries; never overwrites a good file partially."""
    import httpx

    raw_dir = raw_dir or config.ALBERTA_RAW_DIR / "petrinex"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"AB_Vol_{month}.zip"
    if target.exists() and target.stat().st_size > 1_000_000 and not force:
        return target
    url = API.format(month=month)
    last: Exception | None = None
    for attempt in range(4):
        staging = None
        try:
            with httpx.Client(timeout=httpx.Timeout(30, read=600), follow_redirects=True,
                              headers={"User-Agent": "CORE Alberta public-data importer"}) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with tempfile.NamedTemporaryFile(dir=raw_dir, suffix=".part", delete=False) as tmp:
                        staging = Path(tmp.name)
                        for chunk in response.iter_bytes(1 << 20):
                            tmp.write(chunk)
            if staging.stat().st_size < 100_000:
                raise PetrinexUnavailable(f"{month}: response too small ({staging.stat().st_size} bytes)")
            with zipfile.ZipFile(staging):        # integrity check before replacing
                pass
            staging.replace(target)               # atomic
            return target
        except Exception as exc:
            last = exc
            if staging and staging.exists():
                staging.unlink(missing_ok=True)
            time.sleep(min(30, 2 ** attempt))
    raise PetrinexUnavailable(f"Petrinex month {month} could not be downloaded: {last}")


def _open_csv(path: Path) -> io.BytesIO:
    """Petrinex nests a zip inside the downloaded zip; unwrap either shape."""
    with zipfile.ZipFile(path) as outer:
        names = outer.namelist()
        csvs = [n for n in names if n.lower().endswith(".csv")]
        if csvs:
            return io.BytesIO(outer.read(csvs[0]))
        inner_names = [n for n in names if n.lower().endswith(".zip")]
        if not inner_names:
            raise PetrinexUnavailable(f"{path.name}: no CSV or nested zip inside the download")
        with zipfile.ZipFile(io.BytesIO(outer.read(inner_names[0]))) as inner:
            inner_csvs = [n for n in inner.namelist() if n.lower().endswith(".csv")]
            if not inner_csvs:
                raise PetrinexUnavailable(f"{path.name}: nested zip contains no CSV")
            return io.BytesIO(inner.read(inner_csvs[0]))


# ---------------------------------------------------------------------------
# Parse / normalize
# ---------------------------------------------------------------------------

def parse_month(path: Path) -> tuple[pd.DataFrame, dict]:
    """Read one month into per-well monthly rows. Raises on a schema change."""
    buffer = _open_csv(path)
    header = pd.read_csv(io.BytesIO(buffer.getvalue()), nrows=0)
    present = set(header.columns)
    missing = [c for c in REQUIRED_COLS if c not in present]
    if missing:
        raise PetrinexUnavailable(
            f"Petrinex schema changed in {path.name}: required column(s) {', '.join(missing)} not found. "
            "Existing cached dataset remains active."
        )
    usecols = [c for c in USE_COLS if c in present]
    raw = pd.read_csv(io.BytesIO(buffer.getvalue()), usecols=usecols, dtype=str, low_memory=False)
    total_rows = len(raw)

    activity = raw.ActivityID.fillna("").str.upper()
    product = raw.ProductID.fillna("").str.upper()
    keep_activity = activity.isin(["PROD", "INJ", "REC", "DISP"])
    rows = raw[keep_activity & product.isin(["OIL", "GAS", "WATER"])].copy()
    rows["activity"] = activity[rows.index]
    rows["product"] = product[rows.index]

    identifier = rows.get("FromToIDIdentifier")
    if identifier is None:
        identifier = rows.FromToID
    identifier = identifier.fillna(rows.FromToID).astype(str)
    confidential = identifier.str.contains(r"\*", regex=True)
    rows = rows[~confidential]
    identifier = identifier[~confidential]

    if "FromToIDType" in rows:
        is_well = rows.FromToIDType.fillna("").str.upper().eq("WI")
    else:
        is_well = rows.FromToID.fillna("").str.upper().str.startswith("ABWI")
    rows = rows[is_well]
    identifier = identifier[is_well]

    parsed = identifier.map(ats.parse_uwi)
    valid = parsed.notna()
    rows = rows[valid]
    parsed = parsed[valid]
    if rows.empty:
        raise PetrinexUnavailable(f"{path.name}: no well-level rows parsed")

    rows["uwi"] = [p["uwi"] for p in parsed]
    rows["ats_cell"] = [p["cell"] for p in parsed]
    rows["legal_location"] = [p["legal_location"] for p in parsed]
    rows["month"] = rows.ProductionMonth.str.slice(0, 7)
    rows["volume"] = pd.to_numeric(rows.Volume, errors="coerce")
    rows["hours"] = pd.to_numeric(rows.get("Hours"), errors="coerce")

    prod = rows[rows.activity == "PROD"]
    inj = rows[rows.activity.isin(["INJ", "DISP"])]

    def _pivot(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["uwi", "month"])
        table = frame.pivot_table(index=["uwi", "month"], columns="product", values="volume", aggfunc="sum")
        table.columns = [f"{prefix}{c.lower()}" for c in table.columns]
        return table.reset_index()

    volumes = _pivot(prod, "")
    injection = _pivot(inj, "inj_")
    hours = rows.groupby(["uwi", "month"], as_index=False).hours.max()
    attrs = rows.sort_values("month").groupby("uwi", as_index=False).agg(
        ats_cell=("ats_cell", "last"),
        legal_location=("legal_location", "last"),
        operator=("OperatorName", "last") if "OperatorName" in rows else ("uwi", "last"),
        facility_id=("ReportingFacilityID", "last") if "ReportingFacilityID" in rows else ("uwi", "last"),
        facility_name=("ReportingFacilityName", "last") if "ReportingFacilityName" in rows else ("uwi", "last"),
    )

    monthly = volumes.merge(injection, on=["uwi", "month"], how="outer").merge(hours, on=["uwi", "month"], how="left")
    monthly = monthly.rename(columns={"oil": "oil_m3", "water": "water_m3", "gas": "gas_e3m3",
                                      "inj_water": "inj_water_m3", "inj_gas": "inj_gas_e3m3", "inj_oil": "inj_oil_m3"})
    for col in ("oil_m3", "water_m3", "gas_e3m3", "inj_water_m3", "inj_gas_e3m3"):
        if col not in monthly:
            monthly[col] = np.nan
    stats = {
        "source_rows": int(total_rows),
        "well_rows_kept": int(len(rows)),
        "confidential_rows_dropped": int(confidential.sum()),
        "wells": int(monthly.uwi.nunique()),
        "records": int(len(monthly)),
    }
    return monthly, {"attrs": attrs, "stats": stats}


def available_months(count: int = 12, end: str | None = None) -> list[str]:
    """Most recent `count` months ending at `end` (default: two months back from today)."""
    if end:
        anchor = pd.Period(end, freq="M")
    else:
        anchor = pd.Period(datetime.now(timezone.utc).strftime("%Y-%m"), freq="M") - 2
    return [str(anchor - i) for i in range(count - 1, -1, -1)]


def build(months: list[str], progress=None) -> dict:
    """Download + normalize the requested months and replace the cache atomically."""
    frames, attr_frames, per_month = [], [], {}
    for index, month in enumerate(months):
        if progress:
            progress(f"downloading {month}", index, len(months))
        path = download_month(month)
        if progress:
            progress(f"parsing {month}", index, len(months))
        monthly, extra = parse_month(path)
        frames.append(monthly)
        attr_frames.append(extra["attrs"])
        per_month[month] = extra["stats"]
    if not frames:
        raise PetrinexUnavailable("no months requested")
    monthly = pd.concat(frames, ignore_index=True).drop_duplicates(["uwi", "month"], keep="last")
    attrs = pd.concat(attr_frames, ignore_index=True).drop_duplicates("uwi", keep="last")

    monthly["days"] = [pd.Period(m).days_in_month for m in monthly.month]
    # Water cut is UNDEFINED - not zero - unless both liquid phases were reported and
    # some liquid was actually produced.  A missing water declaration must never be
    # read as "no water".
    liquid = monthly.oil_m3.fillna(0) + monthly.water_m3.fillna(0)
    defined = monthly.water_m3.notna() & monthly.oil_m3.notna() & (liquid > 0)
    monthly["water_cut"] = np.where(defined, monthly.water_m3 / liquid.replace(0, np.nan), np.nan)
    monthly["oil_m3_per_day"] = monthly.oil_m3 / monthly.days
    monthly = monthly.sort_values(["uwi", "month"]).reset_index(drop=True)

    latest_month = monthly.month.max()
    latest = monthly[monthly.month == latest_month].set_index("uwi")
    counts = monthly.groupby("uwi").size().rename("months_reported")
    wells = attrs.set_index("uwi").join(counts).join(
        latest[["oil_m3", "gas_e3m3", "water_m3", "water_cut", "oil_m3_per_day"]]
    ).reset_index()
    wells["latest_month"] = latest_month

    # Ambiguity guard: a legal subdivision with more than one reporting well cannot
    # be attributed to a single ST37 point without the operator's own well list.
    per_cell = wells.groupby("ats_cell").uwi.nunique()
    unique_cells = set(per_cell[per_cell == 1].index)
    link = wells[wells.ats_cell.isin(unique_cells)].copy()
    link["candidates"] = 1

    meta = {
        "source": "Petrinex",
        "dataset": "Petrinex Alberta Public Data — Conventional Volumetrics",
        "publisher": "Petrinex (Alberta jurisdiction)",
        "licence": "Petrinex public data terms — https://www.petrinex.ca/terms",
        "landing_page": "https://www.petrinex.ca/public-data/apd/",
        "source_url": API.format(month="{YYYY-MM}"),
        "value_type": "REPORTED (monthly volumetric declarations, not telemetry)",
        "units": {"oil_m3": "m3/month", "water_m3": "m3/month", "gas_e3m3": "e3m3/month", "hours": "h/month"},
        "months": months,
        "latest_month": latest_month,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "wells": int(wells.uwi.nunique()),
        "records": int(len(monthly)),
        "distinct_cells": int(wells.ats_cell.nunique()),
        "unambiguous_cells": int(len(unique_cells)),
        "ambiguous_cells": int((per_cell > 1).sum()),
        "per_month": per_month,
    }

    out_dir = CACHE()
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="petrinex-", dir=out_dir.parent))
    try:
        monthly.to_parquet(staging / "monthly.parquet", index=False)
        wells.to_parquet(staging / "wells.parquet", index=False)
        link[["ats_cell", "uwi", "operator", "facility_id", "facility_name", "latest_month",
              "oil_m3", "gas_e3m3", "water_m3", "water_cut", "oil_m3_per_day",
              "months_reported", "candidates"]].to_parquet(staging / "link.parquet", index=False)
        (staging / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
        backup = out_dir.with_name(out_dir.name + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        if out_dir.exists():
            out_dir.rename(backup)
        staging.rename(out_dir)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _MEMO.clear()
    return meta


# ---------------------------------------------------------------------------
# Read side
# ---------------------------------------------------------------------------
_MEMO: dict[str, tuple[float, object]] = {}


def cache_stamp() -> float:
    path = CACHE() / "link.parquet"
    return path.stat().st_mtime if path.exists() else 0.0


def cache_meta() -> dict | None:
    path = CACHE() / "meta.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _read(name: str) -> pd.DataFrame | None:
    path = CACHE() / name
    if not path.exists():
        return None
    stamp = path.stat().st_mtime
    hit = _MEMO.get(name)
    if hit and hit[0] == stamp:
        return hit[1]
    frame = pd.read_parquet(path)
    _MEMO[name] = (stamp, frame)
    return frame


def cell_link() -> pd.DataFrame | None:
    return _read("link.parquet")


def monthly() -> pd.DataFrame | None:
    return _read("monthly.parquet")


def history(uwi: str) -> pd.DataFrame:
    frame = monthly()
    if frame is None:
        return pd.DataFrame()
    return frame[frame.uwi == uwi].sort_values("month")


def well_record(uwi: str) -> dict | None:
    frame = _read("wells.parquet")
    if frame is None:
        return None
    hit = frame[frame.uwi == uwi]
    if hit.empty:
        return None
    row = hit.iloc[0]
    return row.where(pd.notna(row), None).to_dict()
