"""CORE configuration: paths, model version, default settings (all editable, all tagged with provenance)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CORE_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DEMO_DIR = DATA_DIR / "demo"
DOCS_DIR = DEMO_DIR / "documents"
UPLOAD_DIR = DATA_DIR / "uploads"
CACHE_DIR = PROCESSED_DIR / "cache"
ALBERTA_DIR = DATA_DIR / "alberta"
ALBERTA_RAW_DIR = ALBERTA_DIR / "raw"
ALBERTA_CACHE_DIR = ALBERTA_DIR / "cache"
STATE_FILE = DEMO_DIR / "state.json"
SETTINGS_FILE = DEMO_DIR / "settings.json"

for d in (RAW_DIR, PROCESSED_DIR, DEMO_DIR, DOCS_DIR, UPLOAD_DIR, CACHE_DIR, ALBERTA_DIR, ALBERTA_RAW_DIR, ALBERTA_CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)

MODEL_VERSION = "0.1.0"
M3_TO_BBL = 6.28981

# Provenance tags used everywhere a number is shown.
PUBLIC_ASSUMPTION = "PUBLIC ASSUMPTION"
OPERATOR_PROVIDED = "OPERATOR PROVIDED"
CALCULATED = "CALCULATED"
MODEL_ESTIMATE = "MODEL ESTIMATE"
OPERATOR_DATA_REQUIRED = "OPERATOR DATA REQUIRED"


def _a(value: Any, source: str = PUBLIC_ASSUMPTION, note: str = "", unit: str = "") -> dict:
    return {"value": value, "source": source, "note": note, "unit": unit, "as_of": "2026-09-01"}


DEFAULT_SETTINGS: dict[str, Any] = {
    "units": {"volume": "bbl", "currency": "USD"},
    "economics": {
        "oil_price": _a(70.0, note="Illustrative Brent-linked price; replace with operator planning price", unit="$/bbl"),
        "royalty_rate": _a(0.15, note="Illustrative fiscal take", unit="fraction"),
        "lifting_cost": _a(9.0, note="Illustrative operating cost per barrel of oil", unit="$/bbl"),
        "discount_rate": _a(0.10, note="Annual discount rate", unit="fraction"),
        "horizon_months": _a(24, note="Economic evaluation horizon", unit="months"),
        "water": {
            "lift_energy": _a(0.25, note="Electricity to lift fluid", unit="$/bbl water"),
            "separation": _a(0.10, unit="$/bbl water"),
            "treatment": _a(0.35, unit="$/bbl water"),
            "chemicals": _a(0.15, unit="$/bbl water"),
            "transport": _a(0.10, unit="$/bbl water"),
            "disposal": _a(0.60, note="Applied when facility disposes", unit="$/bbl water"),
            "reinjection": _a(0.30, note="Applied when facility reinjects", unit="$/bbl water"),
            "corrosion_scale": _a(None, source=OPERATOR_DATA_REQUIRED, note="No approved cost model in demo", unit="$/bbl water"),
            "capacity_threshold": _a(0.85, note="Facility utilisation above which capacity shadow cost applies", unit="fraction"),
        },
        "intervention_costs": {
            "pump_replacement": _a(45000, unit="$"),
            "cleanout": _a(30000, unit="$"),
            "water_shutoff": _a(120000, unit="$"),
            "stimulation": _a(150000, unit="$"),
            "workover": _a(200000, unit="$"),
            "restart": _a(25000, note="Simple return-to-production without downhole work", unit="$"),
            "pump_optimisation": _a(8000, unit="$"),
            "diagnostic_test": _a(5000, note="Cost of a diagnostic before committing to a job", unit="$"),
        },
        "intervention_duration_months": {
            "pump_replacement": 0.5, "cleanout": 0.5, "water_shutoff": 1.0, "stimulation": 1.0,
            "workover": 1.5, "restart": 0.25, "pump_optimisation": 0.25, "diagnostic_test": 0.25,
        },
    },
    "causal": {
        "default_model": "auto",
        "pre_window": 12,
        "post_window": 12,
        "max_donors": 25,
        "min_donors": 3,
        "bootstrap_samples": 60,
        "placebo_wells": 12,
        "same_field_only": False,
        "seed": 7,
    },
    "restart": {"min_inactive_months": 3, "min_producing_months": 3, "zero_threshold_bpd": 0.5},
    "confidence": {"high": 0.80, "moderate": 0.55, "min_pre_r2": 0.4},
    "portfolio": {
        "budget": 1_000_000, "crews": 2, "rigs": 1, "horizon_months": 12, "max_concurrent": 6,
        "min_npv": 0, "risk_tolerance": 0.6, "objective": "npv",
    },
    "archive": {"llm_provider": os.environ.get("LLM_PROVIDER", "mock"), "auto_approve_confidence": 0.9, "ocr_languages": "rus+aze+eng"},
    "decisions": {"require_reject_reason": True},
}


def deep_merge(base: dict, override: dict) -> dict:
    out = json.loads(json.dumps(base))
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return deep_merge(DEFAULT_SETTINGS, json.loads(SETTINGS_FILE.read_text()))
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def save_settings(settings: dict) -> dict:
    merged = deep_merge(DEFAULT_SETTINGS, settings)
    SETTINGS_FILE.write_text(json.dumps(merged, indent=2))
    return merged


def reset_settings() -> dict:
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()
    return load_settings()


def val(assumption: Any) -> Any:
    """Read the value out of a provenance-tagged assumption (or pass a plain number through)."""
    if isinstance(assumption, dict) and "value" in assumption:
        return assumption["value"]
    return assumption
