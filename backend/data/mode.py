"""Data mode: SYNTHETIC (the existing demo) or REAL (public regulatory data).

Design rule: this module **wraps** the existing systems, it never replaces them.

* SYNTHETIC resolves to the bundled synthetic data set and the existing simulated
  SCADA/demo behaviour, completely unchanged.
* REAL resolves to a real public data set (AER/Petrinex today) plus the Alberta
  public map caches, and reports every field the public sources do not publish as
  unavailable rather than borrowing a synthetic value.

Default is SYNTHETIC so the full demo remains available immediately.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import config
from . import store

SYNTHETIC = "SYNTHETIC"
REAL = "REAL"
MODES = (SYNTHETIC, REAL)

_MODE_FILE: Path = config.PROCESSED_DIR / "data_mode.json"

# The analytical data set each mode uses. Synthetic is fixed; the real slot is
# whichever real public data set has been imported.
SYNTHETIC_DATASET = "synthetic"
REAL_DATASET_PREFERENCE = ("texas_rrc", "alberta_petrinex")


def _read() -> dict:
    if _MODE_FILE.exists():
        try:
            return json.loads(_MODE_FILE.read_text())
        except Exception:
            pass
    return {"mode": SYNTHETIC}


def current() -> str:
    mode = _read().get("mode", SYNTHETIC)
    return mode if mode in MODES else SYNTHETIC


def real_dataset_name() -> str | None:
    """The imported real data set backing REAL mode, or None when none is installed."""
    available = {d["name"] for d in store.list_datasets()}
    for name in REAL_DATASET_PREFERENCE:
        if name in available and store.dataset_health(name).get("usable"):
            return name
    return None


def dataset_for(mode: str) -> str | None:
    return SYNTHETIC_DATASET if mode == SYNTHETIC else real_dataset_name()


def set_mode(mode: str) -> dict:
    """Switch mode and point the analytical data set at that mode's data.

    Never falls back across modes: selecting REAL with no real data set imported
    leaves REAL selected and reports that it needs importing, rather than quietly
    serving synthetic rows under a REAL badge.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown data mode: {mode}")
    target = dataset_for(mode)
    activated = None
    if target:
        store.set_active_dataset(target)
        activated = target
    _MODE_FILE.write_text(json.dumps({"mode": mode, "dataset": activated}, indent=2))
    return {"mode": mode, "dataset": activated, "ready": bool(activated)}


def sync_from_active() -> str:
    """Keep the mode flag honest if the active data set was changed directly."""
    active = store.active_dataset_name()
    mode = SYNTHETIC if active == SYNTHETIC_DATASET else REAL
    if mode != current():
        _MODE_FILE.write_text(json.dumps({"mode": mode, "dataset": active}, indent=2))
    return mode


def describe() -> dict:
    """Mode banner content: label, source line and reporting date."""
    from . import alberta, petrinex_cache

    mode = current()
    real_name = real_dataset_name()
    if mode == SYNTHETIC:
        meta = {}
        try:
            meta = store.load_dataset(SYNTHETIC_DATASET).meta
        except Exception:
            pass
        return {
            "mode": SYNTHETIC,
            "label": "Synthetic Demo",
            "detail": "Simulated SCADA",
            "source_line": "Synthetic Demo • Simulated SCADA",
            "scada": "Simulated live telemetry (demo)",
            "scada_live": True,
            "reporting_date": (meta.get("date_range") or [None, None])[1],
            "dataset": SYNTHETIC_DATASET,
            "ready": True,
            "real_available": bool(real_name),
        }
    pmeta = petrinex_cache.cache_meta() or {}
    st37 = alberta.meta("st37") or {}
    return {
        "mode": REAL,
        "label": "AER + Petrinex Public Data",
        "detail": "Reported monthly volumes — not telemetry",
        "source_line": "AER + Petrinex Public Data",
        "scada": "Live SCADA not connected",
        "scada_live": False,
        "reporting_date": pmeta.get("latest_month"),
        "st37_retrieved": st37.get("retrieved_at"),
        "dataset": real_name,
        "ready": bool(real_name),
        "needs_import": None if real_name else
            "No real public data set is imported yet. Install it from the Data hub or run "
            "scripts/update_alberta_data.py --all, then python scripts/fetch_petrinex.py.",
        "real_available": bool(real_name),
    }
