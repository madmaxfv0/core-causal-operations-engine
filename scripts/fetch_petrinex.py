#!/usr/bin/env python3
"""Download and canonicalise Alberta Petrinex public conventional volumetric data (REAL PUBLIC DATA mode).

    python scripts/fetch_petrinex.py --months 2023-01 2025-12          # inclusive range
    python scripts/fetch_petrinex.py --months 2025-01 2025-06 --max-wells 2000 --activate

Source: https://www.petrinex.ca/public-data/apd/  (API: https://www.petrinex.gov.ab.ca/publicdata/API/Files/AB/Vol/{YYYY-MM}/CSV)
Requires internet access. Files are cached under data/raw. Nothing here is fabricated: if the download fails the
script says so and leaves the bundled synthetic data set active.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd  # noqa: E402

from backend import config  # noqa: E402
from backend.data import petrinex, store  # noqa: E402


def month_range(a: str, b: str) -> list[str]:
    return [str(p) for p in pd.period_range(a, b, freq="M")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs=2, metavar=("FROM", "TO"), required=True)
    ap.add_argument("--max-wells", type=int, default=0, help="optional cap for local experiments; 0 = import all matched wells")
    ap.add_argument("--min-months", type=int, default=24, help="keep wells with at least this many producing months")
    ap.add_argument("--activate", action="store_true", help="make the Alberta data set active and rebuild the evidence base")
    a = ap.parse_args()
    months = month_range(*a.months)
    print(f"Downloading {len(months)} monthly files from Petrinex into {config.RAW_DIR} ...")
    try:
        tables, meta = petrinex.build_alberta(months, config.RAW_DIR, max_wells=a.max_wells or None, min_months=a.min_months)
    except Exception as e:
        print(f"FAILED: {e}\nThe bundled synthetic data set remains active. If the file layout changed, update backend/data/petrinex.py.")
        sys.exit(1)
    meta.update({"rows": int(len(tables["production_monthly"])), "date_range": [months[0], months[-1]], "created_at": datetime.utcnow().isoformat() + "Z", "fields": ["oil_m3", "water_m3", "gas_e3m3", "hours"], "quality": "public; confidential rows dropped"})
    store.write_dataset("alberta_petrinex", tables, meta)
    print(f"Alberta data set written: {len(tables['wells'])} wells, {len(tables['production_monthly'])} well-months.")
    if a.activate:
        store.set_active_dataset("alberta_petrinex")
        print("Activated. Rebuilding evidence base ...")
        from backend.core import precompute
        precompute.build_all()
    else:
        print("Activate with: python scripts/init_demo.py --dataset alberta_petrinex --rebuild")


if __name__ == "__main__":
    main()
