#!/usr/bin/env python3
"""Initialise (or reset) the CORE demo.

    python scripts/init_demo.py            # generate synthetic data (if missing), sample documents, precompute evidence base
    python scripts/init_demo.py --reset    # restore demo state: decisions, scenarios, review queue, settings, plan edits
    python scripts/init_demo.py --rebuild  # force regeneration of data and all caches
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, state  # noqa: E402
from backend.archive import extraction as archive  # noqa: E402
from backend.core import engine, precompute, synthetic  # noqa: E402
from backend.data import store  # noqa: E402


def generate_synthetic(log=print):
    t = time.time()
    tabs = synthetic.generate()
    store.write_dataset("synthetic", tabs, {"label": "SYNTHETIC — FOR METHOD VALIDATION", "source": "CORE synthetic generator (planted truth)", "data_mode": "SYNTHETIC VALIDATION DATA", "start": "2019-01", "n_months": 84,
                                            "rows": int(len(tabs["production_monthly"])), "date_range": ["2019-01", "2025-12"], "fields": ["well_id", "month", "oil_m3", "water_m3", "gas_e3m3", "hours", "status"],
                                            "quality": "planted DQ faults", "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    log(f"Synthetic data set written ({time.time() - t:.0f}s): {len(tabs['wells'])} wells, {len(tabs['production_monthly'])} rows, {len(tabs['interventions'])} intervention records")


def reset_state(log=print):
    state.reset()
    config.reset_settings()
    archive.write_samples()
    archive.reset_bundled()
    for d in archive.documents():
        try:
            archive.extract(d["document_id"])
        except Exception as e:
            log(f"extraction failed for {d['file_name']}: {e}")
    log("Demo state reset: decisions, scenarios, plan edits, settings, archive review queue")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--dataset", default=None, help="activate a dataset (e.g. synthetic, alberta)")
    a = ap.parse_args()
    if a.dataset:
        store.set_active_dataset(a.dataset)
    if a.rebuild or not (config.PROCESSED_DIR / "synthetic" / "meta.json").exists():
        generate_synthetic()
        if store.active_dataset_name() == "synthetic":
            engine.cache_clear()
    if not (config.PROCESSED_DIR / "active.txt").exists():
        store.set_active_dataset("synthetic")
    if a.reset or a.rebuild or not config.STATE_FILE.exists():
        reset_state()
    if a.rebuild or precompute.stale():
        print("Precomputing evidence base (this runs every causal analysis once; a few minutes on first run)...")
        last = {"t": time.time()}

        def prog(msg):
            if time.time() - last["t"] > 5:
                print("  " + msg)
                last["t"] = time.time()
        precompute.build_all(progress=prog)
    else:
        print("Evidence base is current.")
    print("Done. Start the app with: scripts/start_demo.sh (or: uvicorn backend.api.main:app --port 8000)")


if __name__ == "__main__":
    main()
